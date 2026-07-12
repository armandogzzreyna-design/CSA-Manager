from __future__ import annotations

import re
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import requests
from nicegui import events, ui

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings
from csa_manager.services import DataLoadService, OptimizationService, ReportingService


FILES = {
    "validaciones_otc": {
        "label": "Validaciones OTC CSA",
        "hint": "Workbook operativo del día anterior o del proceso actual.",
        "accept": ".xlsx,.xls",
    },
    "posicion_otc": {
        "label": "POSICION_OTC",
        "hint": "Posición de derivados OTC desde Aladdin.",
        "accept": ".xlsx,.xls",
    },
    "posicion_bnp_gs_ms": {
        "label": "POSICION_BNP_GS_MS",
        "hint": "Colateral de BNP, Goldman y Morgan Stanley.",
        "accept": ".xlsx,.xls",
    },
    "posicion_bbva": {
        "label": "POSICION_BBVA",
        "hint": "Colateral BBVA con layout separado.",
        "accept": ".xlsx,.xls",
    },
    "movimientos_otc": {
        "label": "Movimientos_OTC",
        "hint": "Movimientos de títulos. Opcional.",
        "accept": ".xlsx,.xls",
    },
    "movimientos_cash": {
        "label": "Movimientos_CASH",
        "hint": "Movimientos de efectivo. Opcional.",
        "accept": ".xlsx,.xls",
    },
    "deuda_076": {
        "label": "Vector deuda .076",
        "hint": "Archivo TXT de vector de deuda.",
        "accept": ".076,.txt,.dat",
        "raw": True,
    },
    "derivados_077": {
        "label": "Vector derivados .077",
        "hint": "Archivo TXT de vector de derivados.",
        "accept": ".077,.txt,.dat",
        "raw": True,
    },
}

session_files: dict[str, Path] = {}
fix_value: float | None = None


def save_upload(event: events.UploadEventArguments, key: str) -> None:
    suffix = Path(event.name).suffix
    with NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_file.write(event.content.read())
        session_files[key] = Path(temp_file.name)
    ui.notify(f"{event.name} cargado", type="positive")


def fetch_banxico_fix() -> float:
    response = requests.get("https://www.banxico.org.mx/tipcamb/tipCamMIAction.do", timeout=15)
    response.raise_for_status()
    match = re.search(r"\b\d{1,2}\.\d{4,6}\b", response.text)
    if not match:
        raise ValueError("No se encontró un valor FIX en la página de Banxico.")
    return float(match.group(0))


def rows(dataframe) -> list[dict[str, Any]]:
    return dataframe.astype(str).to_dict(orient="records")


def columns(dataframe) -> list[dict[str, str]]:
    return [{"name": column, "label": column, "field": column, "align": "left"} for column in dataframe.columns]


def table(dataframe, rows_per_page: int = 12) -> None:
    ui.table(columns=columns(dataframe), rows=rows(dataframe), pagination=rows_per_page).classes("w-full")


def metric(label: str, value: str) -> None:
    with ui.card().classes("p-4 min-w-48 bg-white shadow-sm border"):
        ui.label(label).classes("text-xs uppercase text-slate-500 tracking-wide")
        ui.label(value).classes("text-2xl font-semibold text-slate-900")


def status_chip(loaded: bool) -> None:
    if loaded:
        ui.badge("Cargado", color="green")
    else:
        ui.badge("Pendiente", color="grey")


def read_raw_preview(path: Path, limit: int = 20) -> list[dict[str, str]]:
    text = path.read_text(encoding="latin-1", errors="replace")
    return [{"linea": str(i + 1), "texto": line} for i, line in enumerate(text.splitlines()[:limit])]


def refresh_views() -> None:
    for view in [carga_archivos, resumen_operativo, valuaciones, vectores, optimizacion, exportar]:
        try:
            view.refresh()
        except Exception:
            pass
    ui.notify("Archivos procesados. Las vistas fueron actualizadas.", type="positive")


def page_shell() -> None:
    ui.add_head_html(
        """
        <style>
        body { background: #f5f7fb; }
        .nicegui-content { padding: 0; }
        </style>
        """
    )
    with ui.row().classes("w-full items-center justify-between px-6 py-4 bg-slate-950 text-white"):
        with ui.column().classes("gap-0"):
            ui.label("CSA Manager OTC").classes("text-xl font-semibold")
            ui.label("Middle Office · CSA · Colateral OTC").classes("text-xs text-slate-300")
        with ui.row().classes("items-center gap-6"):
            ui.label(f"Fecha: {settings.DEFAULT_BUSINESS_DATE}").classes("text-sm")
            ui.label("Sin histórico · sesión temporal").classes("text-sm text-slate-300")


