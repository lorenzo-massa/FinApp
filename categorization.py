import json
import logging
import re
from pathlib import Path
from typing import Any, TypedDict, Union

from settings import CATEGORIES_FILE

logger = logging.getLogger(__name__)

# Global constants for default categories
DEFAULT_INCOME_LABEL = "Varie"
DEFAULT_EXPENSE_LABEL = "Altro"

RuleItem = Union[str, dict[str, Any]]


class CategoryConfig(TypedDict, total=False):
    rules: dict[str, list[RuleItem]]
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
        logger.warning("Categories file not found at %s. Using default empty rules.", filepath)
        return default_config

    try:
        with open(filepath, "r", encoding="utf-8") as file:
            data = json.load(file)
            return data if isinstance(data, dict) else default_config
    except Exception as exc:
        logger.error("Failed to load category rules from %s: %s. Using default empty rules.", filepath, exc)
        return default_config


class CompiledRule:
    """Represents a compiled rule with optional criteria."""

    def __init__(
        self,
        pattern: re.Pattern[str],
        rule_type: str | None = None,
        bank: str | None = None,
        min_amount: float | None = None,
        max_amount: float | None = None,
    ) -> None:
        self.pattern = pattern
        self.rule_type = rule_type.lower() if rule_type else None
        self.bank = bank.lower() if bank else None
        self.min_amount = float(min_amount) if min_amount is not None else None
        self.max_amount = float(max_amount) if max_amount is not None else None

    def matches(self, description: str, amount: float, bank: str = "") -> bool:
        if not self.pattern.search(description):
            return False

        if self.rule_type:
            if self.rule_type in {"expense", "outflow"} and amount > 0:
                return False
            if self.rule_type in {"income", "inflow"} and amount < 0:
                return False

        if self.bank and bank:
            if self.bank not in bank.lower():
                return False

        abs_amount = abs(amount)
        if self.min_amount is not None and abs_amount < self.min_amount:
            return False
        if self.max_amount is not None and abs_amount > self.max_amount:
            return False

        return True


class TransactionCategorizer:
    """Categorizes transactions based on configurable keyword rules and amount signs."""

    def __init__(self, category_data: CategoryConfig) -> None:
        raw_rules = category_data.get("rules", {})
        self.rules: dict[str, list[CompiledRule]] = {}

        for category, items in raw_rules.items():
            compiled_rules: list[CompiledRule] = []
            for item in items:
                if isinstance(item, str):
                    try:
                        pat = re.compile(item, re.IGNORECASE)
                        compiled_rules.append(CompiledRule(pattern=pat))
                    except re.error as err:
                        raise ValueError(
                            f"Invalid regex rule for category '{category}': {err}"
                        ) from err
                elif isinstance(item, dict):
                    pattern_str = item.get("pattern")
                    if not isinstance(pattern_str, str):
                        raise ValueError(
                            f"Invalid regex rule for category '{category}': pattern must be a string."
                        )
                    try:
                        pat = re.compile(pattern_str, re.IGNORECASE)
                        compiled_rules.append(
                            CompiledRule(
                                pattern=pat,
                                rule_type=item.get("type") or item.get("direction"),
                                bank=item.get("bank"),
                                min_amount=item.get("min_amount"),
                                max_amount=item.get("max_amount"),
                            )
                        )
                    except re.error as err:
                        raise ValueError(
                            f"Invalid regex rule for category '{category}': {err}"
                        ) from err
                else:
                    raise ValueError(
                        f"Invalid regex rule for category '{category}': pattern must be a string."
                    )

            self.rules[category] = compiled_rules

        self.default_income: str = category_data.get("default_income", DEFAULT_INCOME_LABEL)
        self.default_expense: str = category_data.get("default_expense", DEFAULT_EXPENSE_LABEL)

    def categorize(self, description: str, amount: float, bank: str = "") -> str:
        """Categorize a single transaction by description, amount, and bank."""
        # 1. Match specific rules
        for category, rules in self.rules.items():
            for rule in rules:
                if rule.matches(description, amount, bank):
                    return category

        # 2. Fallback based on transaction direction
        if amount > 0:
            return self.default_income
        return self.default_expense