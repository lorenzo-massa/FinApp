import os
from pathlib import Path

# Base directory
BASE_DIR = Path(__file__).resolve().parent

# Optional .env loader
ENV_FILE = BASE_DIR / ".env"
if ENV_FILE.is_file():
    try:
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    key, val = stripped.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("\"'")
                    if key and key not in os.environ:
                        os.environ[key] = val
    except Exception:
        pass

# File paths
INPUT_DIR = Path(os.getenv("FINAPP_INPUT_DIR", str(BASE_DIR / "input")))
ARCHIVE_DIR = Path(os.getenv("FINAPP_ARCHIVE_DIR", str(INPUT_DIR / "archive")))
CREDENTIALS_FILE = Path(os.getenv("FINAPP_CREDENTIALS_FILE", str(BASE_DIR / "credentials.json")))
CATEGORIES_FILE = Path(os.getenv("FINAPP_CATEGORIES_FILE", str(BASE_DIR / "categories.json")))

# Google Sheets Configuration
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
SPREADSHEET_NAME = os.getenv("FINAPP_SPREADSHEET_NAME", "FinApp")
WORKSHEET_TRANSACTIONS = os.getenv("FINAPP_WORKSHEET_TRANSACTIONS", "Transactions")
WORKSHEET_CATEGORIES = os.getenv("FINAPP_WORKSHEET_CATEGORIES", "Categories")
WORKSHEET_DIRECTA = os.getenv("FINAPP_WORKSHEET_DIRECTA", "Investments operations")