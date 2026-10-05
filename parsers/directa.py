import csv
from io import StringIO
from pathlib import Path

import pandas as pd

from .base import BaseParser
from .utils import normalize_amount


class DirectaParser(BaseParser):
    """Parser implementation for Directa CSV exports."""

    BANK_LABEL = "Directa"

    def parse(self) -> pd.DataFrame:
        text = Path(self.filepath).read_text(encoding="utf-8-sig")
        lines = text.splitlines()

        header_index = None
        for idx, line in enumerate(lines):
            if "Data operazione" in line and "Tipo operazione" in line:
                header_index = idx
                break

        if header_index is None:
            raise ValueError("Unable to find the Directa header row in the CSV file.")

        header_line = lines[header_index].strip()
        data_lines = [line for line in lines[header_index + 1 :] if line.strip()]

        if not data_lines:
            raise ValueError("No Directa transaction rows were found in the CSV file.")

        reader = csv.reader(StringIO(header_line + "\n" + "\n".join(data_lines)), delimiter=";")
        rows = [row for row in reader if any(cell.strip() for cell in row)]

        if not rows:
            raise ValueError("No Directa rows could be parsed from the CSV file.")

        header = [self._clean_header(cell) for cell in rows[0]]
        normalized_rows = []

        for row in rows[1:]:
            if not row or not any(cell.strip() for cell in row):
                continue

            while len(row) < len(header):
                row.append("")
            if len(row) > len(header):
                row = row[: len(header)]

            normalized_rows.append({header[i]: row[i] for i in range(len(header))})

        if not normalized_rows:
            raise ValueError("No valid Directa transaction records were found.")

        df = pd.DataFrame(normalized_rows)
        df = df.rename(columns={
            "data operazione": "date",
            "data valuta": "value_date",
            "tipo operazione": "operation_type",
            "ticker": "ticker",
            "isin": "isin",
            "descrizione": "description",
            "quantità": "quantity",
            "importo euro": "amount_eur",
            "importo divisa": "amount_foreign",
            "divisa": "currency",
            "riferimento ordine": "order_reference",
        })

        required_columns = [
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
            "order_reference",
        ]
        for col in required_columns:
            if col not in df.columns:
                df[col] = ""

        df["date"] = pd.to_datetime(df["date"], format="%d-%m-%Y", errors="coerce")
        df["value_date"] = pd.to_datetime(df["value_date"], format="%d-%m-%Y", errors="coerce")

        df["date"] = df["date"].dt.strftime("%Y-%m-%d")
        df["value_date"] = df["value_date"].dt.strftime("%Y-%m-%d")

        df["description"] = df["description"].apply(self._clean_text)
        df["description"] = df.apply(lambda row: self._describe_row(row), axis=1)

        df["quantity"] = df["quantity"].apply(self._parse_quantity)
        df["amount_eur"] = df["amount_eur"].apply(self._parse_amount)
        df["amount_foreign"] = df["amount_foreign"].apply(self._parse_amount)
        df["currency"] = df["currency"].fillna("EUR").str.upper().replace({"": "EUR"})
        df["movement"] = df["operation_type"].apply(self._map_movement)

        result = df[
            [
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
        ].copy()

        result = result.dropna(subset=["date", "movement"]).reset_index(drop=True)
        return result

    @staticmethod
    def _clean_header(value: object) -> str:
        return str(value).strip().lower()

    @staticmethod
    def _clean_text(value: object) -> str:
        if value is None or pd.isna(value):
            return ""
        text = str(value).strip()
        if text.lower() in {"nan", "none", "null", ""}:
            return ""
        return text

    @classmethod
    def _describe_row(cls, row: pd.Series) -> str:
        description = cls._clean_text(row.get("description"))
        operation = cls._clean_text(row.get("operation_type"))
        ticker = cls._clean_text(row.get("ticker"))

        if description:
            return description
        if ticker:
            return f"{operation} {ticker}" if operation else ticker
        return operation or "Directa movement"

    @staticmethod
    def _parse_quantity(value: object) -> float:
        cleaned = str(value).strip().replace(".", "").replace(" ", "") if value is not None else "0"
        if cleaned in {"", "-", "--", "nan", "None"}:
            return 0.0
        cleaned = cleaned.replace(".", "").replace(",", ".")
        try:
            return float(cleaned)
        except ValueError:
            return 0.0

    @staticmethod
    def _parse_amount(value: object) -> float:
        if value is None or pd.isna(value):
            return 0.0
        text = str(value).strip()
        if not text or text.lower() in {"nan", "none", "null"}:
            return 0.0
        cleaned = text.replace("€", "").replace(" ", "")
        if "," in cleaned and "." in cleaned:
            if cleaned.rfind(",") > cleaned.rfind("."):
                cleaned = cleaned.replace(".", "").replace(",", ".")
            else:
                cleaned = cleaned.replace(",", "")
        elif "," in cleaned:
            cleaned = cleaned.replace(",", ".")
        try:
            return float(cleaned)
        except ValueError:
            return 0.0

    @staticmethod
    def _map_movement(operation_type: object) -> str:
        op = str(operation_type).strip().lower()
        if "acquisto" in op:
            return "BUY"
        if "vendita" in op:
            return "SELL"
        if "dividendo" in op or "cedola" in op:
            return "DIVIDEND"
        if "conferimento" in op or "bonifico" in op or "trasferimento" in op:
            return "CASH_TRANSFER"
        if "bollo" in op or "commission" in op or "fee" in op:
            return "FEE"
        return "OTHER"
