import re
import warnings

import pandas as pd

from .base import BaseParser
from .utils import normalize_amount, STANDARD_COLUMNS, COL_DATE, COL_DESCRIPTION, COL_AMOUNT


class IsybankParser(BaseParser):
    """Parser implementation for Isybank Excel files."""

    BANK_LABEL = "Isybank"

    def parse(self) -> pd.DataFrame:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=UserWarning)
            df = pd.read_excel(self.filepath, skiprows=17)

        df.columns = [str(col).strip() for col in df.columns]

        for col in ["Data", "Operazione", "Dettagli", "Importo"]:
            if col not in df.columns:
                raise KeyError(f"Mandatory column '{col}' not found in Isybank Excel file.")

        desc_series = []
        for _, row in df.iterrows():
            description = self._clean_text(row.get("Operazione"))
            detail = self._clean_text(row.get("Dettagli"))
            description = self._compose_description(description, detail)
            desc_series.append(description)

        date_series = (
            pd.to_datetime(df["Data"], format="mixed", errors="coerce")
            .dt.strftime("%Y-%m-%d")
        )
        amount_series = df["Importo"].apply(normalize_amount)

        result_df = pd.DataFrame({
            COL_DATE: date_series,
            COL_DESCRIPTION: desc_series,
            COL_AMOUNT: amount_series,
        })

        result_df = result_df.dropna(subset=[COL_DATE, COL_AMOUNT])
        return result_df[STANDARD_COLUMNS]

    @staticmethod
    def _clean_text(value) -> str:
        if pd.isna(value):
            return ""
        return str(value).strip()

    @staticmethod
    def _compose_description(description: str, detail: str) -> str:
        if "bonifico" in description.lower():
            match = re.search(r"disposto\s+(.*)", detail, flags=re.IGNORECASE)
            if match:
                return f"{description} {match.group(1).strip()}"
        return description