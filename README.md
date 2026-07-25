# 🏦 FinApp - Finance Ingestor

![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

A Python-based CLI tool for automating personal finance tracking. FinApp ingests bank export files, normalizes transaction data, applies custom categorization rules, and syncs everything to a Google Sheets worksheet.

## ✨ Features

- **Multi-Bank Parsing:** Parsing and normalization for real-world bank export layouts (e.g., Isybank, Trade Republic).
- **Smart Categorization:** Rule-based category assignment driven by a highly configurable JSON file.
- **Google Sheets Sync:** Directly appends new transactions to your cloud spreadsheet avoiding duplicates.
- **Interactive CLI:** Command-line interface for daily syncing, category updates, or full resets.
- **Data Integrity:** Hashing mechanism to prevent duplicate entries during consecutive syncs.
- **Test Coverage:** Automated testing to ensure parser stability.

---

## 📂 Project Structure

```text
├── input/               # Directory for raw bank exports (ignored by git)
├── parsers/             # Logic for parsing and normalizing different bank formats
├── categorization.py    # Category resolution based on JSON rules
├── cli.py               # Interactive command-line entrypoint
├── google_sheets.py     # Google Sheets connection and worksheet operations
├── ingest_sheets.py     # Main application runner
├── settings.py          # Central configuration and constants
└── tests/               # Test suite
```

---

## 🚀 Getting Started

### Prerequisites

* **Python 3.11** or higher.
* A **Google Cloud Project** with the Google Sheets API enabled.
* A **Service Account** with access to your target Google Sheet.

### 1. Installation

Clone the repository and set up your virtual environment:

```bash
git clone [https://github.com/lorenzo-massa/FinApp.git](https://github.com/lorenzo-massa/FinApp.git)
cd FinApp

# Create and activate virtual environment (Windows)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# (On macOS/Linux use: source .venv/bin/activate)

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

Before running the application, you need to set up your local configuration files (these are ignored by Git for security reasons):

1. **Google Credentials:** Download your Service Account JSON key from Google Cloud Console, rename it to `credentials.json`, and place it in the root directory.
2. **Share the Sheet:** Open your target Google Sheet (`FinApp` by default) and share it with the email address of your Service Account (e.g., `your-bot@your-project.iam.gserviceaccount.com`) granting *Editor* permissions.
3. **Categorization Rules:** Create a `categories.json` file in the root directory. You can use the following structure as a template:

```json
{
  "rules": {
    "Groceries": ["SUPERMARKET", "MARKET"],
    "Salary": ["PAYROLL", "SALARY"],
    "Utilities": ["ELECTRICITY", "WATER"]
  },
  "default_income": "Pther Income",
  "default_expense": "Other Expenses"
}
```

---

## 💻 Usage

Place your raw bank export files (`.xls`, `.xlsx`, or `.csv`) into the `input/` directory, then run the CLI:

```bash
python ingest_sheets.py
```

### Interactive Menu Options:

1. **Sync new transactions (Default):** Imports files from `input/`, calculates hashes, and appends *only* the new transactions to Google Sheets.
2. **Update Categories (Fast):** Re-reads existing transactions from Google Sheets and applies the latest rules from `categories.json` (preserves rows marked as "Manual").
3. **Full reset and reload:** Clears the `Transactions` worksheet completely and re-imports all files from scratch.

### Real-world Workflow

1. Download your latest bank statements and drop them into `input/`.
2. Run the script and choose Option `1`.
3. If you notice uncategorized items in Google Sheets, add the relevant keywords to your `categories.json`.
4. Run the script again and choose Option `2` to retroactively apply the new categories.

---

## 🧪 Testing

The automated tests use in-memory fixtures to exercise the parser behavior deterministically, ensuring that real financial data is not required for testing.

To run the regression suite:

```bash
python -m pytest -q
```

---

## 🤝 Contributing

Contributions, issues, and feature requests are welcome! Feel free to check the [issues page](https://github.com/lorenzo-massa/FinApp/issues).

## 📝 License

This project is licensed under the MIT License.
