import logging
from typing import Any

import gspread
from google.oauth2.service_account import Credentials

from settings import CREDENTIALS_FILE, SCOPES, SPREADSHEET_NAME, WORKSHEET_CATEGORIES, WORKSHEET_TRANSACTIONS

logger = logging.getLogger(__name__)


def connect_to_sheets() -> Any:
    """Open the connection to Google Sheets via a service account."""
    if not CREDENTIALS_FILE.exists():
        raise FileNotFoundError(
            f"Unable to find the credentials file {CREDENTIALS_FILE.name}"
        )

    creds = Credentials.from_service_account_file(
        CREDENTIALS_FILE,
        scopes=SCOPES,
    )
    client = gspread.authorize(creds)
    return client.open(SPREADSHEET_NAME)


def sync_categories_to_sheet(spreadsheet: Any, category_data: dict[str, Any]) -> None:
    """Update the configured categories sheet while preserving the option schema."""
    try:
        sheet_cat = spreadsheet.worksheet(WORKSHEET_CATEGORIES)
        category_rows = [["Category"], ["-"]]

        for category in category_data.get("rules", {}).keys():
            category_rows.append([category])

        category_rows.append([category_data.get("default_income", "Entrate Varie")])
        category_rows.append([category_data.get("default_expense", "Altro")])

        sheet_cat.clear()
        sheet_cat.update("A1", category_rows)
        logger.info(f"'{WORKSHEET_CATEGORIES}' sheet synced successfully.")
    except Exception as exc:
        logger.warning(f"Error while syncing the '{WORKSHEET_CATEGORIES}' sheet: %s", exc)


def get_sheet_column_index(headers: list[str], target: str) -> int:
    """Return the requested column index with a safe fallback."""
    normalized_headers = [str(header).strip().lower() for header in headers]
    try:
        return normalized_headers.index(target.lower())
    except ValueError:
        return {
            "categoria": 3,
            "importo": 4,
            "descrizione": 5,
        }.get(target.lower(), 0)


def recategorize_existing(sheet: Any, category_data: dict[str, Any], categorize_fn) -> None:
    """Read transactions from the sheet and update only the modified categories."""
    logger.info("Reading existing transactions from Google Sheets...")
    all_data = sheet.get_all_values()

    if len(all_data) <= 1:
        logger.info("No transactions available to update.")
        return

    headers = all_data[0]
    rows = all_data[1:]
    cat_col_idx = get_sheet_column_index(headers, "Categoria")
    amount_col_idx = get_sheet_column_index(headers, "Importo")
    desc_col_idx = get_sheet_column_index(headers, "Descrizione")

    updated_categories: list[list[str]] = []
    modified_count = 0

    for row in rows:
        old_category = row[cat_col_idx].strip() if len(row) > cat_col_idx else ""
        description = row[desc_col_idx] if len(row) > desc_col_idx else ""

        try:
            amount = float(row[amount_col_idx].replace(",", ".").replace("€", ""))
        except (IndexError, ValueError):
            amount = 0.0

        new_category = categorize_fn(description, amount, category_data)
        updated_categories.append([new_category])

        if old_category != new_category:
            modified_count += 1

    sheet.update(f"D2:D{len(updated_categories) + 1}", updated_categories)

    if modified_count > 0:
        logger.info(
            "Update complete! %s categories were actually changed across %s total transactions.",
            modified_count,
            len(rows),
        )
    else:
        logger.info(
            "Analyzed %s transactions: no category changes were required.",
            len(rows),
        )


def clear_transactions_sheet(sheet: Any) -> None:
    """Clear the sheet content while keeping only the header row."""
    logger.info("Clearing in progress...")
    headers = [["ID", "Date", "Account", "Category", "Amount", "Description", "Year-Month"]]
    sheet.clear()
    sheet.update("A1", headers)
    logger.info(f"'{WORKSHEET_TRANSACTIONS}' sheet reset successfully!")


def get_transaction_sheet(spreadsheet: Any) -> Any:
    return spreadsheet.worksheet(WORKSHEET_TRANSACTIONS)
