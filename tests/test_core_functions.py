import pandas as pd
import pytest
import json
import csv
from io import BytesIO, StringIO
from unittest.mock import MagicMock, patch

from categorization import (
    TransactionCategorizer,
    load_category_rules,
    DEFAULT_INCOME_LABEL,
    DEFAULT_EXPENSE_LABEL,
)
from google_sheets import (
    GoogleSheetsClient,
    STANDARD_HEADERS,
)
from parsers import DirectaParser, IsybankParser, TradeRepublicParser
from parsers.utils import normalize_amount


# ==========================================
# Core Utility Functions
# ==========================================

class MockBufferFactory:
    """Factory to generate in-memory files for testing."""
    
    @staticmethod
    def create_csv(data: list[dict]) -> StringIO:
        buffer = StringIO()
        pd.DataFrame(data).to_csv(buffer, index=False)
        buffer.seek(0)
        return buffer

    @staticmethod
    def create_excel(data: list[list]) -> BytesIO:
        buffer = BytesIO()
        pd.DataFrame(data).to_excel(buffer, index=False, header=False)
        buffer.seek(0)
        return buffer


# ==========================================
# Base Parser Test Class
# ==========================================

class BaseParserTest:
    """Base test class providing common test structure and mocking interface for all parsers."""
    
    parser_class = None
    expected_columns = ["date", "description", "amount"]

    def _create_buffer(self, data: list[dict]):
        """Convert a list of dictionaries into the appropriate file buffer (CSV/Excel)."""
        raise NotImplementedError("Subclasses must implement _create_buffer")

    def _parse_data(self, data: list[dict], tmp_path):
        return self.parser_class(self._create_buffer(data)).parse()

    def _get_standard_data(self) -> list[dict]:
        """Return standard valid mock data specific to the parser."""
        raise NotImplementedError("Subclasses must implement _get_standard_data")

    # --- Common Tests for all parsers ---

    def test_returns_expected_columns(self, tmp_path):
        """Each parser returns its normalized output columns in a stable order."""
        df = self._parse_data(self._get_standard_data(), tmp_path)
        
        assert list(df.columns) == self.expected_columns

    def test_raises_error_on_completely_invalid_data(self, tmp_path):
        """All parsers should fail gracefully when essential columns are missing."""
        with pytest.raises((ValueError, KeyError)):
            self._parse_data(
                [{"random_column": "123", "another_column": "456"}],
                tmp_path,
            )


# ==========================================
# Specific Parser Tests
# ==========================================

