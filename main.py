from __future__ import annotations

import re
import sys
from numbers import Number
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import requests
from nicegui import events, run as nicegui_run, ui

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings
from csa_manager.services import DataLoadService, OperationalAnalyticsService, OptimizationService, ReportingService


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
session_file_meta: dict[str, dict[str, str]] = {}
fix_value: float | None = None


def configure_nicegui_runtime() -> None:
    original_setup = nicegui_run.setup

    def safe_setup() -> None:
        try:
            original_setup()
        except PermissionError:
            nicegui_run.process_pool = None

    nicegui_run.setup = safe_setup


def save_upload(event: events.UploadEventArguments, key: str) -> None:
    suffix = Path(event.name).suffix
    content = event.content.read()
    with NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_file.write(content)
        session_files[key] = Path(temp_file.name)
    session_file_meta[key] = {
        "archivo": FILES[key]["label"],
        "nombre": event.name,
        "tamano": f"{len(content):,} bytes",
        "estado": "Cargado",
    }
    ui.notify(f"{event.name} cargado. Presiona Procesar archivos o revisa Resumen.", type="positive")
    try:
        carga_archivos.refresh()
        resumen_operativo.refresh()
    except Exception:
        pass


def register_local_file(key: str, path: Path) -> None:
    if not path.exists():
        ui.notify(f"No existe: {path}", type="warning")
        return
    session_files[key] = path
    session_file_meta[key] = {
        "archivo": FILES[key]["label"],
        "nombre": path.name,
        "tamano": f"{path.stat().st_size:,} bytes",
        "estado": "Cargado desde Downloads",
    }


def load_downloads_example_files() -> None:
    downloads = Path.home() / "Downloads"
    candidates = {
        "validaciones_otc": downloads / "Validaciones OTC CSA 10.07.2026.xlsx",
        "posicion_otc": downloads / "POSICION_OTC.xlsx",
        "posicion_bnp_gs_ms": downloads / "POSICION_BNP_GS_MS.xlsx",
        "posicion_bbva": downloads / "POSICION_BBVA.xlsx",
        "movimientos_otc": downloads / "Movimientos_OTC.xlsx",
        "movimientos_cash": downloads / "Movimientos_CASH.xlsx",
        "deuda_076": downloads / "20260709.076",
        "derivados_077": downloads / "20260709.077",
    }
    for key, path in candidates.items():
        register_local_file(key, path)
    refresh_views()


def fetch_banxico_fix() -> float:
    response = requests.get("https://www.banxico.org.mx/tipcamb/tipCamMIAction.do", timeout=15)
    response.raise_for_status()
    match = re.search(r"\b\d{1,2}\.\d{4,6}\b", response.text)
    if not match:
        raise ValueError("No se encontró un valor FIX en la página de Banxico.")
    return float(match.group(0))


def rows(dataframe) -> list[dict[str, Any]]:
    def fmt(value: object, pattern: str) -> str:
        if value is None:
            return ""
        if isinstance(value, Number):
            try:
                if value != value:
                    return ""
                return pattern.format(float(value))
            except Exception:
                return str(value)
        return str(value)

    formatted = dataframe.copy()
    for column in formatted.columns:
        upper = str(column).upper()
        if not hasattr(formatted[column], "dtype"):
            continue
        if "PRECIO" in upper or "HAIRCUT" in upper or "FIX" in upper:
            formatted[column] = formatted[column].map(lambda value: fmt(value, "{:,.6f}"))
        elif any(token in upper for token in ["VALUACION", "MONTO", "CASH", "COLATERAL", "FALTANTE", "EXCESO"]):
            formatted[column] = formatted[column].map(lambda value: fmt(value, "{:,.2f}"))
        elif any(token in upper for token in ["TITULOS", "NOCIONAL", "DIAS"]):
            formatted[column] = formatted[column].map(lambda value: fmt(value, "{:,.0f}"))
        else:
            formatted[column] = formatted[column].astype(str)
    return formatted.to_dict(orient="records")


