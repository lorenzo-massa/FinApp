import logging

import gspread

from categorization import TransactionCategorizer
from settings import CREDENTIALS_FILE, SPREADSHEET_NAME, WORKSHEET_DIRECTA, WORKSHEET_TRANSACTIONS

logger = logging.getLogger(__name__)

SheetCell = str | int | float | bool | None
SheetRow = list[SheetCell]

# Global constants for sheet headers
HEADER_ID = "id"
HEADER_DATE = "date"
HEADER_ACCOUNT = "account"
HEADER_CATEGORY = "category"
HEADER_AMOUNT = "amount"
HEADER_DESCRIPTION = "description"
HEADER_YEAR_MONTH = "year-month"
HEADER_MANUAL = "manual"

STANDARD_HEADERS = [
    HEADER_ID,
    HEADER_DATE,
    HEADER_ACCOUNT,
    HEADER_CATEGORY,
    HEADER_AMOUNT,
    HEADER_DESCRIPTION,
    HEADER_YEAR_MONTH,
    HEADER_MANUAL,
]

DIRECTA_HEADERS = [
    "Id",
    "Date",
    "Value_date",
    "Operation_type",
    "Ticker",
    "Isin",
    "Description",
    "Quantity",
    "Amount_eur",
    "Amount_foreign",
    "Currency",
    "Movement",
    "Order_reference",
]

MANDATORY_HEADERS = [HEADER_CATEGORY, HEADER_AMOUNT, HEADER_DESCRIPTION, HEADER_MANUAL]


def _col_to_letter(col_idx: int) -> str:
    """Convert a 0-based index to an Excel column letter (0 -> 'A', 3 -> 'D')."""
    return chr(65 + col_idx)


class GoogleSheetsClient:
    """OOP client to manage interaction with the Google Transactions sheet."""

    def __init__(self) -> None:
        spreadsheet = self.connect_to_sheets()
        self.spreadsheet = spreadsheet
        self.sheet = self.get_transaction_sheet(spreadsheet)
        self.directa_sheet = self.get_directa_sheet(spreadsheet)

    def clear(self) -> None:
        """Clear the worksheet keeping only the header row."""
        all_values = self.sheet.get_all_values()
        if not all_values:
            return

        headers = all_values[0]
        self.sheet.clear()
        self.sheet.append_row(headers)

    def get_hashes(self, worksheet: gspread.Worksheet | None = None) -> list[str]:
        target_sheet = worksheet if worksheet is not None else self.sheet
        return target_sheet.col_values(1)[1:]

    @staticmethod
    def _is_manual_entry(raw_manual: str | bool | None) -> bool:
        """Normalize Google Sheets checkbox values to a boolean."""
        if isinstance(raw_manual, str):
            return raw_manual.strip().upper() == "TRUE"
        return bool(raw_manual)

    def get_manual_overrides(self) -> dict[str, str]:
        """Return a mapping of transaction hash to saved manual category."""
        all_values: list[SheetRow] = self.sheet.get_all_values()
        if not all_values or len(all_values) <= 1:
            return {}

        headers = [str(h).strip().lower() for h in all_values[0]]

        try:
            col_id = headers.index(HEADER_ID)
            col_category = headers.index(HEADER_CATEGORY)
            col_manual = headers.index(HEADER_MANUAL)
        except ValueError:
            return {}

        manual_overrides: dict[str, str] = {}
        for row in all_values[1:]:

            if not self._is_manual_entry(row[col_manual]):
                continue

            transaction_id = str(row[col_id]).strip()
            category = str(row[col_category]).strip()
            if transaction_id and category:
                manual_overrides[transaction_id] = category

        return manual_overrides

    def append_rows(
        self,
        rows: list[SheetRow],
        worksheet: gspread.Worksheet | None = None,
    ) -> None:
        target_sheet = worksheet if worksheet is not None else self.sheet
        target_sheet.append_rows(rows)

    def recategorize_existing(
        self,
        categorizer: TransactionCategorizer,
    ) -> int:
        """Recategorize non-manual rows preserving user edits and return the number of truly updated rows."""
        all_values: list[SheetRow] = self.sheet.get_all_values()
        if not all_values or len(all_values) <= 1:
            return 0

        headers = [str(h).strip().lower() for h in all_values[0]]

        try:
            col_category = headers.index(HEADER_CATEGORY)
            col_amount = headers.index(HEADER_AMOUNT)
            col_description = headers.index(HEADER_DESCRIPTION)
            col_manual = headers.index(HEADER_MANUAL)
        except ValueError as err:
            raise ValueError(
                f"Required header missing in Google Sheet: {err}"
            ) from err

        data_rows = all_values[1:]
        updated_categories: list[list[str]] = []
        updated_count = 0
        processed_rows = 0
        skipped_manual_rows = 0

        for row in data_rows:
            current_category = (
                row[col_category] if col_category < len(row) else ""
            )

            raw_manual = row[col_manual] if col_manual < len(row) else False
            if self._is_manual_entry(raw_manual):
                skipped_manual_rows += 1
                updated_categories.append([current_category])
                continue

            description = (
                row[col_description] if col_description < len(row) else ""
            )
            raw_amount = row[col_amount] if col_amount < len(row) else "0"

            amount = self._parse_amount_safely(raw_amount)
            new_category = categorizer.categorize(description, amount)
            processed_rows += 1

            if new_category != current_category:
                updated_count += 1

            updated_categories.append([new_category])

        if not updated_categories:
            logger.info("No rows were available to recategorize.")
            return 0

        logger.info(
            "Processed %s rows for recategorization; skipped %s manual rows; updated %s rows.",
            processed_rows,
            skipped_manual_rows,
            updated_count,
        )

        start_row = 2
        end_row = start_row + len(updated_categories) - 1

        col_letter = _col_to_letter(col_category)
        range_label = f"{col_letter}{start_row}:{col_letter}{end_row}"

        self.sheet.update(range_label, updated_categories)
        
        return updated_count
    
    @staticmethod
    def _parse_amount_safely(raw_amount: object) -> float:
        """Helper to parse amount values robustly from sheet cells."""
        if raw_amount is None:
            return 0.0
        text = str(raw_amount).strip()
        if not text:
            return 0.0
        
        cleaned = text.replace("€", "").replace("$", "").replace(" ", "")
        if "," in cleaned and "." in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", ".")

        try:
            return float(cleaned)
        except ValueError:
            return 0.0

    def connect_to_sheets(self) -> gspread.Spreadsheet:
        """Open and return the Google Spreadsheet searching by NAME using CREDENTIALS_FILE."""
        gc = gspread.service_account(filename=CREDENTIALS_FILE)
        return gc.open(SPREADSHEET_NAME)


    def get_transaction_sheet(self, spreadsheet: gspread.Spreadsheet) -> gspread.Worksheet:
        """Return the existing Transactions worksheet."""
        return spreadsheet.worksheet(WORKSHEET_TRANSACTIONS)

    def get_directa_sheet(self, spreadsheet: gspread.Spreadsheet) -> gspread.Worksheet:
        """Return the existing Investments operations worksheet."""
        return spreadsheet.worksheet(WORKSHEET_DIRECTA)






