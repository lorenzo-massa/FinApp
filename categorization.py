import json
from pathlib import Path
from typing import Any

from settings import CATEGORIES_FILE

# Global constants for default categories
DEFAULT_INCOME_LABEL = "Varie"
DEFAULT_EXPENSE_LABEL = "Altro"


def load_category_rules(filepath: Path = CATEGORIES_FILE) -> dict[str, Any]:
    """Loads category mapping rules from a JSON file."""
    default_config = {
        "rules": {},
        "default_income": DEFAULT_INCOME_LABEL,
        "default_expense": DEFAULT_EXPENSE_LABEL,
    }
    
    if not filepath.exists():
        return default_config

    try:
        with open(filepath, "r", encoding="utf-8") as file:
            data = json.load(file)
            return data if isinstance(data, dict) else default_config
    except (json.JSONDecodeError, IOError):
        return default_config


class TransactionCategorizer:
    """Categorizes transactions based on configurable keyword rules and amount signs."""

    def __init__(self, category_data: dict[str, Any]) -> None:
        raw_rules = category_data.get("rules", {})
        # Pre-convert keywords to uppercase for better performance and robustness
        self.rules: dict[str, list[str]] = {
            category: [kw.upper() for kw in keywords]
            for category, keywords in raw_rules.items()
        }
        self.default_income: str = category_data.get("default_income", DEFAULT_INCOME_LABEL)
        self.default_expense: str = category_data.get("default_expense", DEFAULT_EXPENSE_LABEL)

    def categorize(self, description: str, amount: float) -> str:
        """Categorize a single transaction by description and amount."""
        desc_upper = description.upper()

        # 1. Match specific rules
        for category, keywords in self.rules.items():
            for keyword in keywords:
                if keyword in desc_upper:
                    return category

        # 2. Fallback based on transaction direction
        if amount > 0:
            return self.default_income
        return self.default_expense