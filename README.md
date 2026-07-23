# Finance Ingestor

A small Python project for ingesting bank exports into Google Sheets, normalizing transaction data, and applying category rules from JSON configuration.

## Overview

The project is designed to:

- read real bank export formats such as Isybank and Trade Republic,
- standardize the resulting transaction columns,
- classify transactions using configurable category rules,
- sync the processed data into a Google Sheets workbook through a simple interactive CLI.

## Project structure

- `settings.py` — central configuration, constants, and worksheet names.
- `parsers.py` — parsing and normalization logic for Isybank and Trade Republic exports.
- `categorization.py` — category resolution based on the rules in `categories.json`.
- `google_sheets.py` — Google Sheets connection, synchronization, and worksheet helpers.
- `cli.py` — interactive command-line entrypoint.
- `tests/` — regression test suite.
- `input/` — folder used for the files to be imported.

## Features

- robust parsing for real-world bank export layouts,
- normalized date and amount handling,
- category assignment driven by JSON rules,
- targeted category refresh on existing sheet data,
- full reset-and-reload workflow,
- automated regression testing to lock in the expected behavior.

## Requirements

- Python 3.11+
- a virtual environment named `.venv`
- `credentials.json` containing the Google service account credentials
- `categories.json` containing the categorization rules

## Setup

1. Create the virtual environment:

   ```powershell
   python -m venv .venv
   ```

2. Activate it:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

3. Install dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

4. Run the CLI:

   ```powershell
   python ingest_sheets.py
   ```

## Interactive menu

When the CLI starts, it offers the following options:

1. `Sync new transactions`  
   Imports files from `input/` and appends only the new transactions.

2. `Update ONLY Categories`  
   Re-reads the existing transactions from Google Sheets and updates their categories using the current JSON rules.

3. `Full reset and reload from scratch`  
   Clears the `Transactions` worksheet and reloads all input files from scratch.

## Real-world workflow example

A typical usage flow looks like this:

1. Place the latest bank export files into `input/`.
2. Run the CLI with:

   ```powershell
   python ingest_sheets.py
   ```

3. Choose option `1` to import the newly available transactions.
4. If you change the category rules in `categories.json`, choose option `2` to refresh categories on the existing sheet without re-importing everything.
5. If you want to rebuild the entire transaction state from scratch, choose option `3` to clear the worksheet and reprocess all input files.

## Testing

Run the regression suite with:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## Testing note

The automated tests do not read the real files from `input/`. Instead, they use in-memory fixtures to exercise the parser behavior deterministically without relying on external files.

## Maintenance notes

- The project is split into modules to keep the codebase easier to maintain and test.
- Logging is used to distinguish informational messages, warnings, and errors.
- Category behavior is configurable through JSON rather than hardcoded in the application logic.
