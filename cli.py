import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from categorization import TransactionCategorizer, load_category_rules
from google_sheets import DIRECTA_HEADERS, GoogleSheetsClient
from parsers import parse_bank_file
from parsers.utils import (
    build_transaction_hash, normalize_amount,
    COL_DATE, COL_DESCRIPTION, COL_AMOUNT
)
from settings import INPUT_DIR, WORKSHEET_TRANSACTIONS

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


RowBuilder = Callable[[Any, str, Path, int], tuple[str, list[object]] | None]


def _get_input_files(include_directa: bool) -> list[Path]:
    return sorted(
        item
        for item in INPUT_DIR.iterdir()
        if item.is_file()
        and item.suffix.lower() in {".xls", ".xlsx", ".csv"}
        and ("directa" in item.name.lower()) == include_directa
        and not item.name.startswith("~$")
    )


def _collect_new_rows(
    files: list[Path],
    existing_hashes: set[str],
    row_builder: RowBuilder,
    expected_bank_label: str | None = None,
) -> list[list[object]]:
    new_rows: list[list[object]] = []

    for filepath in files:
        logger.info("Processing file: %s", filepath.name)
        file_new_rows = 0
        try:
            dataframe, bank_label = parse_bank_file(filepath)
            if expected_bank_label and bank_label != expected_bank_label:
                logger.info("Skipping non-%s file: %s", expected_bank_label, filepath.name)
                continue

            for row_index, row in dataframe.iterrows():
                built_row = row_builder(row, bank_label, filepath, row_index)
                if built_row is None:
                    continue

                row_hash, sheet_row = built_row
                if row_hash in existing_hashes:
                    logger.info(
                        "Skipping duplicate row %s in %s: hash already exists",
                        row_index,
                        filepath.name,
                    )
                    continue

                existing_hashes.add(row_hash)
                new_rows.append(sheet_row)
                file_new_rows += 1

            logger.info("Added %s new rows from %s", file_new_rows, filepath.name)
        except Exception as exc:
            logger.error("Error processing %s: %s", filepath.name, exc)

    return new_rows


def _sync_input_files(
    files: list[Path],
    client: GoogleSheetsClient,
    worksheet: Any,
    existing_hashes: set[str],
    row_builder: RowBuilder,
    source_name: str,
    expected_bank_label: str | None = None,
) -> None:
    if not files:
        logger.warning("No %s files found in the 'input/' folder.", source_name)
        return

    new_rows = _collect_new_rows(
        files,
        existing_hashes,
        row_builder,
        expected_bank_label,
    )
    if not new_rows:
        logger.info("No %s rows to add.", source_name)
        return

    logger.info("Appending %s %s rows to Google Sheets...", len(new_rows), source_name)
    client.append_rows(new_rows, worksheet)
    logger.info("%s rows uploaded successfully!", source_name)


def process_directa_files() -> None:
    """Import only Directa investment operations to the dedicated worksheet."""
    logger.info("Connecting to Google Sheets for Directa import...")
    client = GoogleSheetsClient()
    files = _get_input_files(include_directa=True)
    existing_hashes = set(client.get_hashes(client.directa_sheet))

    def build_directa_row(
        row: Any,
        bank_label: str,
        filepath: Path,
        row_index: int,
    ) -> tuple[str, list[object]]:
        operation = [
            row.get(header.lower(), "")
            for header in DIRECTA_HEADERS[1:]
        ]
        operation_by_header = {
            header.lower(): value
            for header, value in zip(DIRECTA_HEADERS[1:], operation)
        }
        row_hash = build_transaction_hash(
            "directa",
            str(operation_by_header["date"] or ""),
            normalize_amount(operation_by_header["amount_eur"] or 0),
            str(operation_by_header["description"] or ""),
        )
        return row_hash, [row_hash, *operation]

    _sync_input_files(
        files,
        client,
        client.directa_sheet,
        existing_hashes,
        build_directa_row,
        "Directa",
        expected_bank_label="Directa",
    )


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

    files = _get_input_files(include_directa=False)

    def build_transaction_row(
        row: Any,
        bank_label: str,
        filepath: Path,
        row_index: int,
    ) -> tuple[str, list[object]] | None:
        if row[COL_DATE] is None or row[COL_AMOUNT] is None:
            logger.warning(
                "Skipping row %s in %s: missing date or amount",
                row_index,
                filepath.name,
            )
            return None

        date_obj = row[COL_DATE]
        amount_val = normalize_amount(row[COL_AMOUNT])
        desc_val = str(row[COL_DESCRIPTION]).strip()
        hash_val = build_transaction_hash(
            bank_label, str(date_obj), amount_val, desc_val
        )

        saved_manual_category = manual_overrides.get(hash_val)
        if saved_manual_category is not None:
            category_name = saved_manual_category
            is_manual = True
        else:
            category_name = categorizer.categorize(desc_val, amount_val)
            is_manual = False

        return hash_val, [
            hash_val,
            str(date_obj),
            bank_label,
            category_name,
            amount_val,
            desc_val,
            str(date_obj)[:7],
            is_manual,
        ]

    _sync_input_files(
        files,
        client,
        client.sheet,
        existing_hashes,
        build_transaction_row,
        "standard transaction",
    )


def main() -> None:
    """CLI interface."""
    print("\n--- 🏦 FinApp ---")
    print("1. Sync new transactions (default)")
    print("2. Sync Directa operations")
    print("3. Update Categories (Fast - re-apply JSON rules preserving manual edits)")
    print("4. Reset and reload while preserving manual overrides")
    print(
        "5. Full reset and reload (Clear"
        f" '{WORKSHEET_TRANSACTIONS}' and reload input files)"
    )

    choice = input("\nChoose an option (1/2/3/4/5) [Default: 1]: ").strip()

    if choice == "2":
        process_directa_files()
    elif choice == "3":
        category_data = load_category_rules()
        categorizer = TransactionCategorizer(category_data)

        logger.info("Connecting to Google Sheets...")
        client = GoogleSheetsClient()

        logger.info("Starting recategorization of existing transactions...")
        updated_count = client.recategorize_existing(categorizer)

        logger.info(
            "Recategorization finished. %s transaction(s) were updated.",
            updated_count,
        )
    elif choice == "4":
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
    elif choice == "5":
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