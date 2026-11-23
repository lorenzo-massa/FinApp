import argparse
import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from categorization import (
    CategoryConfig,
    TransactionCategorizer,
    load_category_rules,
    validate_categories_against_sheet,
)
from google_sheets import DIRECTA_HEADERS, GoogleSheetsClient
from parsers import parse_bank_file
from parsers.utils import (
    build_transaction_hash, normalize_amount,
    COL_DATE, COL_DESCRIPTION, COL_AMOUNT
)
from settings import (
    ARCHIVE_DIR,
    CATEGORIES_FILE,
    INPUT_DIR,
    WORKSHEET_CATEGORIES,
    WORKSHEET_TRANSACTIONS,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


RowBuilder = Callable[[Any, str, Path, int, dict[tuple[str, str, float, str], int]], tuple[str, list[object]] | None]


def _get_input_files(include_directa: bool) -> list[Path]:
    if not INPUT_DIR.exists():
        return []
    return sorted(
        item
        for item in INPUT_DIR.iterdir()
        if item.is_file()
        and item.suffix.lower() in {".xls", ".xlsx", ".csv"}
        and ("directa" in item.name.lower()) == include_directa
        and not item.name.startswith("~$")
    )


def archive_processed_files(files: list[Path], archive_dir: Path | None = None) -> None:
    """Move processed input files to the archive directory."""
    if not files:
        return
    target_dir = archive_dir if archive_dir is not None else ARCHIVE_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    for file in files:
        if not file.exists():
            continue
        dest = target_dir / file.name
        if dest.exists():
            stem = file.stem
            suffix = file.suffix
            counter = 1
            while (target_dir / f"{stem}_{counter}{suffix}").exists():
                counter += 1
            dest = target_dir / f"{stem}_{counter}{suffix}"
        file.rename(dest)
        logger.info("Archived processed file: %s -> %s", file.name, dest.name)


class CollectResult(tuple):
    """Result container for collected rows and metadata with 2-tuple backwards compatibility."""

    new_rows: list[list[object]]
    successful_files: list[Path]
    duplicates_count: int

    def __new__(cls, new_rows: list[list[object]], successful_files: list[Path], duplicates_count: int = 0) -> "CollectResult":
        obj = super().__new__(cls, (new_rows, successful_files))
        obj.new_rows = new_rows
        obj.successful_files = successful_files
        obj.duplicates_count = duplicates_count
        return obj


def print_execution_summary(
    source_name: str,
    files_inspected: int,
    files_successful: int,
    new_rows_count: int,
    duplicates_count: int,
    dry_run: bool,
    archived_count: int = 0,
) -> None:
    mode_label = "DRY RUN (simulation - no changes made)" if dry_run else "LIVE (changes saved to Google Sheets)"
    print("\n" + "=" * 55)
    print(f"📊 EXECUTION SUMMARY ({source_name})")
    print("=" * 55)
    print(f"• Mode:                    {mode_label}")
    print(f"• Files inspected:         {files_inspected}")
    print(f"• Files parsed:            {files_successful}")
    print(f"• New transactions added:  {new_rows_count}")
    print(f"• Duplicates skipped:      {duplicates_count}")
    if archived_count > 0:
        print(f"• Files archived:          {archived_count}")
    print("=" * 55 + "\n")


def _collect_new_rows(
    files: list[Path],
    existing_hashes: set[str],
    row_builder: RowBuilder,
    expected_bank_label: str | None = None,
) -> CollectResult:
    new_rows: list[list[object]] = []
    successful_files: list[Path] = []
    duplicates_count = 0

    for filepath in files:
        logger.info("Processing file: %s", filepath.name)
        file_new_rows = 0
        try:
            dataframe, bank_label = parse_bank_file(filepath)
            if expected_bank_label and bank_label != expected_bank_label:
                logger.info("Skipping non-%s file: %s", expected_bank_label, filepath.name)
                continue

            seen_in_file: dict[tuple[str, str, float, str], int] = {}
            for row_index, row in dataframe.iterrows():
                built_row = row_builder(row, bank_label, filepath, row_index, seen_in_file)
                if built_row is None:
                    continue

                row_hash, sheet_row = built_row
                if row_hash in existing_hashes:
                    logger.info(
                        "Skipping duplicate row %s in %s: hash already exists",
                        row_index,
                        filepath.name,
                    )
                    duplicates_count += 1
                    continue

                existing_hashes.add(row_hash)
                new_rows.append(sheet_row)
                file_new_rows += 1

            logger.info("Added %s new rows from %s", file_new_rows, filepath.name)
            successful_files.append(filepath)
        except Exception as exc:
            logger.error("Error processing %s: %s", filepath.name, exc)

    return CollectResult(new_rows, successful_files, duplicates_count)


def _sync_input_files(
    files: list[Path],
    client: GoogleSheetsClient,
    worksheet: Any,
    existing_hashes: set[str],
    row_builder: RowBuilder,
    source_name: str,
    expected_bank_label: str | None = None,
    dry_run: bool = False,
    archive: bool = False,
) -> list[list[object]]:
    if not files:
        logger.warning("No %s files found in the 'input/' folder.", source_name)
        return []

    collect_res = _collect_new_rows(
        files,
        existing_hashes,
        row_builder,
        expected_bank_label,
    )
    new_rows, successful_files = collect_res.new_rows, collect_res.successful_files
    duplicates_count = collect_res.duplicates_count

    archived_count = 0
    if dry_run:
        logger.info("[DRY RUN] %s new %s row(s) detected (preview):", len(new_rows), source_name)
        for idx, row in enumerate(new_rows[:10], start=1):
            preview_row = [str(cell) for cell in (row[1:6] if len(row) > 6 else row[:5])]
            logger.info("  [%s] %s", idx, " | ".join(preview_row))
        if len(new_rows) > 10:
            logger.info("  ... and %s more row(s).", len(new_rows) - 10)
        if archive:
            logger.info("[DRY RUN] Would archive %s processed file(s) to %s", len(successful_files), ARCHIVE_DIR)
            archived_count = len(successful_files)
        print_execution_summary(
            source_name=source_name,
            files_inspected=len(files),
            files_successful=len(successful_files),
            new_rows_count=len(new_rows),
            duplicates_count=duplicates_count,
            dry_run=True,
            archived_count=archived_count,
        )
        return new_rows

    if not new_rows:
        logger.info("No %s rows to add.", source_name)
    else:
        logger.info("Appending %s %s rows to Google Sheets...", len(new_rows), source_name)
        client.append_rows(new_rows, worksheet)
        logger.info("%s rows uploaded successfully!", source_name)

    if archive and successful_files:
        archive_processed_files(successful_files)
        archived_count = len(successful_files)

    print_execution_summary(
        source_name=source_name,
        files_inspected=len(files),
        files_successful=len(successful_files),
        new_rows_count=len(new_rows),
        duplicates_count=duplicates_count,
        dry_run=False,
        archived_count=archived_count,
    )

    return new_rows


def process_directa_files(
    dry_run: bool = False,
    archive: bool = False,
) -> list[list[object]]:
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
        seen_in_file: dict[tuple[str, str, float, str], int],
    ) -> tuple[str, list[object]]:
        operation = [
            row.get(header.lower(), "")
            for header in DIRECTA_HEADERS[1:]
        ]
        operation_by_header = {
            header.lower(): value
            for header, value in zip(DIRECTA_HEADERS[1:], operation)
        }
        date_val = str(operation_by_header["date"] or "")
        amount_val = normalize_amount(operation_by_header["amount_eur"] or 0)
        desc_val = str(operation_by_header["description"] or "")

        key = ("directa", date_val, amount_val, desc_val.lower())
        occurrence = seen_in_file.get(key, 0)
        seen_in_file[key] = occurrence + 1

        row_hash = build_transaction_hash(
            "directa",
            date_val,
            amount_val,
            desc_val,
            occurrence=occurrence,
        )
        return row_hash, [row_hash, *operation]

    return _sync_input_files(
        files,
        client,
        client.directa_sheet,
        existing_hashes,
        build_directa_row,
        "Directa",
        expected_bank_label="Directa",
        dry_run=dry_run,
        archive=archive,
    )


