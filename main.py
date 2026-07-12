from __future__ import annotations

import sys
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from nicegui import events, ui

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings
from csa_manager.services import DataLoadService, OptimizationService, ValuationService


TABLE_UPLOADS = {
    "collateral_positions": "Posiciones normalizadas de colateral",
    "market_prices": "Precios normalizados",
    "fx_rates": "Tipo de cambio FIX",
    "haircut_rules": "Reglas de haircut",
    "inventory": "Inventario disponible",
    "margin_calls": "Llamadas de margen",
}

ALADDIN_UPLOADS = {
    "posicion_otc": "POSICION_OTC.xlsx",
    "posicion_bnp_gs_ms": "POSICION_BNP_GS_MS.xlsx",
    "posicion_bbva": "POSICION_BBVA.xlsx",
    "movimientos_otc": "Movimientos_OTC.xlsx",
}

VECTOR_UPLOADS = {
    "deuda_076": "DEUDA.076",
    "derivados_077": "DERIVADOS.077",
}

session_files: dict[str, Path] = {}
vector_files: dict[str, Path] = {}


def save_upload(event: events.UploadEventArguments, key: str, target: dict[str, Path]) -> None:
    suffix = Path(event.name).suffix
    with NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_file.write(event.content.read())
        target[key] = Path(temp_file.name)
    ui.notify(f"{event.name} loaded", type="positive")


def dataframe_rows(dataframe) -> list[dict[str, Any]]:
    return dataframe.astype(str).to_dict(orient="records")


def dataframe_columns(dataframe) -> list[dict[str, str]]:
    return [{"name": column, "label": column, "field": column, "align": "left"} for column in dataframe.columns]


def show_dataframe(dataframe) -> None:
    ui.table(
        columns=dataframe_columns(dataframe),
        rows=dataframe_rows(dataframe),
        pagination=10,
    ).classes("w-full")


def read_vector_lines(path: Path, limit: int = 30) -> list[dict[str, str]]:
    text = path.read_text(encoding="latin-1", errors="replace")
    return [{"line": str(index + 1), "raw_text": line} for index, line in enumerate(text.splitlines()[:limit])]


def layout_header() -> None:
    with ui.row().classes("w-full items-center justify-between bg-slate-900 text-white p-4"):
        ui.label("CSA Manager OTC").classes("text-xl font-bold")
        ui.label(f"Fecha de proceso: {settings.DEFAULT_BUSINESS_DATE}")
        ui.label("Ambiente: LOCAL")


def dashboard() -> None:
    ui.label("Panel diario OTC").classes("text-2xl font-semibold")
    loader = DataLoadService(session_files)
    rows = [
        {"input": "Posiciones de colateral", "rows": str(len(loader.load_collateral_positions())), "status": "Cargado"},
        {"input": "Precios", "rows": str(len(loader.load_market_prices())), "status": "Cargado"},
        {"input": "FIX", "rows": str(len(loader.load_fx_rates())), "status": "Cargado"},
        {"input": "Haircuts", "rows": str(len(loader.load_haircut_rules())), "status": "Cargado"},
        {"input": "Inventario", "rows": str(len(loader.load_inventory())), "status": "Cargado"},
        {"input": "Llamadas de margen", "rows": str(len(loader.load_margin_calls())), "status": "Cargado"},
    ]
    ui.table(
        columns=[
            {"name": "input", "label": "Archivo / Dataset", "field": "input", "align": "left"},
            {"name": "rows", "label": "Registros", "field": "rows", "align": "left"},
            {"name": "status", "label": "Estado", "field": "status", "align": "left"},
        ],
        rows=rows,
    ).classes("w-full")


