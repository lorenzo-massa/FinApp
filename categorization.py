import json
import re
from pathlib import Path
from typing import TypedDict

from settings import CATEGORIES_FILE

# Global constants for default categories
DEFAULT_INCOME_LABEL = "Varie"
DEFAULT_EXPENSE_LABEL = "Altro"


class CategoryConfig(TypedDict):
    rules: dict[str, list[str]]
    default_income: str
    default_expense: str


def load_category_rules(filepath: Path = CATEGORIES_FILE) -> CategoryConfig:
    """Loads category mapping rules from a JSON file."""
    default_config: CategoryConfig = {
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

    def __init__(self, category_data: CategoryConfig) -> None:
        raw_rules = category_data.get("rules", {})
        self.rules: dict[str, list[re.Pattern[str]]] = {}
        for category, patterns in raw_rules.items():
            compiled_patterns: list[re.Pattern[str]] = []
            for pattern in patterns:
                if not isinstance(pattern, str):
                    raise ValueError(
                        f"Invalid regex rule for category '{category}': pattern must be a string."
                    )
                try:
                    compiled_patterns.append(re.compile(pattern, re.IGNORECASE))
                except re.error as err:
                    raise ValueError(
                        f"Invalid regex rule for category '{category}': {err}"
                    ) from err

            self.rules[category] = compiled_patterns

        self.default_income: str = category_data.get("default_income", DEFAULT_INCOME_LABEL)
        self.default_expense: str = category_data.get("default_expense", DEFAULT_EXPENSE_LABEL)

    def categorize(self, description: str, amount: float) -> str:
        """Categorize a single transaction by description and amount."""
        # 1. Match specific rules
        for category, patterns in self.rules.items():
            for pattern in patterns:
                if pattern.search(description):
                    return category

        # 2. Fallback based on transaction direction
        if amount > 0:
            return self.default_income
        return self.default_expense