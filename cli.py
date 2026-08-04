import logging

from categorization import TransactionCategorizer, load_category_rules
from google_sheets import GoogleSheetsClient
from parsers import parse_bank_file
from parsers.utils import (
    build_transaction_hash, normalize_amount, 
    COL_DATE, COL_DESCRIPTION, COL_AMOUNT
)
from settings import INPUT_DIR, WORKSHEET_TRANSACTIONS

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def process_files(
    force_reset: bool = False,
    preserve_manual_overrides: bool = False,
) -> None:
    """Import files and upload new transactions to Google Sheets."""
    category_data = load_category_rules()
    categorizer = TransactionCategorizer(category_data)

    logger.info("Connecting to Google Sheets...")
    client = GoogleSheetsClient()
    manual_overrides: dict[str, str] = {}

    if force_reset:
        if preserve_manual_overrides:
            logger.info("Checking manual overrides before clearing the worksheet...")
            manual_overrides = client.get_manual_overrides()
        logger.info("Clearing the worksheet...")
        client.clear()
        existing_hashes: set[str] = set()
    else:
        existing_hashes = set(client.get_hashes())

    logger.info("Existing transactions in sheet: %s", len(existing_hashes))

    files = sorted(
        item
        for item in INPUT_DIR.iterdir()
        if item.is_file()
        and item.suffix.lower() in {".xls", ".xlsx", ".csv"}
        and not item.name.startswith("~$")
    )

    if not files:
        logger.warning("No files found in the 'input/' folder.")
        return

    new_rows: list[list[object]] = []

    for filepath in files:
        logger.info("Processing file: %s", filepath.name)

        try:
            df, bank_label = parse_bank_file(filepath)

            for _, row in df.iterrows():
                if row[COL_DATE] is None or row[COL_AMOUNT] is None:
                    continue

                date_obj = row[COL_DATE]
                amount_val = normalize_amount(row[COL_AMOUNT])
                desc_val = str(row[COL_DESCRIPTION]).strip()
                hash_val = build_transaction_hash(
                    bank_label, str(date_obj), amount_val, desc_val
                )

                if hash_val in existing_hashes:
                    continue

                saved_manual_category = manual_overrides.get(hash_val)
                if saved_manual_category is not None:
                    category_name = saved_manual_category
                    is_manual = True
                else:
                    category_name = categorizer.categorize(desc_val, amount_val)
                    is_manual = False

                new_rows.append(
                    [
                        hash_val,
                        str(date_obj),
                        bank_label,
                        category_name,
                        amount_val,
                        desc_val,
                        str(date_obj)[:7],
                        is_manual,
                    ]
                )
                existing_hashes.add(hash_val)

        except Exception as exc:
            logger.error("Error processing %s: %s", filepath.name, exc)

    if new_rows:
        logger.info(
            "Appending %s new transactions to Google Sheets...", len(new_rows)
        )
        client.append_rows(new_rows)
        logger.info("Upload completed successfully!")
    else:
        logger.info("No new transactions to add.")


def main() -> None:
    """CLI interface."""
    print("\n--- 🏦 FinApp ---")
    print("1. Sync new transactions (default)")
    print("2. Update Categories (Fast - re-apply JSON rules preserving manual edits)")
    print("3. Reset and reload while preserving manual overrides")
    print(
        "4. Full reset and reload (Clear"
        f" '{WORKSHEET_TRANSACTIONS}' and reload input files)"
    )

    choice = input("\nChoose an option (1/2/3/4) [Default: 1]: ").strip()

    if choice == "2":
        category_data = load_category_rules()
        categorizer = TransactionCategorizer(category_data)

        logger.info("Connecting to Google Sheets...")
        client = GoogleSheetsClient()
        
        logger.info("Recategorizing existing transactions...")
        updated_count = client.recategorize_existing(categorizer)
        
        logger.info("Successfully updated categories for %s transaction(s).", updated_count)
    elif choice == "3":
        confirm = (
            input(
                "⚠️ This reset keeps manual override rows. Continue? (y/n): "
            )
            .strip()
            .lower()
        )
        if confirm == "y":
            process_files(force_reset=True, preserve_manual_overrides=True)
        else:
            logger.info("Operation cancelled.")
    elif choice == "4":
        confirm = (
            input(
                "⚠️ Are you sure you want to CLEAR the sheet and reload? (y/n): "
            )
            .strip()
            .lower()
        )
        if confirm == "y":
            process_files(force_reset=True)
        else:
            logger.info("Operation cancelled.")
    else:
        process_files(force_reset=False)

if __name__ == "__main__":
    main()