def upload_card(key: str, spec: dict[str, Any]) -> None:
    with ui.card().classes("w-full p-4 shadow-sm border bg-white"):
        with ui.row().classes("w-full justify-between items-start"):
            with ui.column().classes("gap-1"):
                ui.label(spec["label"]).classes("font-semibold text-slate-900")
                ui.label(spec["hint"]).classes("text-xs text-slate-500")
            status_chip(key in session_files)
        ui.upload(
            label="Subir archivo",
            auto_upload=True,
            on_upload=lambda event, upload_key=key: save_upload(event, upload_key),
        ).props(f"accept={spec['accept']}").classes("w-full")


@ui.refreshable
def carga_archivos() -> None:
    ui.label("Carga de archivos").classes("text-2xl font-semibold text-slate-900")
    ui.label("Carga únicamente los archivos del proceso OTC. Si no hubo movimientos, simplemente no subas ese archivo.").classes("text-slate-600")
    ui.label("Después de subir archivos, presiona Procesar archivos para actualizar las pestañas de Resumen, Valuaciones y Vectores.").classes("text-slate-500")

    with ui.grid(columns=2).classes("w-full gap-4"):
        for key, spec in FILES.items():
            upload_card(key, spec)

    with ui.row().classes("gap-2"):
        ui.button("Procesar archivos", on_click=refresh_views).props("color=primary icon=sync")
        ui.button("Limpiar sesión", on_click=lambda: (session_files.clear(), refresh_views())).props("outline icon=delete")

    ui.separator()
    ui.label("Tipo de cambio FIX").classes("text-lg font-semibold")
    ui.label("Puedes capturarlo manualmente o pedirle a la app que lo busque en Banxico, igual que el notebook original.").classes("text-slate-600")

    fix_input = ui.number("FIX manual", value=fix_value, min=0.0, step=0.0001, format="%.6f").classes("w-80")

    def save_fix() -> None:
        global fix_value
        fix_value = float(fix_input.value or 0)
        ui.notify(f"FIX guardado: {fix_value}", type="positive")

    def lookup_fix() -> None:
        global fix_value
        try:
            fix_value = fetch_banxico_fix()
            fix_input.value = fix_value
            ui.notify(f"FIX Banxico: {fix_value}", type="positive")
        except Exception as exc:
            ui.notify(f"No se pudo obtener FIX: {exc}", type="negative")

    with ui.row().classes("gap-2"):
        ui.button("Guardar FIX", on_click=save_fix).props("color=primary")
        ui.button("Buscar en Banxico", on_click=lookup_fix).props("outline")


@ui.refreshable
def resumen_operativo() -> None:
    loader = DataLoadService(session_files)
    sheets = ReportingService(session_files).workbook_preview()

    ui.label("Resumen operativo").classes("text-2xl font-semibold text-slate-900")
    with ui.row().classes("gap-4"):
        metric("Archivos cargados", str(len(session_files)))
        metric("Hojas del workbook", str(len(sheets)))
        metric("FIX", "-" if fix_value is None else f"{fix_value:.6f}")

    status_rows = []
    for key, spec in FILES.items():
        status_rows.append(
            {
                "archivo": spec["label"],
                "estado": "Cargado" if key in session_files else "Pendiente",
                "tipo": "TXT" if spec.get("raw") else "Excel",
            }
        )
    ui.table(
        columns=[
            {"name": "archivo", "label": "Archivo", "field": "archivo", "align": "left"},
            {"name": "tipo", "label": "Tipo", "field": "tipo", "align": "left"},
            {"name": "estado", "label": "Estado", "field": "estado", "align": "left"},
        ],
        rows=status_rows,
        pagination=20,
    ).classes("w-full")

    if any(key in session_files for key in ["posicion_otc", "posicion_bnp_gs_ms", "posicion_bbva", "movimientos_otc", "movimientos_cash"]):
        ui.label("Vista rápida de archivos Aladdin").classes("text-lg font-semibold")
        previews = [
            ("POSICION_OTC", loader.load_aladdin_otc_positions()),
            ("POSICION_BNP_GS_MS", loader.load_aladdin_bnp_gs_ms_positions()),
            ("POSICION_BBVA", loader.load_aladdin_bbva_positions()),
            ("Movimientos_OTC", loader.load_aladdin_otc_movements()),
            ("Movimientos_CASH", loader.load_aladdin_cash_movements()),
        ]
        for name, dataframe in previews:
            if dataframe is not None:
                with ui.expansion(f"{name} · {len(dataframe)} registros", icon="table_chart").classes("w-full"):
                    table(dataframe)


@ui.refreshable
def valuaciones() -> None:
    ui.label("Valuaciones y llamadas").classes("text-2xl font-semibold text-slate-900")
    sheets = ReportingService(session_files).workbook_preview()
    if sheets:
        ui.label("Mostrando el workbook operativo cargado. Esta vista replica las hojas que usan en el proceso actual.").classes("text-slate-600")
        for sheet_name in ["VALUACION", "TOTALES", "POSICIONES", "CASH", "COLATERALES"]:
            if sheet_name in sheets:
                with ui.expansion(sheet_name, icon="table_chart", value=sheet_name == "VALUACION").classes("w-full"):
                    table(sheets[sheet_name], rows_per_page=15)
        return

    ui.label("Sube Validaciones OTC CSA para ver las valuaciones y llamadas con el layout operativo.").classes("text-orange-700")