class TestTradeRepublicParser(BaseParserTest):
    """Specific tests for the Trade Republic CSV Parser."""
    
    parser_class = TradeRepublicParser

    def _create_buffer(self, data: list[dict]) -> StringIO:
        # Trade Republic directly uses standard CSV format
        return MockBufferFactory.create_csv(data)

    def _get_standard_data(self) -> list[dict]:
        return [
            {
                "datetime": "2026-07-23T10:00:00",
                "date": "2026-07-23",
                "account_type": "checking",
                "category": "buy",
                "type": "Buy",
                "amount": "12.34",
                "description": "Synthetic test transaction",
                "name": "Fixture Example",
                "counterparty_name": "",
                "currency": "EUR"
            }
        ]

    def test_parses_standard_row_values(self):
        buffer = self._create_buffer(self._get_standard_data())
        df = self.parser_class(buffer).parse()

        assert len(df) == 1
        assert df.iloc[0]["description"] == "Synthetic test transaction - Fixture Example"
        assert normalize_amount(df.iloc[0]["amount"]) == 12.34

    def test_strips_literal_null_suffix_from_description(self):
        buffer = self._create_buffer([
            {"date": "2026-07-23", "amount": "12.34", "description": "MCDONALD Snull"}
        ])
        df = self.parser_class(buffer).parse()
        assert df.iloc[0]["description"] == "MCDONALD S"

    def test_includes_counterparty_name_in_description(self):
        buffer = self._create_buffer([
            {
                "date": "2026-07-23", 
                "amount": "12.34", 
                "name": "Fixture Example", 
                "type": "Buy", 
                "counterparty_name": "Fixture Merchant"
            }
        ])
        df = self.parser_class(buffer).parse()
        assert df.iloc[0]["description"] == "Buy - Fixture Example - Fixture Merchant"

    def test_appends_full_name_when_description_is_truncated(self):
        buffer = self._create_buffer([
            {
                "date": "2026-06-29",
                "amount": "-5.000000",
                "name": "TEST MERCHANT HOLDINGS",
                "description": "TEST MERCHANT HOLD",
            }
        ])
        df = self.parser_class(buffer).parse()
        assert df.iloc[0]["description"] == "TEST MERCHANT HOLD - TEST MERCHANT HOLDINGS"

    def test_keeps_existing_description_and_appends_only_missing_context(self):
        buffer = self._create_buffer([
            {
                "date": "2026-07-23",
                "amount": "12.34",
                "description": "Synthetic test transaction",
                "counterparty_name": "Fixture Merchant",
            }
        ])
        df = self.parser_class(buffer).parse()
        assert df.iloc[0]["description"] == "Synthetic test transaction - Fixture Merchant"

    def test_ignores_fake_empty_counterparty_values(self):
        buffer = self._create_buffer([
            {
                "date": "2026-07-23",
                "amount": "12.34",
                "description": "Synthetic test transaction",
                "counterparty_name": "null",
            }
        ])
        df = self.parser_class(buffer).parse()
        assert df.iloc[0]["description"] == "Synthetic test transaction"

    def test_falls_back_to_counterparty_when_description_is_missing(self):
        buffer = self._create_buffer([
            {
                "date": "2026-07-23",
                "amount": "12.34",
                "description": "",
                "counterparty_name": "Fixture Merchant",
            }
        ])
        df = self.parser_class(buffer).parse()
        assert df.iloc[0]["description"] == "Fixture Merchant"

    def test_raises_value_error_on_missing_columns(self):
        buffer = self._create_buffer([{"random_column": "123", "description": "No date or amount"}])
        with pytest.raises(ValueError, match="Unable to find 'date' or 'amount' columns"):
            self.parser_class(buffer).parse()

    def test_raises_error_when_all_text_fields_are_empty(self):
        buffer = self._create_buffer([
            {"date": "2026-07-23", "amount": "15.00", "description": "null", "name": "None", "counterparty_name": ""}
        ])
        with pytest.raises(ValueError, match="Transaction found without any descriptive text"):
            self.parser_class(buffer).parse()

    def test_parse_trade_republic_fallback_description_without_description_column(self):
        """Verify that the parser correctly falls back to type, name, and counterparty when the 'description' column is absent."""
        buffer = self._create_buffer(
            [
                {
                    "date": "2026-07-23",
                    "amount": "50.00",
                    "type": "SAVINGS_PLAN",
                    "name": "Fixture ETF",
                    "counterparty_name": "Synthetic Broker",
                    # Note: no 'description' column provided at all
                }
            ]
        )

        df = self.parser_class(buffer).parse()

        assert len(df) == 1
        assert df.iloc[0]["description"] == "SAVINGS_PLAN - Fixture ETF - Synthetic Broker"


class TestDirectaParser(BaseParserTest):
    """Specific tests for the Directa CSV parser."""

    parser_class = DirectaParser
    expected_columns = [
        "date",
        "value_date",
        "operation_type",
        "ticker",
        "isin",
        "description",
        "quantity",
        "amount_eur",
        "amount_foreign",
        "currency",
        "movement",
        "order_reference",
    ]

    def _get_standard_data(self) -> list[dict]:
        return [
            {
                "Data operazione": "11-11-2026",
                "Data valuta": "12-11-2026",
                "Tipo operazione": "Acquisto",
                "Ticker": "FAKE1",
                "Isin": "IT0000000001",
                "Protocollo": "",
                "Descrizione": "Synthetic equity sample position",
                "Quantità": "1",
                "Importo euro": "-39,64",
                "Importo Divisa": "0",
                "Divisa": "EUR",
                "Riferimento ordine": "FAKE-ORDER-001",
            },
            {
                "Data operazione": "18-08-2026",
                "Data valuta": "18-08-2026",
                "Tipo operazione": "Conferimento con bonifico",
                "Ticker": "",
                "Isin": "",
                "Protocollo": "FAKE-PROTOCOL-002",
                "Descrizione": "",
                "Quantità": "0",
                "Importo euro": "280",
                "Importo Divisa": "0",
                "Divisa": "EUR",
                "Riferimento ordine": "",
            },
        ]

    def _parse_data(self, data: list[dict], tmp_path):
        csv_path = tmp_path / "directa_sample.csv"
        buffer = StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(data[0]), delimiter=";")
        writer.writeheader()
        writer.writerows(data)
        csv_path.write_text(
            "\n".join(
                [
                    "Conto : P0000 YYYYY XXXXXXXX;;;;;;;;;;;",
                    "Data estrazione : 4-10-2026 15:50:29;;;;;;;;;;;",
                    ";;;;;;;;;;;",
                    "Tutti i movimenti ordinati per Data Operazione;;;;;;;;;;;",
                    buffer.getvalue().rstrip(),
                ]
            ),
            encoding="utf-8",
        )
        return self.parser_class(csv_path).parse()

    def test_parses_directa_investment_rows(self, tmp_path):
        df = self._parse_data(self._get_standard_data(), tmp_path)

        assert df.iloc[0]["movement"] == "BUY"
        assert df.iloc[0]["ticker"] == "FAKE1"
        assert df.iloc[0]["quantity"] == 1.0
        assert df.iloc[0]["amount_eur"] == -39.64
        assert df.iloc[1]["movement"] == "CASH_TRANSFER"
        assert df.iloc[1]["amount_eur"] == 280.0


