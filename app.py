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
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)


def render_header() -> None:
    cols = st.columns([2, 2, 2, 2])
    cols[0].metric("Business Date", settings.DEFAULT_BUSINESS_DATE)
    cols[1].metric("Environment", settings.DEFAULT_ENVIRONMENT)
    cols[2].metric("Process Status", "Ready")
    cols[3].metric("User Role", "Operator")


def render_dashboard() -> None:
    st.subheader("Daily Process Dashboard")
    loader = DataLoadService()
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
    loader = DataLoadService()
    tabs = st.tabs(["Collateral Positions", "Market Prices", "FX Rates", "Haircut Rules", "Inventory", "Margin Calls"])
    with tabs[0]:
        st.dataframe(loader.load_collateral_positions(), use_container_width=True, hide_index=True)
    with tabs[1]:
        st.dataframe(loader.load_market_prices(), use_container_width=True, hide_index=True)
    with tabs[2]:
        st.dataframe(loader.load_fx_rates(), use_container_width=True, hide_index=True)
    with tabs[3]:
        st.dataframe(loader.load_haircut_rules(), use_container_width=True, hide_index=True)
    with tabs[4]:
        st.dataframe(loader.load_inventory(), use_container_width=True, hide_index=True)
    with tabs[5]:
        st.dataframe(loader.load_margin_calls(), use_container_width=True, hide_index=True)


def render_valuations() -> None:
    st.subheader("Valuations")
    results = ValuationService().run_collateral_valuation()
    total_value = results["collateral_value"].dropna().sum()
    cols = st.columns(3)
    cols[0].metric("Positions", len(results))
    cols[1].metric("Collateral Value", f"{total_value:,.2f}")
    cols[2].metric("Warnings", int(results["warnings"].astype(bool).sum()))
    st.dataframe(results, use_container_width=True, hide_index=True)


def render_optimization() -> None:
    st.subheader("Collateral Optimization")
    preserve_cash = st.toggle("Preserve cash", value=True)
    allocations, summary = OptimizationService().optimize_first_margin_call(preserve_cash=preserve_cash)
    cols = st.columns(4)
    cols[0].metric("Status", summary["status"])
    cols[1].metric("Required", summary["required_amount"])
    cols[2].metric("Covered", summary["covered_amount"])
    cols[3].metric("Excess", summary["overcollateralization"])
    if summary["warnings"]:
        st.warning(summary["warnings"])
    st.dataframe(allocations, use_container_width=True, hide_index=True)


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