@ui.refreshable
def vectores() -> None:
    ui.label("Vectores TXT").classes("text-2xl font-semibold text-slate-900")
    ui.label("Vista previa de archivos .076 y .077. Por ahora no se guarda histórico y solo se muestran primeras líneas.").classes("text-slate-600")

    loaded_any = False
    for key in ["deuda_076", "derivados_077"]:
        if key in session_files:
            loaded_any = True
            with ui.expansion(FILES[key]["label"], icon="description", value=True).classes("w-full"):
                ui.table(
                    columns=[
                        {"name": "linea", "label": "Línea", "field": "linea", "align": "left"},
                        {"name": "texto", "label": "Texto", "field": "texto", "align": "left"},
                    ],
                    rows=read_raw_preview(session_files[key]),
                    pagination=20,
                ).classes("w-full")
    if not loaded_any:
        ui.label("No hay vectores cargados.").classes("text-slate-600")


@ui.refreshable
def optimizacion() -> None:
    ui.label("Optimización de colateral").classes("text-2xl font-semibold text-slate-900")
    ui.label("Usa el monto solicitado por contraparte. Este monto puede diferir de nuestra valuación interna.").classes("text-slate-600")

    with ui.card().classes("w-full p-4 bg-blue-50 border border-blue-100 shadow-sm"):
        ui.markdown(
            """
            **¿Qué significa preservar efectivo?**

            - **Activado:** el optimizador intenta usar primero títulos elegibles y deja el efectivo como último recurso.
            - **Desactivado:** el optimizador puede usar efectivo primero si cubre la llamada de forma más directa.
            - El monto base de optimización es el **monto solicitado por la contraparte**, porque operativamente se envía lo que ellos llaman aunque nuestra valuación interna sea diferente.
            """
        ).classes("text-sm text-slate-700")

    preserve_cash = ui.switch("Preservar efectivo", value=True)
    amount = ui.number("Monto solicitado por contraparte", value=6000.0, min=0.0, step=1000.0).classes("w-80")
    result_area = ui.column().classes("w-full")

    def run() -> None:
        result_area.clear()
        try:
            allocations, summary = OptimizationService(session_files).optimize_first_margin_call(
                preserve_cash=bool(preserve_cash.value),
                counterparty_required_amount=float(amount.value or 0),
            )
            with result_area:
                with ui.row().classes("gap-4"):
                    metric("Estado", summary["status"])
                    metric("Requerido", summary["required_amount"])
                    metric("Cubierto", summary["covered_amount"])
                    metric("Exceso", summary["overcollateralization"])
                if summary["warnings"]:
                    ui.label(summary["warnings"]).classes("text-orange-700")
                table(allocations)
        except Exception as exc:
            with result_area:
                ui.label("No se pudo optimizar con los datos actuales.").classes("text-red-700")
                ui.label(str(exc)).classes("text-red-600")

    ui.button("Optimizar colateral", on_click=run).props("color=primary icon=auto_awesome")
    run()


@ui.refreshable
def exportar() -> None:
    ui.label("Exportar resultado").classes("text-2xl font-semibold text-slate-900")
    ui.label("Genera un Excel con las hojas cargadas y las vistas calculadas en esta sesión.").classes("text-slate-600")

    def export_excel() -> None:
        output_path = Path(NamedTemporaryFile(delete=False, suffix=".xlsx").name)
        ReportingService(session_files).export_session_workbook(output_path)
        ui.download(str(output_path), filename="CSA_Manager_OTC_resultado.xlsx")

    ui.button("Exportar Excel", on_click=export_excel).props("color=primary icon=download")


@ui.page("/")
def index() -> None:
    page_shell()
    with ui.column().classes("w-full max-w-7xl mx-auto p-6 gap-6"):
        with ui.tabs().classes("w-full bg-white rounded shadow-sm") as tabs:
            tab_carga = ui.tab("Carga")
            tab_resumen = ui.tab("Resumen")
            tab_valuaciones = ui.tab("Valuaciones")
            tab_vectores = ui.tab("Vectores")
            tab_optimizacion = ui.tab("Optimización")
            tab_exportar = ui.tab("Exportar")

        with ui.tab_panels(tabs, value=tab_carga).classes("w-full bg-transparent"):
            with ui.tab_panel(tab_carga).classes("gap-4"):
                carga_archivos()
            with ui.tab_panel(tab_resumen).classes("gap-4"):
                resumen_operativo()
            with ui.tab_panel(tab_valuaciones).classes("gap-4"):
                valuaciones()
            with ui.tab_panel(tab_vectores).classes("gap-4"):
                vectores()
            with ui.tab_panel(tab_optimizacion).classes("gap-4"):
                optimizacion()
            with ui.tab_panel(tab_exportar).classes("gap-4"):
                exportar()


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(title="CSA Manager OTC", host="0.0.0.0", port=8080, reload=False)