class TestIsybankParser(BaseParserTest):
    """Specific tests for the Isybank Excel Parser."""
    
    parser_class = IsybankParser

    def _create_buffer(self, data: list[dict]) -> BytesIO:
        # Isybank expects an Excel file with 17 initial skipped rows, followed by headers
        if not data:
            return MockBufferFactory.create_excel([])
        
        headers = list(data[0].keys())
        rows = [[row.get(h, "") for h in headers] for row in data]
        
        # Simulate the 17 useless rows generated by the bank
        skips = [["skip"] * len(headers)] * 17
        full_data = skips + [headers] + rows
        
        return MockBufferFactory.create_excel(full_data)

    def _get_standard_data(self) -> list[dict]:
        return [
            {
                "Data": "2026-07-23 10:30:00",
                "Operazione": "Pagamento",
                "Dettagli": "SAMPLE PURCHASE",
                "Importo": "-12.34"
            }
        ]

    def test_parses_standard_row_values(self):
        """Test standard behavior with the real Isybank column names."""
        buffer = self._create_buffer(self._get_standard_data())
        df = self.parser_class(buffer).parse()

        assert len(df) == 1
        assert df.iloc[0]["date"] == "2026-07-23"
        assert df.iloc[0]["description"] == "Pagamento"
        assert normalize_amount(df.iloc[0]["amount"]) == -12.34

    def test_bonifico_uses_detail_suffix_after_disposto(self):
        """Bonifico rows should append the text after 'disposto' from the Dettagli column."""
        buffer = self._create_buffer([
            {"Data": "2026-07-22", "Operazione": "Bonifico", "Dettagli": "Conto corrente disposto a Sample Client", "Importo": "+100.00"}
        ])
        df = self.parser_class(buffer).parse()

        assert df.iloc[0]["description"] == "Bonifico a Sample Client"

    def test_raises_keyerror_on_missing_mandatory_columns(self):
        """Verify that a KeyError is raised when any required Isybank column is missing."""
        buffer = self._create_buffer([
            {"Data": "2026-07-01", "Importo": "-10.00"}
        ])
        with pytest.raises(KeyError, match="Mandatory column 'Operazione'"):
            self.parser_class(buffer).parse()

    def test_handles_dirty_dates_and_missing_values(self):
        """Verifies cleaning of times in dates and handling of empty/NaN values in the real Isybank schema."""
        buffer = self._create_buffer([
            {"Data": "2026-01-15T18:45:00", "Operazione": None, "Dettagli": "", "Importo": "-10.00"},
            {"Data": "2026-02-20 00:00:00", "Operazione": "  Caffè  ", "Dettagli": "", "Importo": "-1.20"}
        ])
        df = self.parser_class(buffer).parse()

        assert df.iloc[0]["date"] == "2026-01-15"
        assert df.iloc[1]["date"] == "2026-02-20"
        assert df.iloc[0]["description"] == ""
        assert df.iloc[1]["description"] == "Caffè"

    def test_drops_rows_with_invalid_or_missing_dates(self):
        """Verify that rows with unparseable or missing dates are automatically dropped."""
        buffer = self._create_buffer([
            {"Data": "2026-07-23", "Operazione": "Valid Row", "Dettagli": "", "Importo": "-10.00"},
            {"Data": "Invalid Date", "Operazione": "Summary Row", "Dettagli": "", "Importo": "-100.00"},
            {"Operazione": "Missing Date Row", "Dettagli": "", "Importo": "-5.00"}
        ])
        df = self.parser_class(buffer).parse()

        assert len(df) == 1
        assert df.iloc[0]["description"] == "Valid Row"


