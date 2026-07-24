import pandas as pd
import hashlib
from typing import Any

# Global constants for standardized output columns
COL_DATE = "date"
COL_DESCRIPTION = "description"
COL_AMOUNT = "amount"
STANDARD_COLUMNS = [COL_DATE, COL_DESCRIPTION, COL_AMOUNT]

def normalize_amount(value: Any) -> float:
    """Normalize an amount read from Excel/CSV into a float."""
    if pd.isna(value):
        raise ValueError("Null or invalid amount")

    if isinstance(value, str):
        clean_value = value.strip().replace("€", "").replace(" ", "")

        if "," in clean_value and "." in clean_value:
            if clean_value.rfind(",") > clean_value.rfind("."):
                clean_value = clean_value.replace(".", "").replace(",", ".")
            else:
                clean_value = clean_value.replace(",", "")
        elif "," in clean_value:
            integer_part, fractional_part = clean_value.split(",", 1)
            if len(fractional_part) <= 2:
                clean_value = f"{integer_part}.{fractional_part}"
            else:
                clean_value = clean_value.replace(",", "")
        elif "." in clean_value:
            clean_value = clean_value

        return float(clean_value)

    return float(value)

def build_transaction_hash(
    bank_label: str,
    date_val: str,
    amount_val: float,
    desc_val: str,
) -> str:
    """Generate a stable hash to avoid duplicate loads."""
    raw_hash_string = f"{bank_label}_{date_val}_{amount_val:.2f}_{desc_val.lower()}"
    return hashlib.sha256(raw_hash_string.encode("utf-8")).hexdigest()