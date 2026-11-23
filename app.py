import logging
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from categorization import (
    TransactionCategorizer,
    load_category_rules,
    validate_categories_against_sheet,
)
from google_sheets import DIRECTA_HEADERS, GoogleSheetsClient
from parsers import detect_parser, parse_bank_file
from parsers.utils import (
    COL_AMOUNT,
    COL_DATE,
    COL_DESCRIPTION,
    build_transaction_hash,
    normalize_amount,
)
from settings import (
    CATEGORIES_FILE,
    SPREADSHEET_NAME,
    WORKSHEET_CATEGORIES,
    WORKSHEET_DIRECTA,
    WORKSHEET_TRANSACTIONS,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="FinApp - Finance Ingestor",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def get_sheets_client() -> GoogleSheetsClient | None:
    try:
        return GoogleSheetsClient()
    except Exception as exc:
        st.error(f"Impossibile connettersi a Google Sheets: {exc}")
        return None


def get_existing_hashes(client: GoogleSheetsClient, is_directa: bool) -> set[str]:
    try:
        sheet = client.directa_sheet if is_directa else client.sheet
        return set(client.get_hashes(sheet))
    except Exception as exc:
        st.warning(f"Errore nel recupero degli ID esistenti dal foglio: {exc}")
        return set()


def process_uploaded_file(
    file_bytes: bytes,
    filename: str,
    categorizer: TransactionCategorizer,
    existing_standard_hashes: set[str],
    existing_directa_hashes: set[str],
) -> dict:
    suffix = Path(filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(file_bytes)
        tmp_path = Path(tmp.name)

    try:
        parser_cls = detect_parser(tmp_path)
        df, bank_label = parse_bank_file(tmp_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    is_directa = bank_label.lower() == "directa"
    seen_in_file: dict[tuple[str, str, float, str], int] = {}
    rows_to_upload: list[list[object]] = []
    preview_records: list[dict] = []
    duplicates_count = 0

    if is_directa:
        for _, row in df.iterrows():
            operation = [row.get(header.lower(), "") for header in DIRECTA_HEADERS[1:]]
            op_dict = {
                header.lower(): value
                for header, value in zip(DIRECTA_HEADERS[1:], operation)
            }
            date_val = str(op_dict.get("date") or "")
            amount_val = normalize_amount(op_dict.get("amount_eur") or 0)
            desc_val = str(op_dict.get("description") or "")

            key = ("directa", date_val, amount_val, desc_val.lower())
            occ = seen_in_file.get(key, 0)
            seen_in_file[key] = occ + 1

            h = build_transaction_hash("directa", date_val, amount_val, desc_val, occurrence=occ)
            is_dup = h in existing_directa_hashes

            if is_dup:
                duplicates_count += 1
            else:
                existing_directa_hashes.add(h)
                rows_to_upload.append([h, *operation])

            preview_records.append({
                "Date": date_val,
                "Bank": "Directa",
                "Category": "Investment",
                "Amount": amount_val,
                "Description": desc_val,
                "Status": "⚠️ Già caricata" if is_dup else "✅ Nuova",
            })
    else:
        for _, row in df.iterrows():
            if row[COL_DATE] is None or row[COL_AMOUNT] is None:
                continue

            date_obj = row[COL_DATE]
            amount_val = normalize_amount(row[COL_AMOUNT])
            desc_val = str(row[COL_DESCRIPTION]).strip()

            key = (bank_label, str(date_obj), amount_val, desc_val.lower())
            occ = seen_in_file.get(key, 0)
            seen_in_file[key] = occ + 1

            h = build_transaction_hash(bank_label, str(date_obj), amount_val, desc_val, occurrence=occ)
            is_dup = h in existing_standard_hashes

            category_name = categorizer.categorize(desc_val, amount_val, bank_label)

            if is_dup:
                duplicates_count += 1
            else:
                existing_standard_hashes.add(h)
                rows_to_upload.append([
                    h,
                    str(date_obj),
                    bank_label,
                    category_name,
                    amount_val,
                    desc_val,
                    str(date_obj)[:7],
                    False,
                ])

            preview_records.append({
                "Date": str(date_obj),
                "Bank": bank_label,
                "Category": category_name,
                "Amount": amount_val,
                "Description": desc_val,
                "Status": "⚠️ Già caricata" if is_dup else "✅ Nuova",
            })

    return {
        "filename": filename,
        "bank_label": bank_label,
        "is_directa": is_directa,
        "total_parsed": len(df),
        "new_count": len(rows_to_upload),
        "duplicates_count": duplicates_count,
        "rows_to_upload": rows_to_upload,
        "preview_records": preview_records,
    }


def main():
    st.title("🏦 FinApp - Personal Finance Hub")

    category_config = load_category_rules()
    categorizer = TransactionCategorizer(category_config)

    # Sidebar
    with st.sidebar:
        st.header("⚙️ Stato Sistema")
        st.markdown(f"**Foglio Google**: `{SPREADSHEET_NAME}`")
        st.markdown(f"**Worksheet Transazioni**: `{WORKSHEET_TRANSACTIONS}`")
        st.markdown(f"**Worksheet Investimenti**: `{WORKSHEET_DIRECTA}`")
        st.markdown(f"**Regole Categorie caricate**: `{len(category_config.get('rules', {}))}`")

        client = get_sheets_client()
        if client:
            st.success("🟢 Google Sheets connesso")
        else:
            st.error("🔴 Disconnesso")

        st.markdown("---")
        st.caption("FinApp ETL Pipeline & Ingestor")

    tab_import, tab_categories, tab_dashboard = st.tabs([
        "📥 Import & Sync",
        "🏷️ Categorie & Audit",
        "📊 Panoramica Dati",
    ])

    # ==========================================
    # TAB 1: IMPORT & SYNC
    # ==========================================
    with tab_import:
        st.subheader("Carica Estratti Conto (Drag & Drop)")
        uploaded_files = st.file_uploader(
            "Trascina qui i tuoi file (CSV, XLS, XLSX da Isybank, Trade Republic, Directa)",
            type=["csv", "xls", "xlsx"],
            accept_multiple_files=True,
        )

        if uploaded_files:
            if not client:
                st.error("Impossibile procedere senza connessione a Google Sheets.")
                return

            with st.spinner("Connessione a Google Sheets per recupero hash esistenti..."):
                existing_standard = get_existing_hashes(client, is_directa=False)
                existing_directa = get_existing_hashes(client, is_directa=True)

            all_results = []
            for upl in uploaded_files:
                file_bytes = upl.read()
                res = process_uploaded_file(
                    file_bytes=file_bytes,
                    filename=upl.name,
                    categorizer=categorizer,
                    existing_standard_hashes=existing_standard,
                    existing_directa_hashes=existing_directa,
                )
                all_results.append(res)

            total_new_standard = sum(len(r["rows_to_upload"]) for r in all_results if not r["is_directa"])
            total_new_directa = sum(len(r["rows_to_upload"]) for r in all_results if r["is_directa"])
            total_duplicates = sum(r["duplicates_count"] for r in all_results)

            st.markdown("---")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("File Analizzati", len(all_results))
            col2.metric("Nuove Transazioni", total_new_standard)
            col3.metric("Nuove Op. Directa", total_new_directa)
            col4.metric("Duplicati Ignorati", total_duplicates)

            all_previews = []
            for r in all_results:
                for row in r["preview_records"]:
                    all_previews.append({
                        "File": r["filename"],
                        "Data": row["Date"],
                        "Conto": row["Bank"],
                        "Categoria": row["Category"],
                        "Importo (€)": row["Amount"],
                        "Descrizione": row["Description"],
                        "Stato": row["Status"],
                    })

            if all_previews:
                st.subheader("📋 Anteprima Transazioni Rilevate")
                preview_df = pd.DataFrame(all_previews)
                st.dataframe(
                    preview_df,
                    use_container_width=True,
                    hide_index=True,
                )

            st.markdown("---")
            col_btn1, col_btn2 = st.columns([1, 4])
            with col_btn1:
                sync_button = st.button("🚀 Sincronizza su Sheets", type="primary", use_container_width=True)

            if sync_button:
                if total_new_standard == 0 and total_new_directa == 0:
                    st.info("Nessuna nuova transazione da caricare (tutte già presenti nel foglio).")
                else:
                    progress = st.progress(0)
                    status_text = st.empty()

                    if total_new_standard > 0:
                        status_text.text("Caricamento transazioni standard...")
                        standard_rows = []
                        for r in all_results:
                            if not r["is_directa"]:
                                standard_rows.extend(r["rows_to_upload"])
                        client.append_rows(standard_rows, client.sheet)
                        progress.progress(60)

                    if total_new_directa > 0:
                        status_text.text("Caricamento operazioni Directa...")
                        directa_rows = []
                        for r in all_results:
                            if r["is_directa"]:
                                directa_rows.extend(r["rows_to_upload"])
                        client.append_rows(directa_rows, client.directa_sheet)
                        progress.progress(100)

                    status_text.text("Completato!")
                    st.success(
                        f"✅ Sincronizzazione completata! {total_new_standard} transazioni e "
                        f"{total_new_directa} operazioni Directa caricate con successo su Google Sheets."
                    )
        else:
            st.info("💡 Trascina uno o più file esportati per visualizzare l'anteprima e sincronizzare.")

    # ==========================================
    # TAB 2: CATEGORIE & AUDIT
    # ==========================================
    with tab_categories:
        st.subheader("Audit & Allineamento Categorie")
        if client:
            sheet_categories = client.get_valid_categories()
            if sheet_categories:
                diff = validate_categories_against_sheet(category_config, sheet_categories)
                col_a, col_b = st.columns(2)

                with col_a:
                    st.markdown(f"### Nel foglio `{WORKSHEET_CATEGORIES}` ({len(sheet_categories)})")
                    st.write(sorted(list(sheet_categories)))

                with col_b:
                    st.markdown(f"### Nel file locale `{CATEGORIES_FILE.name}`")
                    st.write(sorted(list(category_config.get("rules", {}).keys())))

                st.markdown("---")
                if diff["unknown_in_json"]:
                    st.warning(
                        f"⚠️ **Presenti in JSON ma mancanti in Google Sheets**: {', '.join(sorted(diff['unknown_in_json']))}"
                    )
                else:
                    st.success("✅ Tutte le categorie del JSON esistono nel foglio Google!")

                if diff["uncovered_in_sheet"]:
                    st.info(
                        f"ℹ️ **Presenti in Google Sheets ma senza regole nel JSON**: {', '.join(sorted(diff['uncovered_in_sheet']))}"
                    )
            else:
                st.info(f"Nessuna categoria trovata nel foglio `{WORKSHEET_CATEGORIES}`.")

            st.markdown("---")
            st.subheader("⚡ Ricategorizzazione Rapida")
            st.caption("Riapplica le regole del JSON a tutte le transazioni non manuali già presenti su Google Sheets.")
            if st.button("Aggiorna Categorie su Google Sheets"):
                with st.spinner("Ricategorizzazione in corso su Google Sheets..."):
                    updated = client.recategorize_existing(categorizer)
                    st.success(f"Aggiornamento completato: {updated} transazioni aggiornate!")
        else:
            st.warning("Connessione a Google Sheets non disponibile.")

    # ==========================================
    # TAB 3: PANORAMICA & GRAFICI
    # ==========================================
    with tab_dashboard:
        st.subheader("📊 Panoramica Transazioni Recenti")
        if uploaded_files and 'all_previews' in locals() and all_previews:
            df_chart = pd.DataFrame(all_previews)
            new_df = df_chart[df_chart["Stato"] == "✅ Nuova"]

            if not new_df.empty:
                col_m1, col_m2 = st.columns(2)
                entrate = new_df[new_df["Importo (€)"] > 0]["Importo (€)"].sum()
                uscite = new_df[new_df["Importo (€)"] < 0]["Importo (€)"].sum()
                col_m1.metric("Totale Entrate (Nuove)", f"+{entrate:,.2f} €")
                col_m2.metric("Totale Uscite (Nuove)", f"{uscite:,.2f} €")

                st.markdown("#### Spese per Categoria (Transazioni Nuove)")
                spese_df = new_df[new_df["Importo (€)"] < 0].copy()
                spese_df["Importo (€)"] = spese_df["Importo (€)"].abs()
                cat_summary = spese_df.groupby("Categoria")["Importo (€)"].sum().reset_index()
                st.bar_chart(cat_summary.set_index("Categoria"))
            else:
                st.info("Tutte le transazioni analizzate sono già presenti su Google Sheets.")
        else:
            st.info("Carica dei file nel tab 'Import & Sync' per visualizzare il riepilogo grafico delle nuove transazioni.")


if __name__ == "__main__":
    main()
