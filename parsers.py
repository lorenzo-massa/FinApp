import hashlib
import warnings
from pathlib import Path
from typing import Any

import pandas as pd


def normalize_amount(value: Any) -> float:
    """Normalize an amount read from Excel/CSV into a float."""
    if pd.isna(value):
        raise ValueError("Importo nullo o non valido")

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
            # Preserve a lone dot as decimal separator for values like 12.345
            # instead of interpreting it as a thousands separator.
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


def parse_isybank(filepath: Path) -> pd.DataFrame:
    """Parse the Isybank format and return three standardized columns."""
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            category=UserWarning,
            module="openpyxl",
        )
        df_raw = pd.read_excel(filepath, header=None, dtype=object)

    if df_raw.shape[0] < 18:
        raise ValueError("Isybank file is too short to contain the expected header.")

    header_idx = None
    for index, row in df_raw.iloc[17:].iterrows():
        row_text = " ".join(
            str(value).strip().lower()
            for value in row.values
            if pd.notna(value)
        )

        if "data" in row_text and any(
            keyword in row_text
            for keyword in ("importo", "accrediti", "addebiti", "valore")
        ):
            header_idx = index
            break

    if header_idx is None:
        raise ValueError("Unable to find the header in the Isybank file.")

    df = df_raw.iloc[header_idx + 1 :].copy()
    df.columns = [str(value).strip() for value in df_raw.iloc[header_idx].values]
    df = df.dropna(how="all").reset_index(drop=True)

    date_column = None
    operation_column = None
    details_column = None
    amount_column = None

    for column in df.columns:
        column_text = str(column).strip().lower()

        if "data" in column_text and date_column is None:
            date_column = column
        elif "operazione" in column_text and operation_column is None:
            operation_column = column
        elif any(keyword in column_text for keyword in ("dettagli", "descrizione", "causale")) and details_column is None:
            details_column = column
        elif any(keyword in column_text for keyword in ("importo", "accrediti", "addebiti", "valore")) and amount_column is None:
            amount_column = column

    if not all([date_column, amount_column]):
        raise ValueError("Isybank header does not match the expected format.")

    if operation_column is None and details_column is None:
        raise ValueError("Isybank header does not match the expected format.")

    df = df.rename(columns={date_column: "date", amount_column: "amount"})

    if operation_column is not None:
        df["description"] = df[operation_column].fillna("").astype(str).str.strip()
    else:
        df["description"] = df[details_column].fillna("").astype(str).str.strip()

    if details_column is not None and operation_column is not None:
        details_series = df[details_column].fillna("").astype(str).str.strip()
        df["description"] = df["description"].where(
            df["description"].astype(str).str.len() > 0,
            details_series,
        )

    df["date"] = pd.to_datetime(df["date"], errors="coerce", format="mixed")
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")

    return df[["date", "description", "amount"]]


def parse_trade_republic(filepath: Path) -> pd.DataFrame:
    """Parse the Trade Republic format."""
    df = pd.read_csv(filepath, sep=",", engine="python", dtype=object)
    df.columns = [str(column).strip().lower() for column in df.columns]

    date_column = next(
        (column for column in ("date", "datetime") if column in df.columns),
        None,
    )
    amount_column = next(
        (column for column in ("amount", "original_amount") if column in df.columns),
        None,
    )

    if not date_column or not amount_column:
        raise ValueError("Unable to find 'date' or 'amount' columns in TR.")

    def _clean_text(value: object) -> str:
        if value is None or pd.isna(value):
            return ""

        text = str(value).strip()
        if text.lower() in {"nan", "none", "null"}:
            return ""

        return text

    def _compose_description(
        description_value: str,
        name_value: str,
        counterparty_value: str,
    ) -> str:
        description_text = _clean_text(description_value)
        name_text = _clean_text(name_value)
        counterparty_text = _clean_text(counterparty_value)

        if description_text:
            for part in (name_text, counterparty_text):
                if not part:
                    continue
                if part.lower() in description_text.lower():
                    continue
                description_text = f"{description_text} - {part}"
            return description_text

        parts: list[str] = []
        if name_text:
            parts.append(name_text)
        if counterparty_text:
            parts.append(counterparty_text)

        if parts:
            return " - ".join(parts)

        return "Trade Republic Tx"

    if "description" in df.columns:
        df["description"] = df.apply(
            lambda row: _compose_description(
                row.get("description", ""),
                row.get("name", ""),
                row.get("counterparty_name", ""),
            ),
            axis=1,
        )
    else:
        description_parts: list[pd.Series | str] = []

        if "type" in df.columns:
            description_parts.append(df["type"].fillna("").astype(str))
        if "name" in df.columns:
            description_parts.append(df["name"].fillna("").astype(str))
        if "counterparty_name" in df.columns:
            description_parts.append(df["counterparty_name"].fillna("").astype(str))

        if description_parts:
            df["description"] = (
                description_parts[0]
                if len(description_parts) == 1
                else description_parts[0].str.cat(description_parts[1:], sep=" - ")
            )
        else:
            df["description"] = "Trade Republic Tx"

    df = df.dropna(subset=[date_column, amount_column]).copy()
    df = df[df[amount_column].astype(str).str.strip() != ""]

    df["date"] = pd.to_datetime(df[date_column], errors="coerce")
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    df["amount"] = df[amount_column].apply(normalize_amount)

    df["description"] = df["description"].replace({"nan": "", "None": ""})
    df["description"] = df["description"].astype(str).str.strip()
    df["description"] = df["description"].str.replace(r"\s*null\s*$", "", case=False, regex=True)
    df["description"] = df["description"].astype(str).str.strip()

    if "description" not in df.columns:
        df["description"] = "Trade Republic Tx"

    df = df.dropna(subset=["date", "amount", "description"])
    return df[["date", "description", "amount"]]


def parse_bank_file(filepath: Path) -> tuple[pd.DataFrame, str]:
    """Select the correct parser based on the file extension or file name."""
    filename = filepath.name.lower()

    if filename.endswith(".csv") or "trade" in filename:
        return parse_trade_republic(filepath), "Trade Republic"

    return parse_isybank(filepath), "Isybank"
