from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings
from csa_manager.services import DataLoadService, OptimizationService, ValuationService


st.set_page_config(
    page_title="CSA Manager",
    layout="wide",
    initial_sidebar_state="expanded",
)


UPLOAD_SPECS = {
    "collateral_positions": "Collateral positions",
    "market_prices": "Market prices",
    "fx_rates": "FX rates",
    "haircut_rules": "Haircut rules",
    "inventory": "Inventory",
    "margin_calls": "Margin calls",
}


VECTOR_UPLOAD_SPECS = {
    "deuda_076": "DEUDA.076 / DEUDA txt",
    "derivados_077": "DERIVADOS.077 / DERIVADOS txt",
}


def get_file_overrides() -> dict[str, object]:
    return st.session_state.get("uploaded_files", {})


def render_table(dataframe) -> None:
    st.dataframe(dataframe.astype(str), width="stretch", hide_index=True)


def read_vector_preview(uploaded_file: object, max_lines: int = 20):
    uploaded_file.seek(0)
    raw = uploaded_file.read()
    if isinstance(raw, str):
        text = raw
    else:
        text = raw.decode("latin-1", errors="replace")
    lines = text.splitlines()
    return [{"line_number": index + 1, "raw_line": line} for index, line in enumerate(lines[:max_lines])]


def render_header() -> None:
    cols = st.columns([2, 2, 2, 2])
    cols[0].metric("Business Date", settings.DEFAULT_BUSINESS_DATE)
    cols[1].metric("Environment", settings.DEFAULT_ENVIRONMENT)
    cols[2].metric("Process Status", "Ready")
    cols[3].metric("User Role", "Operator")


def render_dashboard() -> None:
    st.subheader("Daily Process Dashboard")
    loader = DataLoadService(get_file_overrides())
    input_rows = [
        ("Collateral Positions", len(loader.load_collateral_positions()), "Loaded"),
        ("Market Prices", len(loader.load_market_prices()), "Loaded"),
        ("FX Rates", len(loader.load_fx_rates()), "Loaded"),
        ("Haircut Rules", len(loader.load_haircut_rules()), "Loaded"),
        ("Inventory", len(loader.load_inventory()), "Loaded"),
        ("Margin Calls", len(loader.load_margin_calls()), "Loaded"),
    ]
    st.dataframe(
        [{"Input": name, "Rows": rows, "Status": status} for name, rows, status in input_rows],
        width="stretch",
        hide_index=True,
    )


def render_data_intake() -> None:
    st.subheader("Data Intake")
    st.caption("Upload CSV or Excel files to override the bundled example data for this session.")
    uploaded_files = dict(st.session_state.get("uploaded_files", {}))
    upload_columns = st.columns(2)
    for index, (key, label) in enumerate(UPLOAD_SPECS.items()):
        with upload_columns[index % 2]:
            uploaded = st.file_uploader(label, type=["csv", "xlsx", "xls"], key=f"upload_{key}")
            if uploaded is not None:
                uploaded_files[key] = uploaded

    st.divider()
    st.caption("Optional raw vector uploads. These are previewed only in v0.1; parsed vector pricing still uses the market prices table.")
    vector_files = dict(st.session_state.get("vector_files", {}))
    vector_columns = st.columns(2)
    for index, (key, label) in enumerate(VECTOR_UPLOAD_SPECS.items()):
        with vector_columns[index % 2]:
            uploaded = st.file_uploader(label, type=["076", "077", "txt", "dat"], key=f"upload_{key}")
            if uploaded is not None:
                vector_files[key] = uploaded
    st.session_state["uploaded_files"] = uploaded_files
    st.session_state["vector_files"] = vector_files

    if uploaded_files:
        st.success(f"{len(uploaded_files)} uploaded file(s) active in this session.")
    else:
        st.info("No uploads active. The app is using bundled example data.")

    loader = DataLoadService(get_file_overrides())
    tabs = st.tabs([
        "Collateral Positions",
        "Market Prices",
        "FX Rates",
        "Haircut Rules",
        "Inventory",
        "Margin Calls",
        "Raw Vectors",
    ])
    with tabs[0]:
        render_table(loader.load_collateral_positions())
    with tabs[1]:
        render_table(loader.load_market_prices())
    with tabs[2]:
        render_table(loader.load_fx_rates())
    with tabs[3]:
        render_table(loader.load_haircut_rules())
    with tabs[4]:
        render_table(loader.load_inventory())
    with tabs[5]:
        render_table(loader.load_margin_calls())
    with tabs[6]:
        if not vector_files:
            st.info("No raw vector files uploaded.")
        for key, uploaded_file in vector_files.items():
            st.markdown(f"**{VECTOR_UPLOAD_SPECS[key]}**")
            st.dataframe(read_vector_preview(uploaded_file), width="stretch", hide_index=True)


def render_valuations() -> None:
    st.subheader("Valuations")
    try:
        results = ValuationService(get_file_overrides()).run_collateral_valuation()
        total_value = results["collateral_value"].dropna().sum()
        cols = st.columns(3)
        cols[0].metric("Positions", len(results))
        cols[1].metric("Collateral Value", f"{total_value:,.2f}")
        cols[2].metric("Warnings", int(results["warnings"].astype(bool).sum()))
        st.dataframe(results, width="stretch", hide_index=True)
    except Exception as exc:
        st.error("Valuations could not be rendered.")
        st.exception(exc)


def render_optimization() -> None:
    st.subheader("Collateral Optimization")
    preserve_cash = st.toggle("Preserve cash", value=True)
    try:
        allocations, summary = OptimizationService(get_file_overrides()).optimize_first_margin_call(
            preserve_cash=preserve_cash
        )
        cols = st.columns(4)
        cols[0].metric("Status", str(summary["status"]))
        cols[1].metric("Required", str(summary["required_amount"]))
        cols[2].metric("Covered", str(summary["covered_amount"]))
        cols[3].metric("Excess", str(summary["overcollateralization"]))
        if summary["warnings"]:
            st.warning(summary["warnings"])
        st.dataframe(
            allocations.astype(
                {
                    "inventory_id": "string",
                    "asset_id": "string",
                    "fund_code": "string",
                    "currency": "string",
                    "explanation": "string",
                }
            ),
            width="stretch",
            hide_index=True,
        )
    except Exception as exc:
        st.error("Collateral optimization could not be rendered.")
        st.exception(exc)


def main() -> None:
    st.title("CSA Manager")
    render_header()
    page = st.sidebar.radio(
        "Navigation",
        ["Dashboard", "Data Intake", "Valuations", "Collateral Optimization"],
    )
    if page == "Dashboard":
        render_dashboard()
    elif page == "Data Intake":
        render_data_intake()
    elif page == "Valuations":
        render_valuations()
    elif page == "Collateral Optimization":
        render_optimization()


if __name__ == "__main__":
    main()
