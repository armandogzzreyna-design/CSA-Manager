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
    "collateral_positions": "Collateral positions CSV",
    "market_prices": "Market prices CSV",
    "fx_rates": "FX rates CSV",
    "haircut_rules": "Haircut rules CSV",
    "inventory": "Inventory CSV",
    "margin_calls": "Margin calls CSV",
}


def get_file_overrides() -> dict[str, object]:
    return st.session_state.get("uploaded_files", {})


def render_table(dataframe) -> None:
    st.dataframe(dataframe.astype(str), use_container_width=True, hide_index=True)


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
        use_container_width=True,
        hide_index=True,
    )


def render_data_intake() -> None:
    st.subheader("Data Intake")
    st.caption("Upload CSV files to override the bundled example data for this session.")
    uploaded_files = dict(st.session_state.get("uploaded_files", {}))
    upload_columns = st.columns(2)
    for index, (key, label) in enumerate(UPLOAD_SPECS.items()):
        with upload_columns[index % 2]:
            uploaded = st.file_uploader(label, type=["csv"], key=f"upload_{key}")
            if uploaded is not None:
                uploaded_files[key] = uploaded
    st.session_state["uploaded_files"] = uploaded_files

    if uploaded_files:
        st.success(f"{len(uploaded_files)} uploaded file(s) active in this session.")
    else:
        st.info("No uploads active. The app is using bundled example data.")

    loader = DataLoadService(get_file_overrides())
    tabs = st.tabs(["Collateral Positions", "Market Prices", "FX Rates", "Haircut Rules", "Inventory", "Margin Calls"])
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


def render_valuations() -> None:
    st.subheader("Valuations")
    try:
        results = ValuationService(get_file_overrides()).run_collateral_valuation()
        total_value = results["collateral_value"].dropna().sum()
        cols = st.columns(3)
        cols[0].metric("Positions", len(results))
        cols[1].metric("Collateral Value", f"{total_value:,.2f}")
        cols[2].metric("Warnings", int(results["warnings"].astype(bool).sum()))
        st.dataframe(results, use_container_width=True, hide_index=True)
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
            use_container_width=True,
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