def columns(dataframe) -> list[dict[str, str]]:
    return [{"name": column, "label": column, "field": column, "align": "left"} for column in dataframe.columns]


def table(dataframe, rows_per_page: int = 12) -> None:
    ui.table(columns=columns(dataframe), rows=rows(dataframe), pagination=rows_per_page).classes("w-full")


def valuation_table(dataframe, rows_per_page: int = 20) -> None:
    display = dataframe.copy()
    display["SEMAFORO_COLOR"] = display["SEMAFORO"].map({"ROJO": "red", "VERDE": "green"}).fillna("grey")
    table_columns = [
        {"name": column, "label": column, "field": column, "align": "left"}
        for column in display.columns
        if column != "SEMAFORO_COLOR"
    ]
    valuation_rows = rows(display)
    component = ui.table(columns=table_columns, rows=valuation_rows, pagination=rows_per_page).classes("w-full")
    component.add_slot(
        "body-cell-SEMAFORO",
        """
        <q-td :props="props">
          <q-badge :color="props.row.SEMAFORO_COLOR" :label="props.value" />
        </q-td>
        """,
    )


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
    for view in [carga_archivos, resumen_operativo, valuaciones, optimizacion, exportar]:
        try:
            view.refresh()
        except Exception:
            pass
    ui.notify("Archivos procesados. Las vistas fueron actualizadas.", type="positive")


