from io import BytesIO, StringIO

import pandas as pd

from categorization import categorize_transaction
from parsers import normalize_amount, parse_isybank, parse_trade_republic


def _trade_csv_buffer(rows: list[dict[str, str]]) -> StringIO:
    buffer = StringIO()
    pd.DataFrame(rows).to_csv(buffer, index=False)
    buffer.seek(0)
    return buffer


def _isybank_excel_buffer(rows: list[list[str]]) -> BytesIO:
    buffer = BytesIO()
    pd.DataFrame(rows).to_excel(buffer, index=False, header=False)
    buffer.seek(0)
    return buffer


def test_normalize_amount_handles_euro_string():
    assert normalize_amount("1.234,56 €") == 1234.56


def test_normalize_amount_preserves_decimal_precision_without_scaling():
    assert normalize_amount("12.345") == 12.345


def test_categorize_transaction_uses_specific_rules_first():
    category_data = {
        "rules": {
            "Ristoranti e Bar": ["STARBUCKS"],
            "Alimentari e Spesa": ["COOP"],
        },
        "default_income": "Varie",
        "default_expense": "Altro",
    }

    assert categorize_transaction("STARBUCKS TORINO", 10.0, category_data) == "Ristoranti e Bar"


def test_parse_trade_republic_returns_standard_columns():
    csv_buffer = _trade_csv_buffer(
        [
            {
                "datetime": "2026-07-23T10:00:00",
                "date": "2026-07-23",
                "account_type": "checking",
                "category": "buy",
                "type": "Buy",
                "asset_class": "",
                "name": "Example",
                "symbol": "",
                "shares": "",
                "price": "",
                "amount": "12.34",
                "fee": "0",
                "tax": "0",
                "currency": "EUR",
                "original_amount": "12.34",
                "original_currency": "EUR",
                "fx_rate": "1",
                "description": "Example transaction",
                "transaction_id": "id-1",
                "counterparty_name": "",
                "counterparty_iban": "",
                "payment_reference": "",
                "mcc_code": "",
            },
            {
                "datetime": "2026-07-24T10:00:00",
                "date": "2026-07-24",
                "account_type": "checking",
                "category": "summary",
                "type": "Summary",
                "asset_class": "",
                "name": "",
                "symbol": "",
                "shares": "",
                "price": "",
                "amount": "",
                "fee": "0",
                "tax": "0",
                "currency": "EUR",
                "original_amount": "",
                "original_currency": "EUR",
                "fx_rate": "1",
                "description": "",
                "transaction_id": "id-2",
                "counterparty_name": "",
                "counterparty_iban": "",
                "payment_reference": "",
                "mcc_code": "",
            },
        ]
    )

    df = parse_trade_republic(csv_buffer)

    assert list(df.columns) == ["date", "description", "amount"]
    assert len(df) == 1
    assert df.iloc[0]["description"] == "Example transaction"
    assert normalize_amount(df.iloc[0]["amount"]) == 12.34


def test_parse_trade_republic_strips_literal_null_suffix_from_description():
    csv_buffer = _trade_csv_buffer(
        [
            {
                "datetime": "2026-07-23T10:00:00",
                "date": "2026-07-23",
                "amount": "12.34",
                "description": "MCDONALD Snull",
            }
        ]
    )

    df = parse_trade_republic(csv_buffer)

    assert df.iloc[0]["description"] == "MCDONALD S"


def test_parse_trade_republic_includes_counterparty_name_in_description():
    csv_buffer = _trade_csv_buffer(
        [
            {
                "datetime": "2026-07-23T10:00:00",
                "date": "2026-07-23",
                "amount": "12.34",
                "name": "Example",
                "type": "Buy",
                "counterparty_name": "Merchant Srl",
            }
        ]
    )

    df = parse_trade_republic(csv_buffer)

    assert df.iloc[0]["description"] == "Buy - Example - Merchant Srl"


def test_parse_trade_republic_appends_full_name_when_description_is_truncated():
    csv_buffer = _trade_csv_buffer(
        [
            {
                "datetime": "2026-06-29T08:12:58.258723Z",
                "date": "2026-06-29",
                "account_type": "DEFAULT",
                "category": "CASH",
                "type": "CARD_TRANSACTION",
                "asset_class": "",
                "name": "GRUPPO TORINESE TRASPORTI",
                "symbol": "",
                "shares": "",
                "price": "",
                "amount": "-5.000000",
                "fee": "",
                "tax": "",
                "currency": "EUR",
                "original_amount": "",
                "original_currency": "",
                "fx_rate": "",
                "description": "GRUPPO TORINESE TRASPO",
                "transaction_id": "sdfsdferf3454354334ff4",
                "counterparty_name": "",
                "counterparty_iban": "",
                "payment_reference": "",
                "mcc_code": "8457",
            }
        ]
    )

    df = parse_trade_republic(csv_buffer)

    assert df.iloc[0]["description"] == "GRUPPO TORINESE TRASPO - GRUPPO TORINESE TRASPORTI"