def check_categories_alignment(
    client: GoogleSheetsClient,
    category_config: CategoryConfig,
    verbose: bool = False,
) -> dict[str, set[str]]:
    """Validate categories in categories.json against the Categories worksheet."""
    valid_sheet_categories = client.get_valid_categories()
    if not valid_sheet_categories:
        if verbose:
            logger.info("Worksheet '%s' is empty or not available. Skipping validation.", WORKSHEET_CATEGORIES)
        return {"unknown_in_json": set(), "uncovered_in_sheet": set()}

    diff = validate_categories_against_sheet(category_config, valid_sheet_categories)
    unknown = sorted(diff["unknown_in_json"])
    uncovered = sorted(diff["uncovered_in_sheet"])

    if unknown:
        logger.warning(
            "⚠️ Category mismatch: %s categories in %s are not in Google Sheet '%s': %s",
            len(unknown),
            CATEGORIES_FILE.name,
            WORKSHEET_CATEGORIES,
            ", ".join(unknown),
        )

    if verbose:
        print("\n" + "=" * 55)
        print("📋 CATEGORIES VALIDATION AUDIT")
        print("=" * 55)
        print(f"• Total sheet categories: {len(valid_sheet_categories)}")
        print(f"• Total JSON categories:  {len(category_config.get('rules', {}))}")
        if unknown:
            print(f"\n❌ In '{CATEGORIES_FILE.name}' but NOT in Google Sheet '{WORKSHEET_CATEGORIES}':")
            for c in unknown:
                print(f"   - {c}")
        else:
            print(f"\n✅ All categories in '{CATEGORIES_FILE.name}' exist in Google Sheet!")

        if uncovered:
            print(f"\nℹ️ In Google Sheet '{WORKSHEET_CATEGORIES}' but NO rules defined in JSON:")
            for c in uncovered:
                print(f"   - {c}")
        print("=" * 55 + "\n")

    return diff


