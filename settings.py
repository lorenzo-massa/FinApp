from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "input"
CREDENTIALS_FILE = BASE_DIR / "credentials.json"
CATEGORIES_FILE = BASE_DIR / "categories.json"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
SPREADSHEET_NAME = "FinApp"
WORKSHEET_TRANSACTIONS = "Transactions"
WORKSHEET_CATEGORIES = "Categories"
