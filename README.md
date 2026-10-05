# 🏦 FinApp - Finance Ingestor

![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

FinApp is a Python-based personal finance ingestor that reads bank and investment export files, normalizes them, and syncs the resulting rows to Google Sheets. The project currently supports standard transactions and a dedicated Directa investment-operations flow.

## ✨ Features

- **Multi-bank parsing:** supports common export layouts such as Isybank and Trade Republic.
- **Directa support:** imports Directa investment operations into a dedicated sheet separate from regular transactions.
- **Smart categorization:** applies rules from a configurable JSON file to bank transactions.
- **Google Sheets sync:** appends only the rows that are new based on a stable transaction hash.
- **Data integrity:** prevents duplicate inserts by hashing rows before upload.
- **Manual override support:** preserves category overrides on rows marked as manual.
- **Regression tests:** validates parsing and core upload logic.

---

## 📂 Project Structure

```text
├── input/                     # raw CSV/XLS/XLSX files to import
├── parsers/                   # bank-specific parsers and shared normalization helpers
│   ├── __init__.py
│   ├── base.py
│   ├── isybank.py
│   ├── trade_republic.py
│   └── utils.py
├── categories.json            # local category rules used at runtime
├── categories_example.json    # sample category configuration
├── categorization.py          # rule-based categorizer
├── cli.py                     # interactive command-line entrypoint
├── credentials.json           # local Google service-account credentials
├── credentials_example.json   # sample credentials template
├── google_sheets.py           # Google Sheets client and sheet helpers
├── settings.py                # spreadsheet and worksheet configuration
├── tests/                     # pytest regression tests
├── requirements.txt           # Python dependencies
├── README.md                  # project documentation
└── .venv/                     # local virtual environment (not committed)
```

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.11**
- A Google Cloud project with the Google Sheets API enabled
- A service account key downloaded as a JSON file
- A spreadsheet named `FinApp` (or adjust the name in `settings.py`)

### 1. Install the project

```bash
git clone https://github.com/lorenzo-massa/FinApp.git
cd FinApp

# Windows
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# macOS/Linux
# source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure local files

Create the files that are intentionally not committed:

1. `credentials.json` - the Google service account JSON key
2. `categories.json` - your categorization rules
3. `input/*.csv` or `*.xlsx` - files to import

Example `categories.json` structure:

```json
{
  "rules": {
    "Groceries": ["SUPERMARKET", "MARKET"],
    "Salary": ["PAYROLL", "SALARY"],
    "Utilities": ["ELECTRICITY", "WATER"]
  },
  "default_income": "Other Income",
  "default_expense": "Other Expenses"
}
```

Share the target spreadsheet with the service account email and grant Editor access.

---

## 💻 Usage

Run the CLI with the project virtual environment active:

```bash
python cli.py
```

On Windows it is also common to use the project venv explicitly:

```bash
.\.venv\Scripts\python.exe .\cli.py
```

### Interactive menu

1. **Sync new transactions**: imports standard bank files from `input/` into the `Transactions` sheet.
2. **Sync Directa operations**: imports only Directa files into the dedicated `Investments operations` sheet.
3. **Update Categories (Fast)**: re-applies the rules from `categories.json` without touching manual edits.
4. **Reset and reload while preserving manual overrides**: clears and re-imports transaction rows while keeping manual categories.
5. **Full reset and reload**: clears the `Transactions` sheet and reloads all standard files.

### Transactions workflow

1. Download your latest bank statements and drop them into `input/`.
2. Run the CLI and choose option `1` to sync standard transactions.
3. If you notice uncategorized items, update the keywords in `categories.json`.
4. Run the CLI again and choose option `3` to recategorize the existing rows while preserving manual overrides.

### Directa workflow

Directa rows are treated separately from normal bank transactions. They are written to `Investments operations`, and their `Id` column is populated with a stable hash so repeated imports do not duplicate rows.

The Directa import path is intentionally distinct from the normal transaction sync and should not be mixed with the standard `Transactions` flow.

---

## 🧪 Testing

The project uses `pytest` for regression coverage.

Run the suite with the local virtual environment:

```bash
.\.venv\Scripts\python.exe -m pytest -q
```

---

## 🤝 Contributing

Contributions, issues, and feature requests are welcome.

## 📝 License

This project is licensed under the MIT License.
