import logging

from categorization import categorize_transaction, load_category_rules
from google_sheets import clear_transactions_sheet, connect_to_sheets, get_transaction_sheet, recategorize_existing, sync_categories_to_sheet
from parsers import build_transaction_hash, normalize_amount, parse_bank_file
from settings import INPUT_DIR, WORKSHEET_TRANSACTIONS

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def process_files(force_reset: bool = False) -> None:
    """Load all input transactions and append them to the Google Sheets worksheet."""
    category_data = load_category_rules()

    logger.info("Connecting to Google Sheets...")
    spreadsheet = connect_to_sheets()
    sheet = get_transaction_sheet(spreadsheet)

    sync_categories_to_sheet(spreadsheet, category_data)

    if force_reset:
        clear_transactions_sheet(sheet)
        existing_hashes: set[str] = set()
    else:
        existing_hashes = set(sheet.col_values(1)[1:])

    logger.info("Transactions already present in the sheet: %s", len(existing_hashes))

    files = sorted(
        item for item in INPUT_DIR.iterdir()
        if item.is_file()
        and item.suffix.lower() in {".xls", ".xlsx", ".csv"}
        and not item.name.startswith("~$")
    )

    if not files:
        logger.warning("No files found in the /input folder")
        return

    new_rows: list[list[object]] = []

    for filepath in files:
        logger.info("Reading file: %s", filepath)

        try:
            df, bank_label = parse_bank_file(filepath)

            for _, row in df.iterrows():
                if row["date"] is None or row["amount"] is None:
                    continue

                date_obj = row["date"]
                amount_val = normalize_amount(row["amount"])
                desc_val = str(row["description"]).strip()
                hash_val = build_transaction_hash(bank_label, str(date_obj), amount_val, desc_val)

                if hash_val in existing_hashes:
                    continue

                category_name = categorize_transaction(desc_val, amount_val, category_data)
                new_rows.append(
                    [
                        hash_val,
                        str(date_obj),
                        bank_label,
                        category_name,
                        amount_val,
                        desc_val,
                        str(date_obj)[:7],
                    ]
                )
                existing_hashes.add(hash_val)

        except Exception as exc:
            logger.error("Error while processing %s: %s", filepath, exc)

    if new_rows:
        logger.info("Sending %s new transactions to Google Sheets...", len(new_rows))
        sheet.append_rows(new_rows)
        logger.info("Upload completed successfully!")
    else:
        logger.info("No new transactions to add.")


def main() -> None:
    """Main interactive menu for the ingestion workflow."""
    print("\n--- 🏦 PERSONAL FINANCE MANAGER ---")
    print("1. Sync new transactions (Normal)")
    print("2. Update ONLY Categories (Fast - apply the new JSON rules to the current sheet)")
    print(
        f"3. Full reset and reload from scratch (Clear '{WORKSHEET_TRANSACTIONS}' and re-read the files)"
    )

    choice = input("\nChoose an option (1/2/3) [Default: 1]: ").strip()

    if choice == "2":
        category_data = load_category_rules()
        spreadsheet = connect_to_sheets()
        sheet = get_transaction_sheet(spreadsheet)
        sync_categories_to_sheet(spreadsheet, category_data)
        recategorize_existing(sheet, category_data, categorize_transaction)
    elif choice == "3":
        confirm = input("⚠️ Are you sure you want to CLEAR the sheet and reload from scratch? (y/n): ").strip().lower()
        if confirm == "y":
            process_files(force_reset=True)
        else:
            logger.info("Operation cancelled.")
    else:
        process_files(force_reset=False)
