import warnings
import pandas as pd

from .base import BaseParser
from .utils import normalize_amount, STANDARD_COLUMNS, COL_DATE, COL_DESCRIPTION, COL_AMOUNT


class IsybankParser(BaseParser):
    """Parser implementation for Isybank Excel files."""

    BANK_LABEL = "Isybank"
    DESCRIPTION_CANDIDATES = ["Operation", "Operazione", "Dettagli", "Descrizione"]

    def parse(self) -> pd.DataFrame:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=UserWarning)
            df = pd.read_excel(self.filepath, skiprows=17)

        df.columns = [str(col).strip() for col in df.columns]

        for col in ["Data", "Importo"]:
            if col not in df.columns:
                raise KeyError(f"Mandatory column '{col}' not found in Isybank Excel file.")

        desc_col = self._get_description_column(df.columns)

        date_series = (
            pd.to_datetime(df["Data"], format="mixed", errors="coerce")
            .dt.strftime("%Y-%m-%d")
        )

        desc_series = df[desc_col].fillna("").astype(str).str.strip()
        amount_series = df["Importo"].apply(normalize_amount)

        result_df = pd.DataFrame({
            COL_DATE: date_series,
            COL_DESCRIPTION: desc_series,
            COL_AMOUNT: amount_series,
        })

        result_df = result_df.dropna(subset=[COL_DATE, COL_AMOUNT])
        return result_df[STANDARD_COLUMNS]

    def _get_description_column(self, columns: pd.Index) -> str:
        for name in self.DESCRIPTION_CANDIDATES:
            if name in columns:
                return name
            
        for col in columns:
            if str(col).strip().lower() in [c.lower() for c in self.DESCRIPTION_CANDIDATES]:
                return col
                
        raise KeyError("No suitable description column found in the Isybank Excel file.")