def render_error(context: str, exc: Exception) -> None:
    with ui.card().classes("w-full p-4 bg-red-50 border border-red-200"):
        ui.label(f"No se pudo renderizar {context}.").classes("font-semibold text-red-800")
        ui.label(str(exc)).classes("text-red-700")


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
    ui.label("Después de subir archivos, presiona Procesar archivos para actualizar Resumen, Valuaciones y Optimización.").classes("text-slate-500")

    with ui.card().classes("w-full p-4 bg-amber-50 border border-amber-200 shadow-sm"):
        ui.label("Modo local de prueba").classes("font-semibold text-amber-900")
        ui.label("Si el upload del navegador no carga, usa este botón para leer directamente los archivos desde tu carpeta Downloads.").classes("text-amber-800")
        ui.button("Cargar archivos desde Downloads", on_click=load_downloads_example_files).props("color=warning icon=folder_open")

    with ui.grid(columns=2).classes("w-full gap-4"):
        for key, spec in FILES.items():
            upload_card(key, spec)

    with ui.row().classes("gap-2"):
        ui.button("Procesar archivos", on_click=refresh_views).props("color=primary icon=sync")
        ui.button("Limpiar sesión", on_click=lambda: (session_files.clear(), session_file_meta.clear(), refresh_views())).props("outline icon=delete")

    ui.label("Archivos recibidos").classes("text-lg font-semibold")
    if session_file_meta:
        ui.table(
            columns=[
                {"name": "archivo", "label": "Tipo", "field": "archivo", "align": "left"},
                {"name": "nombre", "label": "Nombre recibido", "field": "nombre", "align": "left"},
                {"name": "tamano", "label": "Tamaño", "field": "tamano", "align": "left"},
                {"name": "estado", "label": "Estado", "field": "estado", "align": "left"},
            ],
            rows=list(session_file_meta.values()),
            pagination=20,
        ).classes("w-full")
    else:
        ui.label("Aún no hay archivos recibidos en esta sesión.").classes("text-slate-500")

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
    try:
        loader = DataLoadService(session_files)
        sheets = ReportingService(session_files).workbook_preview()
    except Exception as exc:
        render_error("Resumen", exc)
        return

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
    try:
        sheets = ReportingService(session_files).workbook_preview()
        analytics = OperationalAnalyticsService(session_files)
    except Exception as exc:
        render_error("Valuaciones", exc)
        return
    if sheets:
        ui.label("Resumen consolidado por contraparte y SIEFORE en USD. Rojo: monto a entregar mayor o igual a 400,000 USD. Verde: menor al umbral.").classes("text-slate-600")
        summary = analytics.valuation_summary()
        if not summary.empty:
            red_count = int((summary["SEMAFORO"] == "ROJO").sum())
            green_count = int((summary["SEMAFORO"] == "VERDE").sum())
            with ui.row().classes("gap-4"):
                metric("Valuación OTC USD", f"{summary['VALUACION_OTC_USD'].sum():,.2f}")
                metric("Colateral valuado USD", f"{summary['VALUACION_COLATERAL_USD'].sum():,.2f}")
                metric("Cash neto USD", f"{summary['VALUACION_CASH_USD'].sum():,.2f}")
                metric("Llamadas contraparte USD", f"{summary['MONTO_CONTRAPARTE_USD'].sum():,.2f}")
                metric("Rojas", str(red_count))
                metric("Verdes", str(green_count))
            valuation_table(summary, rows_per_page=20)

            with ui.expansion("Valuaciones por contraparte", icon="account_balance_wallet", value=True).classes("w-full"):
                for counterparty_name, counterparty_summary in summary.groupby("CONTRAPARTE", sort=True):
                    total_call = counterparty_summary["MONTO_CONTRAPARTE_USD"].sum()
                    red_rows = int((counterparty_summary["SEMAFORO"] == "ROJO").sum())
                    with ui.expansion(f"{counterparty_name} · llamadas {total_call:,.2f} USD · rojas {red_rows}", icon="business").classes("w-full"):
                        valuation_table(counterparty_summary.reset_index(drop=True), rows_per_page=12)

        with ui.expansion("Todas las posiciones OTC", icon="analytics").classes("w-full"):
            derivative_positions = analytics.derivative_positions()
            if derivative_positions.empty:
                ui.label("No hay posiciones OTC cargadas.")
            else:
                table(derivative_positions, rows_per_page=20)

        with ui.expansion("Todo el colateral valuado", icon="account_balance").classes("w-full"):
            collateral_positions = analytics.collateral_positions()
            if collateral_positions.empty:
                ui.label("No hay colateral valuado cargado.")
            else:
                table(collateral_positions, rows_per_page=20)

        with ui.expansion("Hojas originales del workbook", icon="table_chart").classes("w-full"):
            for sheet_name in ["VALUACION", "TOTALES", "POSICIONES", "CASH", "COLATERALES"]:
                if sheet_name in sheets:
                    with ui.expansion(sheet_name, icon="table_chart", value=sheet_name == "VALUACION").classes("w-full"):
                        table(sheets[sheet_name], rows_per_page=15)
        return

    ui.label("Sube Validaciones OTC CSA para ver las valuaciones y llamadas con el layout operativo.").classes("text-orange-700")


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
    analytics = OperationalAnalyticsService(session_files)
    summary = analytics.valuation_summary()
    scenario_options: dict[str, dict[str, Any]] = {}
    if not summary.empty:
        for row in summary.itertuples(index=False):
            currency = row.MONEDA_UMBRAL
            counterparty_amount = (
                float(row.MONTO_CONTRAPARTE_MXN) if currency == "MXN" else float(row.MONTO_CONTRAPARTE_USD)
            )
            internal_amount = (
                float(row.MONTO_A_ENTREGAR_INTERNO_MXN)
                if currency == "MXN"
                else float(row.MONTO_A_ENTREGAR_INTERNO_USD)
            )
            scenario_amount = counterparty_amount if counterparty_amount > 0 else internal_amount
            status = "contraparte" if counterparty_amount > 0 else "interno"
            label = f"{row.CONTRAPARTE} | {row.SIEFORE} | {scenario_amount:,.2f} {currency} | {status}"
            scenario_options[label] = {
                "counterparty": row.CONTRAPARTE,
                "fund": row.SIEFORE,
                "amount": scenario_amount,
                "currency": currency,
            }

    first_label = next(iter(scenario_options), None)
    first_scenario = scenario_options.get(first_label, {"counterparty": "GOLDMAN", "fund": "INVER70", "amount": 6000.0, "currency": "USD"})
    selected_scenario = ui.select(
        list(scenario_options.keys()),
        value=first_label,
        label="Contraparte / SIEFORE",
        on_change=lambda _: apply_selected_scenario(),
    ).classes("w-96")
    counterparty = ui.input("Contraparte", value=first_scenario["counterparty"]).classes("w-80")
    fund = ui.input("SIEFORE", value=first_scenario["fund"]).classes("w-80")
    currency = ui.input("Moneda", value=first_scenario["currency"]).props("readonly").classes("w-32")
    amount = ui.number("Monto a optimizar", value=first_scenario["amount"], min=0.0, step=1000.0).classes("w-80")
    action = ui.select(["Enviar colateral", "Sustituir colateral"], value="Enviar colateral", label="Acción").classes("w-80")
    result_area = ui.column().classes("w-full")

    def apply_selected_scenario() -> None:
        selected = scenario_options.get(selected_scenario.value)
        if not selected:
            ui.notify("Selecciona una contraparte/SIEFORE primero.", type="warning")
            return
        counterparty.value = selected["counterparty"]
        fund.value = selected["fund"]
        amount.value = selected["amount"]
        currency.value = selected["currency"]
        ui.notify("Escenario aplicado al formulario.", type="positive")

    if scenario_options:
        ui.button("Usar selección", on_click=apply_selected_scenario).props("outline icon=check")
    else:
        ui.label("No se detectaron valuaciones consolidadas. Puedes capturar contraparte, SIEFORE y monto manualmente.").classes("text-orange-700")

    def run() -> None:
        result_area.clear()
        try:
            recommendation = analytics.collateral_recommendation(
                counterparty=str(counterparty.value or "").upper(),
                fund=str(fund.value or "").upper(),
                amount=float(amount.value or 0),
                preserve_cash=bool(preserve_cash.value),
            )
            with result_area:
                ui.label(f"Acción: {action.value}").classes("font-semibold")
                if action.value == "Sustituir colateral":
                    ui.label("Modo sustitución: por ahora se calcula el colateral de reemplazo sugerido. Después agregaremos selección del colateral que quieres retirar y workflow de aprobación.").classes("text-slate-600")
                if recommendation.empty:
                    ui.label("No hay colateral disponible para esa contraparte/SIEFORE en TOTALES.").classes("text-orange-700")
                    return
                covered = recommendation["VALUACION_CUBIERTA"].sum()
                missing = recommendation["FALTANTE"].max()
                selected_currency = str(currency.value or "USD")
                with ui.row().classes("gap-4"):
                    metric(f"Monto solicitado {selected_currency}", f"{float(amount.value or 0):,.2f}")
                    metric(f"Cubierto sugerido {selected_currency}", f"{covered:,.2f}")
                    metric(f"Faltante {selected_currency}", f"{missing:,.2f}")
                    metric("Instrumentos", str(len(recommendation)))
                table(recommendation)
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
            tab_optimizacion = ui.tab("Optimización")
            tab_exportar = ui.tab("Exportar")

        with ui.tab_panels(tabs, value=tab_carga).classes("w-full bg-transparent"):
            with ui.tab_panel(tab_carga).classes("gap-4"):
                carga_archivos()
            with ui.tab_panel(tab_resumen).classes("gap-4"):
                resumen_operativo()
            with ui.tab_panel(tab_valuaciones).classes("gap-4"):
                valuaciones()
            with ui.tab_panel(tab_optimizacion).classes("gap-4"):
                optimizacion()
            with ui.tab_panel(tab_exportar).classes("gap-4"):
                exportar()


if __name__ in {"__main__", "__mp_main__"}:
    configure_nicegui_runtime()
    ui.run(title="CSA Manager OTC", host="127.0.0.1", port=8080, reload=False)
