import json
from typing import Any

from settings import CATEGORIES_FILE


def load_category_rules() -> dict[str, Any]:
    """Load category configuration from JSON."""
    if not CATEGORIES_FILE.exists():
        raise FileNotFoundError(
            f"Unable to find the configuration file {CATEGORIES_FILE.name}"
        )

    with CATEGORIES_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def categorize_transaction(
    description: str,
    amount: float,
    category_data: dict[str, Any],
) -> str:
    """Assign the most specific available category to a transaction."""
    description_upper = str(description).upper()
    rules = category_data.get("rules", {})
    default_income = category_data.get("default_income", "General Income")
    default_expense = category_data.get("default_expense", "Other")

    best_category: str | None = None
    max_pattern_length = 0

    for category, patterns in rules.items():
        for pattern in patterns:
            if not pattern:
                continue

            if pattern.upper() in description_upper:
                if len(pattern) > max_pattern_length:
                    max_pattern_length = len(pattern)
                    best_category = category

    if best_category:
        return best_category

    return default_income if amount > 0 else default_expense
