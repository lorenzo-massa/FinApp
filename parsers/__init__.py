from pathlib import Path
import warnings
import pandas as pd

from .base import BaseParser
from .directa import DirectaParser
from .isybank import IsybankParser
from .trade_republic import TradeRepublicParser


def detect_parser(filepath: Path) -> type[BaseParser]:
    """Inspect file content and metadata to determine the appropriate bank parser."""
    filename = filepath.name.lower()
    suffix = filepath.suffix.lower()

    # 1. Content-based inspection for CSV files
    if suffix == ".csv" and filepath.is_file():
        try:
            with open(filepath, "r", encoding="utf-8-sig", errors="ignore") as f:
                header_sample = "".join(f.readline() for _ in range(25)).lower()

            if "data operazione" in header_sample and "tipo operazione" in header_sample:
                return DirectaParser

            if any(k in header_sample for k in ["counterparty", "original_amount"]) or (
                "date" in header_sample and "amount" in header_sample
            ):
                return TradeRepublicParser
        except Exception:
            pass

    # 2. Content-based inspection for Excel files
    elif suffix in {".xlsx", ".xls"} and filepath.is_file():
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", category=UserWarning)
                peek_df = pd.read_excel(filepath, skiprows=17, nrows=1)
                cols = {str(c).strip().lower() for c in peek_df.columns}
                if {"data", "operazione", "importo"}.issubset(cols):
                    return IsybankParser
        except Exception:
            pass

    # 3. Fallback based on filename conventions
    if "directa" in filename:
        return DirectaParser
    if "trade" in filename:
        return TradeRepublicParser
    if "isybank" in filename:
        return IsybankParser
    if suffix == ".csv":
        return TradeRepublicParser
    if suffix in {".xlsx", ".xls"}:
        return IsybankParser

    raise ValueError(f"Unsupported or unrecognized bank file: {filepath.name}")


def parse_bank_file(filepath: Path) -> tuple[pd.DataFrame, str]:
    """Select and execute the correct parser based on file type and content."""
    parser_class = detect_parser(filepath)
    parser = parser_class(filepath)
    return parser.parse(), parser.BANK_LABEL


__all__ = [
    "BaseParser",
    "DirectaParser",
    "IsybankParser",
    "TradeRepublicParser",
    "detect_parser",
    "parse_bank_file",
]