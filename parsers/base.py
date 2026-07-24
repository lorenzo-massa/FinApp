from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd

class BaseParser(ABC):
    """Abstract Base Class for bank statement parsers."""

    BANK_LABEL: str = "Unknown"

    def __init__(self, filepath: Path) -> None:
        self.filepath = filepath

    @abstractmethod
    def parse(self) -> pd.DataFrame:
        """Parse the bank file and return a DataFrame with standardized columns."""
        pass