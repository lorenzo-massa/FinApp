from pathlib import Path
import pandas as pd

from .base import BaseParser
from .isybank import IsybankParser
from .trade_republic import TradeRepublicParser

def parse_bank_file(filepath: Path) -> tuple[pd.DataFrame, str]:
    """Select and execute the correct parser based on file type."""
    filename = filepath.name.lower()

    if filename.endswith(".csv") or "trade" in filename:
        parser = TradeRepublicParser(filepath)
    else:
        parser = IsybankParser(filepath)

    return parser.parse(), parser.BANK_LABEL

__all__ = [
    "BaseParser",
    "IsybankParser",
    "TradeRepublicParser"
]