def data_intake() -> None:
    ui.label("Carga de archivos OTC").classes("text-2xl font-semibold")
    ui.label("Los archivos cargados viven solo en esta sesión. No se guarda histórico.").classes("text-slate-600")

    with ui.expansion("Archivos reales de Aladdin", icon="upload_file").classes("w-full"):
        with ui.grid(columns=2).classes("w-full gap-4"):
            for key, label in ALADDIN_UPLOADS.items():
                with ui.card().classes("w-full"):
                    ui.label(label).classes("font-medium")
                    ui.upload(
                        label=f"Subir {label}",
                        auto_upload=True,
                        on_upload=lambda event, upload_key=key: save_upload(event, upload_key, session_files),
                    ).props("accept=.xlsx,.xls")

    with ui.expansion("Datasets normalizados", icon="table_chart").classes("w-full"):
        with ui.grid(columns=2).classes("w-full gap-4"):
            for key, label in TABLE_UPLOADS.items():
                with ui.card().classes("w-full"):
                    ui.label(label).classes("font-medium")
                    ui.upload(
                        label=f"Subir {label}",
                        auto_upload=True,
                        on_upload=lambda event, upload_key=key: save_upload(event, upload_key, session_files),
                    ).props("accept=.csv,.xlsx,.xls")

    with ui.expansion("Vectores de precios TXT", icon="description").classes("w-full"):
        with ui.grid(columns=2).classes("w-full gap-4"):
            for key, label in VECTOR_UPLOADS.items():
                with ui.card().classes("w-full"):
                    ui.label(label).classes("font-medium")
                    ui.upload(
                        label=f"Subir {label}",
                        auto_upload=True,
                        on_upload=lambda event, upload_key=key: save_upload(event, upload_key, vector_files),
                    ).props("accept=.076,.077,.txt,.dat")

    loader = DataLoadService(session_files)
    with ui.tabs().classes("w-full") as tabs:
        tab_aladdin = ui.tab("Aladdin")
        tab_positions = ui.tab("Posiciones")
        tab_prices = ui.tab("Precios")
        tab_fx = ui.tab("FX")
        tab_rules = ui.tab("Haircuts")
        tab_inventory = ui.tab("Inventario")
        tab_calls = ui.tab("Margin Calls")
        tab_vectors = ui.tab("Vectores TXT")
    with ui.tab_panels(tabs, value=tab_aladdin).classes("w-full"):
        with ui.tab_panel(tab_aladdin):
            loader = DataLoadService(session_files)
            aladdin_tables = [
                ("POSICION_OTC", loader.load_aladdin_otc_positions()),
                ("POSICION_BNP_GS_MS", loader.load_aladdin_bnp_gs_ms_positions()),
                ("POSICION_BBVA", loader.load_aladdin_bbva_positions()),
                ("Movimientos_OTC", loader.load_aladdin_otc_movements()),
            ]
            loaded_any = False
            for name, dataframe in aladdin_tables:
                if dataframe is not None:
                    loaded_any = True
                    ui.label(name).classes("font-semibold")
                    show_dataframe(dataframe)
            if not loaded_any:
                ui.label("No hay archivos reales de Aladdin cargados en esta sesión.")
        with ui.tab_panel(tab_positions):
            show_dataframe(loader.load_collateral_positions())
        with ui.tab_panel(tab_prices):
            show_dataframe(loader.load_market_prices())
        with ui.tab_panel(tab_fx):
            show_dataframe(loader.load_fx_rates())
        with ui.tab_panel(tab_rules):
            show_dataframe(loader.load_haircut_rules())
        with ui.tab_panel(tab_inventory):
            show_dataframe(loader.load_inventory())
        with ui.tab_panel(tab_calls):
            show_dataframe(loader.load_margin_calls())
        with ui.tab_panel(tab_vectors):
            if not vector_files:
                ui.label("No hay vectores TXT cargados.")
            for key, path in vector_files.items():
                ui.label(VECTOR_UPLOADS[key]).classes("font-semibold")
                ui.table(
                    columns=[
                        {"name": "line", "label": "Line", "field": "line", "align": "left"},
                        {"name": "raw_text", "label": "Raw text", "field": "raw_text", "align": "left"},
                    ],
                    rows=read_vector_lines(path),
                    pagination=10,
                ).classes("w-full")


def valuations() -> None:
    ui.label("Valuaciones").classes("text-2xl font-semibold")
    try:
        results = ValuationService(session_files).run_collateral_valuation()
        total_value = results["collateral_value"].dropna().sum()
        with ui.row().classes("w-full gap-4"):
            with ui.card().classes("p-4"):
                ui.label("Posiciones").classes("text-slate-500")
                ui.label(str(len(results))).classes("text-2xl font-bold")
            with ui.card().classes("p-4"):
                ui.label("Valor de colateral").classes("text-slate-500")
                ui.label(f"{total_value:,.2f}").classes("text-2xl font-bold")
            with ui.card().classes("p-4"):
                ui.label("Alertas").classes("text-slate-500")
                ui.label(str(int(results["warnings"].astype(bool).sum()))).classes("text-2xl font-bold")
        show_dataframe(results)
    except Exception as exc:
        ui.notify(f"Valuation error: {exc}", type="negative")
        ui.label(str(exc)).classes("text-red-600")


def optimization() -> None:
    ui.label("Optimización de colateral").classes("text-2xl font-semibold")
    ui.label("Usa el monto solicitado por la contraparte cuando su llamada difiere de nuestra valuación interna.").classes("text-slate-600")
    preserve_cash = ui.switch("Preservar efectivo", value=True)
    amount = ui.number(
        "Monto de colateral solicitado por contraparte",
        value=6000.0,
        min=0.0,
        step=1000.0,
    ).classes("w-80")
    result_area = ui.column().classes("w-full")

    def run_optimization() -> None:
        result_area.clear()
        try:
            allocations, summary = OptimizationService(session_files).optimize_first_margin_call(
                preserve_cash=bool(preserve_cash.value),
                counterparty_required_amount=float(amount.value or 0),
            )
            with result_area:
                with ui.row().classes("w-full gap-4"):
                    for label, key in [
                        ("Status", "status"),
                        ("Required", "required_amount"),
                        ("Covered", "covered_amount"),
                        ("Excess", "overcollateralization"),
                    ]:
                        with ui.card().classes("p-4"):
                            ui.label(label).classes("text-slate-500")
                            ui.label(summary[key]).classes("text-xl font-bold")
                if summary["warnings"]:
                    ui.label(summary["warnings"]).classes("text-orange-600")
                show_dataframe(allocations)
        except Exception as exc:
            with result_area:
                ui.label(str(exc)).classes("text-red-600")

    ui.button("Optimizar colateral", on_click=run_optimization).props("color=primary")
    run_optimization()


@ui.page("/")
def index() -> None:
    layout_header()
    with ui.row().classes("w-full"):
        with ui.column().classes("w-64 min-h-screen bg-slate-100 p-4 gap-2"):
            ui.link("Panel diario", "#dashboard").classes("text-slate-800")
            ui.link("Carga OTC", "#data-intake").classes("text-slate-800")
            ui.link("Valuaciones", "#valuations").classes("text-slate-800")
            ui.link("Optimización", "#optimization").classes("text-slate-800")
        with ui.column().classes("flex-1 p-6 gap-8"):
            with ui.element("section").props("id=dashboard").classes("w-full"):
                dashboard()
            with ui.element("section").props("id=data-intake").classes("w-full"):
                data_intake()
            with ui.element("section").props("id=valuations").classes("w-full"):
                valuations()
            with ui.element("section").props("id=optimization").classes("w-full"):
                optimization()


ui.run(title="CSA Manager", host="0.0.0.0", port=8080, reload=False)