def test_parse_trade_republic_keeps_existing_description_and_appends_only_missing_context():
    csv_buffer = _trade_csv_buffer(
        [
            {
                "datetime": "2026-07-23T10:00:00",
                "date": "2026-07-23",
                "account_type": "checking",
                "category": "buy",
                "type": "Buy",
                "asset_class": "",
                "name": "Example",
                "symbol": "",
                "shares": "",
                "price": "",
                "amount": "12.34",
                "fee": "0",
                "tax": "0",
                "currency": "EUR",
                "original_amount": "12.34",
                "original_currency": "EUR",
                "fx_rate": "1",
                "description": "Example transaction",
                "transaction_id": "id-1",
                "counterparty_name": "Merchant Srl",
                "counterparty_iban": "",
                "payment_reference": "",
                "mcc_code": "",
            }
        ]
    )

    df = parse_trade_republic(csv_buffer)

    assert df.iloc[0]["description"] == "Example transaction - Merchant Srl"


def test_parse_trade_republic_ignores_fake_empty_counterparty_values():
    csv_buffer = _trade_csv_buffer(
        [
            {
                "datetime": "2026-07-23T10:00:00",
                "date": "2026-07-23",
                "account_type": "checking",
                "category": "buy",
                "type": "Buy",
                "asset_class": "",
                "name": "Example",
                "symbol": "",
                "shares": "",
                "price": "",
                "amount": "12.34",
                "fee": "0",
                "tax": "0",
                "currency": "EUR",
                "original_amount": "12.34",
                "original_currency": "EUR",
                "fx_rate": "1",
                "description": "Example transaction",
                "transaction_id": "id-1",
                "counterparty_name": "null",
                "counterparty_iban": "",
                "payment_reference": "",
                "mcc_code": "",
            }
        ]
    )

    df = parse_trade_republic(csv_buffer)

    assert df.iloc[0]["description"] == "Example transaction"


def test_parse_trade_republic_falls_back_to_counterparty_when_description_is_missing():
    csv_buffer = _trade_csv_buffer(
        [
            {
                "datetime": "2026-07-23T10:00:00",
                "date": "2026-07-23",
                "account_type": "checking",
                "category": "buy",
                "type": "Buy",
                "asset_class": "",
                "name": "",
                "symbol": "",
                "shares": "",
                "price": "",
                "amount": "12.34",
                "fee": "0",
                "tax": "0",
                "currency": "EUR",
                "original_amount": "12.34",
                "original_currency": "EUR",
                "fx_rate": "1",
                "description": "",
                "transaction_id": "id-1",
                "counterparty_name": "Merchant Srl",
                "counterparty_iban": "",
                "payment_reference": "",
                "mcc_code": "",
            }
        ]
    )

    df = parse_trade_republic(csv_buffer)

    assert df.iloc[0]["description"] == "Merchant Srl"


def test_parse_isybank_uses_fixed_header_layout():
    xlsx_buffer = _isybank_excel_buffer(
        [
            ["skip"] * 8,
            ["skip"] * 8,
            ["skip"] * 8,
            ["skip"] * 8,
            ["skip"] * 8,
            ["skip"] * 8,
            ["skip"] * 8,
            ["skip"] * 8,
            ["skip"] * 8,
            ["skip"] * 8,
            ["skip"] * 8,
            ["skip"] * 8,
            ["skip"] * 8,
            ["skip"] * 8,
            ["skip"] * 8,
            ["skip"] * 8,
            ["skip"] * 8,
            [" Data ", "Operation", "Dettagli ", "Conto", "Contabilizzazione", "Categoria", "Valuta", "Importo"],
            ["2026-07-23 10:30:00", "Pagamento", "PIZZA", "Conto 1", "2026-07-23", "Ristoranti e Bar", "EUR", "-12.34"],
            ["2026-07-24", "Sintesi", "Questo riepilogo contiene troppo testo e informazioni aggiuntive ", "Conto 1", "2026-07-24", "Sintesi", "EUR", "-100.00"],
        ]
    )

    parsed = parse_isybank(xlsx_buffer)

    assert list(parsed.columns) == ["date", "description", "amount"]
    assert len(parsed) == 2
    assert parsed.iloc[0]["date"] == "2026-07-23"
    assert parsed.iloc[0]["description"] == "Pagamento"
    assert normalize_amount(parsed.iloc[0]["amount"]) == -12.34
    assert parsed.iloc[1]["description"] == "Sintesi"
    assert normalize_amount(parsed.iloc[1]["amount"]) == -100.00
