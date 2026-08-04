import re
from typing import Any

import pandas as pd

from .base import BaseParser
from .utils import normalize_amount, STANDARD_COLUMNS, COL_DATE, COL_DESCRIPTION, COL_AMOUNT


class TradeRepublicParser(BaseParser):
    """Parser implementation for Trade Republic CSV files."""

    BANK_LABEL = "Trade Republic"

    def parse(self) -> pd.DataFrame:
        df = pd.read_csv(self.filepath, sep=",", engine="python", dtype=object)
        df.columns = [str(col).strip().lower() for col in df.columns]

        date_col = next((c for c in ("date", "datetime") if c in df.columns), None)
        amount_col = next((c for c in ("amount", "original_amount") if c in df.columns), None)

        if not date_col or not amount_col:
            raise ValueError("Unable to find 'date' or 'amount' columns in TR CSV.")

        df = df.dropna(subset=[date_col, amount_col]).copy()
        df = df[df[amount_col].astype(str).str.strip() != ""]

        if "description" in df.columns:
            desc_series = df.apply(
                lambda row: self._compose_description(
                    row.get("description"),
                    row.get("name"),
                    row.get("counterparty_name"),
                ),
                axis=1,
            )
        else:
            desc_series = df.apply(
                lambda row: self._compose_fallback_description(
                    row.get("type"),
                    row.get("name"),
                    row.get("counterparty_name"),
                ),
                axis=1,
            )

        if (desc_series == "").any():
            raise ValueError("Transaction found without any descriptive text.")

        date_series = pd.to_datetime(df[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
        amount_series = df[amount_col].apply(normalize_amount)

        result_df = pd.DataFrame({
            COL_DATE: date_series,
            COL_DESCRIPTION: desc_series,
            COL_AMOUNT: amount_series,
        })

        result_df = result_df.dropna(subset=[COL_DATE, COL_AMOUNT]).reset_index(drop=True)
        return result_df[STANDARD_COLUMNS]

    @staticmethod
    def _clean_text(value: object) -> str:
        if value is None or pd.isna(value):
            return ""
        text = str(value).strip()
        if text.lower() in {"nan", "none", "null"}:
            return ""
        text = re.sub(r"\s*null\s*$", "", text, flags=re.IGNORECASE).strip()
        return text

    def _compose_description(self, desc_val: object, name_val: object, counterparty_val: object) -> str:
        desc_text = self._clean_text(desc_val)
        name_text = self._clean_text(name_val)
        cp_text = self._clean_text(counterparty_val)

        if desc_text:
            for part in (name_text, cp_text):
                if part and part.lower() not in desc_text.lower():
                    desc_text = f"{desc_text} - {part}"
            return desc_text

        parts = [p for p in (name_text, cp_text) if p]
        return " - ".join(parts)

    def _compose_fallback_description(self, type_val: object, name_val: object, counterparty_val: object) -> str:
        type_text = self._clean_text(type_val)
        name_text = self._clean_text(name_val)
        cp_text = self._clean_text(counterparty_val)

        parts = [p for p in (type_text, name_text, cp_text) if p]
        return " - ".join(parts)