# ==========================================
# Other Generic Tests
# ==========================================

class TestNormalizeAmount:
    def test_handles_euro_string(self):
        assert normalize_amount("1.234,56 €") == 1234.56

    def test_preserves_decimal_precision_without_scaling(self):
        assert normalize_amount("12.345") == 12.345

class TestTransactionCategorizer:
    """Test suite for transaction categorization and rules loading."""

    def test_categorize_uses_specific_rules_first(self):
        """Verify that specific keyword rules take precedence over amount-based fallbacks."""
        category_data = {
            "rules": {
                "Ristoranti e Bar": ["STARBUCKS"],
                "Alimentari e Spesa": ["COOP"],
            },
            "default_income": DEFAULT_INCOME_LABEL,
            "default_expense": DEFAULT_EXPENSE_LABEL,
        }
        categorizer = TransactionCategorizer(category_data)

        assert categorizer.categorize("STARBUCKS TORINO", -10.0) == "Ristoranti e Bar"

    def test_categorize_fallback_to_default_income_on_positive_amount(self):
        """Verify fallback to default income category when no rule matches and amount is positive."""
        category_data = {
            "rules": {"Alimentari": ["COOP"]},
            "default_income": "Stipendio",
            "default_expense": DEFAULT_EXPENSE_LABEL,
        }
        categorizer = TransactionCategorizer(category_data)

        assert categorizer.categorize("RIMBORSO SCONOSCIUTO", 150.0) == "Stipendio"

    def test_categorize_fallback_to_default_expense_on_negative_amount(self):
        """Verify fallback to default expense category when no rule matches and amount is negative."""
        category_data = {
            "rules": {"Alimentari": ["COOP"]},
            "default_income": DEFAULT_INCOME_LABEL,
            "default_expense": "Spese Varie",
        }
        categorizer = TransactionCategorizer(category_data)

        assert categorizer.categorize("PAGAMENTO GENERICO", -25.50) == "Spese Varie"

    def test_load_category_rules_returns_defaults_when_file_missing(self, tmp_path):
        """Verify that default configurations are returned if the JSON category file does not exist."""
        non_existent_file = tmp_path / "missing_categories.json"
        config = load_category_rules(non_existent_file)

        assert config["rules"] == {}
        assert config["default_income"] == DEFAULT_INCOME_LABEL
        assert config["default_expense"] == DEFAULT_EXPENSE_LABEL

    def test_load_category_rules_successfully_reads_json(self, tmp_path):
        """Verify successful loading and parsing of rules from a valid JSON file."""
        categories_file = tmp_path / "categories.json"
        sample_data = {
            "rules": {"Tech": ["AMAZON"]},
            "default_income": "Income",
            "default_expense": "Expense",
        }
        categories_file.write_text(json.dumps(sample_data), encoding="utf-8")

        config = load_category_rules(categories_file)
        assert config == sample_data