def process_files(
    force_reset: bool = False,
    preserve_manual_overrides: bool = False,
    dry_run: bool = False,
    archive: bool = False,
) -> list[list[object]]:
    """Import files and upload new transactions to Google Sheets."""
    category_data = load_category_rules()
    categorizer = TransactionCategorizer(category_data)

    logger.info("Connecting to Google Sheets...")
    client = GoogleSheetsClient()
    check_categories_alignment(client, category_data, verbose=False)
    manual_overrides: dict[str, str] = {}

    if force_reset:
        if preserve_manual_overrides:
            logger.info("Checking manual overrides before clearing the worksheet...")
            manual_overrides = client.get_manual_overrides()
        if dry_run:
            logger.info("[DRY RUN] Would clear the worksheet (preserve_manual: %s)", preserve_manual_overrides)
        else:
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
        seen_in_file: dict[tuple[str, str, float, str], int],
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

        key = (bank_label, str(date_obj), amount_val, desc_val.lower())
        occurrence = seen_in_file.get(key, 0)
        seen_in_file[key] = occurrence + 1

        hash_val = build_transaction_hash(
            bank_label, str(date_obj), amount_val, desc_val, occurrence=occurrence
        )

        saved_manual_category = manual_overrides.get(hash_val)
        if saved_manual_category is not None:
            category_name = saved_manual_category
            is_manual = True
        else:
            category_name = categorizer.categorize(desc_val, amount_val, bank_label)
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

    return _sync_input_files(
        files,
        client,
        client.sheet,
        existing_hashes,
        build_transaction_row,
        "standard transaction",
        dry_run=dry_run,
        archive=archive,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="FinApp - Personal Finance Ingestor")
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Sync new standard transactions from input/ to Google Sheets",
    )
    parser.add_argument(
        "--directa",
        action="store_true",
        help="Sync Directa investment operations to Google Sheets",
    )
    parser.add_argument(
        "--update-categories",
        action="store_true",
        help="Re-apply category rules from categories.json preserving manual edits",
    )
    parser.add_argument(
        "--reset-preserve",
        action="store_true",
        help="Reset and reload standard transactions while preserving manual overrides",
    )
    parser.add_argument(
        "--reset-full",
        action="store_true",
        help="Full reset and reload of standard transactions",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate execution without modifying Google Sheets",
    )
    parser.add_argument(
        "--archive",
        action="store_true",
        help="Move processed files to input/archive/ upon successful completion",
    )
    parser.add_argument(
        "--validate-categories",
        action="store_true",
        help="Audit categories in categories.json against the Google Sheets Categories tab",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """CLI interface."""
    args = parse_args(argv)

    # Headless execution if any specific flag is passed
    if args.validate_categories:
        category_data = load_category_rules()
        logger.info("Connecting to Google Sheets...")
        client = GoogleSheetsClient()
        check_categories_alignment(client, category_data, verbose=True)
        return
    if args.directa:
        process_directa_files(dry_run=args.dry_run, archive=args.archive)
        return
    if args.update_categories:
        category_data = load_category_rules()
        categorizer = TransactionCategorizer(category_data)
        logger.info("Connecting to Google Sheets...")
        client = GoogleSheetsClient()
        logger.info("Starting recategorization of existing transactions...")
        updated_count = client.recategorize_existing(categorizer, dry_run=args.dry_run)
        logger.info("Recategorization finished. %s transaction(s) were updated.", updated_count)
        return
    if args.reset_preserve:
        process_files(force_reset=True, preserve_manual_overrides=True, dry_run=args.dry_run, archive=args.archive)
        return
    if args.reset_full:
        process_files(force_reset=True, preserve_manual_overrides=False, dry_run=args.dry_run, archive=args.archive)
        return
    if args.sync or args.dry_run or args.archive:
        process_files(force_reset=False, dry_run=args.dry_run, archive=args.archive)
        return

    # Interactive menu when no CLI arguments are supplied
    print("\n--- 🏦 FinApp ---")
    print("1. Sync new transactions (default)")
    print("2. Sync Directa operations")
    print("3. Update Categories (Fast - re-apply JSON rules preserving manual edits)")
    print("4. Reset and reload while preserving manual overrides")
    print(
        "5. Full reset and reload (Clear"
        f" '{WORKSHEET_TRANSACTIONS}' and reload input files)"
    )
    print("6. Validate categories against Google Sheet")

    choice = input("\nChoose an option (1/2/3/4/5/6) [Default: 1]: ").strip()

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
    elif choice == "6":
        category_data = load_category_rules()
        logger.info("Connecting to Google Sheets...")
        client = GoogleSheetsClient()
        check_categories_alignment(client, category_data, verbose=True)
    else:
        process_files(force_reset=False)


if __name__ == "__main__":
    main()