class TestGoogleSheetsClient:
    """Test suite for GoogleSheetsClient operations and safeguards."""

    def test_recategorize_existing_preserves_manual_overrides(self):
        """Verify that native boolean checkboxes from Google Sheets are correctly recognized to preserve overrides."""
        row_auto = [
            "hash1",
            "2026-01-10",
            "Isybank",
            "Other",
            "-50.00",
            "SUPERMARKET SPEND",
            "2026-01",
            False,
        ]
        row_manual = [
            "hash2",
            "2026-01-11",
            "Isybank",
            "Custom Expense",
            "-50.00",
            "SUPERMARKET SPEND",
            "2026-01",
            True,
        ]

        mock_sheet = MagicMock()
        mock_sheet.get_all_values.return_value = [STANDARD_HEADERS, row_auto, row_manual]

        category_data = {
            "rules": {"Groceries": ["SUPERMARKET"]},
            "default_expense": "Other",
            "default_income": "General Income",
        }
        categorizer = TransactionCategorizer(category_data)
        
        with patch.object(GoogleSheetsClient, "__init__", lambda self: setattr(self, 'sheet', mock_sheet)):
            client = GoogleSheetsClient()

        client.recategorize_existing(categorizer)

        mock_sheet.update.assert_called_once()
        updated_values = mock_sheet.update.call_args[0][1]

        # Automatic row (False) is updated, manual row (True) is preserved
        assert updated_values == [["Groceries"], ["Custom Expense"]]

    def test_recategorize_existing_handles_amounts_with_currency_symbols(self):
        """Verify that amounts containing currency symbols or commas are safely parsed for categorization sign."""
        row_currency = [
            "hash1",
            "2026-01-10",
            "Isybank",
            "Other",
            "+1.250,50 €",
            "UNKNOWN REFUND",
            "2026-01",
            False,
        ]

        mock_sheet = MagicMock()
        mock_sheet.get_all_values.return_value = [STANDARD_HEADERS, row_currency]

        category_data = {
            "rules": {},
            "default_expense": "Other",
            "default_income": "Salary & Refunds",
        }
        categorizer = TransactionCategorizer(category_data)
        
        with patch.object(GoogleSheetsClient, "__init__", lambda self: setattr(self, 'sheet', mock_sheet)):
            client = GoogleSheetsClient()

        client.recategorize_existing(categorizer)

        updated_values = mock_sheet.update.call_args[0][1]
        # Positive amount should trigger default_income fallback
        assert updated_values == [["Salary & Refunds"]]

    def test_recategorize_existing_does_nothing_on_empty_or_header_only_sheet(self):
        """Verify that recategorization safely returns if the sheet has no rows or only headers."""
        mock_sheet = MagicMock()
        mock_sheet.get_all_values.return_value = [STANDARD_HEADERS]

        categorizer = TransactionCategorizer({})
        
        with patch.object(GoogleSheetsClient, "__init__", lambda self: setattr(self, 'sheet', mock_sheet)):
            client = GoogleSheetsClient()

        client.recategorize_existing(categorizer)
        mock_sheet.update.assert_not_called()

    def test_recategorize_existing_raises_value_error_on_missing_headers(self):
        """Verify that a ValueError is raised if mandatory columns are missing from headers."""
        bad_headers = ["id", "date"]  # Missing mandatory headers like category, amount, etc.
        mock_sheet = MagicMock()
        mock_sheet.get_all_values.return_value = [bad_headers, ["1", "2026-01-01"]]

        categorizer = TransactionCategorizer({})
        
        with patch.object(GoogleSheetsClient, "__init__", lambda self: setattr(self, 'sheet', mock_sheet)):
            client = GoogleSheetsClient()

        with pytest.raises(ValueError, match="Required header missing"):
            client.recategorize_existing(categorizer)

    def test_clear_sheet_resets_and_keeps_headers(self):
        """Verify that clearing the sheet empties all records but preserves the header row."""
        row_data = ["hash1", "2026-01-10", "Isybank", "Other", "-50.00", "TEST", "2026-01", False]
        mock_sheet = MagicMock()
        mock_sheet.get_all_values.return_value = [STANDARD_HEADERS, row_data]

        with patch.object(GoogleSheetsClient, "__init__", lambda self: setattr(self, 'sheet', mock_sheet)):
            client = GoogleSheetsClient()
            
        client.clear()

        mock_sheet.clear.assert_called_once()
        mock_sheet.append_row.assert_called_once_with(STANDARD_HEADERS)

    def test_clear_sheet_does_nothing_if_empty(self):
        """Verify that clearing an already empty sheet does nothing."""
        mock_sheet = MagicMock()
        mock_sheet.get_all_values.return_value = []

        with patch.object(GoogleSheetsClient, "__init__", lambda self: setattr(self, 'sheet', mock_sheet)):
            client = GoogleSheetsClient()
            
        client.clear()

        mock_sheet.clear.assert_not_called()
        mock_sheet.append_row.assert_not_called()

    def test_get_manual_overrides_returns_hash_to_category_map(self):
        """Manual rows should be snapshotted by hash so the reset can restore them later."""
        row_auto = [
            "hash1",
            "2026-01-10",
            "Isybank",
            "Other",
            "-50.00",
            "SUPERMARKET SPEND",
            "2026-01",
            False,
        ]
        row_manual = [
            "hash2",
            "2026-01-11",
            "Isybank",
            "Custom Expense",
            "-50.00",
            "SUPERMARKET SPEND",
            "2026-01",
            True,
        ]

        mock_sheet = MagicMock()
        mock_sheet.get_all_values.return_value = [STANDARD_HEADERS, row_auto, row_manual]

        with patch.object(GoogleSheetsClient, "__init__", lambda self: setattr(self, 'sheet', mock_sheet)):
            client = GoogleSheetsClient()

        assert client.get_manual_overrides() == {"hash2": "Custom Expense"}

