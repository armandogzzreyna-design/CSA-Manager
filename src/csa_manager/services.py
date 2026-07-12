from __future__ import annotations

import math
from dataclasses import asdict
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd

from config import settings
from csa_manager.importers import (
    AladdinBBVAPositionImporter,
    AladdinBNPGSMSPositionImporter,
    AladdinCashMovementImporter,
    AladdinOTCMovementImporter,
    AladdinOTCPositionImporter,
    CollateralPositionImporter,
    FXRateImporter,
    HaircutRuleImporter,
    InventoryImporter,
    MarginCallImporter,
    MarketPriceImporter,
)
from csa_manager.models import (
    CollateralPositionInput,
    FXRate,
    HaircutRule,
    InventoryItem,
    MarginCall,
    MarketPrice,
    OptimizationObjective,
)
from csa_manager.optimization_engine import CollateralOptimizationEngine
from csa_manager.valuation_engine import CollateralValuationEngine


class DataLoadService:
    def __init__(self, file_overrides: dict[str, Any] | None = None) -> None:
        self.file_overrides = file_overrides or {}

    def _source(self, key: str, default_path: Path) -> Path | Any:
        uploaded_file = self.file_overrides.get(key)
        if uploaded_file is not None:
            uploaded_file.seek(0)
            return uploaded_file
        return default_path

    def load_collateral_positions(self) -> pd.DataFrame:
        return CollateralPositionImporter().import_file(
            self._source("collateral_positions", settings.COLLATERAL_POSITIONS_FILE)
        ).dataframe

    def load_market_prices(self) -> pd.DataFrame:
        return MarketPriceImporter().import_file(
            self._source("market_prices", settings.MARKET_PRICES_FILE)
        ).dataframe

    def load_fx_rates(self) -> pd.DataFrame:
        return FXRateImporter().import_file(
            self._source("fx_rates", settings.FX_RATES_FILE)
        ).dataframe

    def load_haircut_rules(self) -> pd.DataFrame:
        return HaircutRuleImporter().import_file(
            self._source("haircut_rules", settings.HAIRCUT_RULES_FILE)
        ).dataframe

    def load_inventory(self) -> pd.DataFrame:
        return InventoryImporter().import_file(
            self._source("inventory", settings.INVENTORY_FILE)
        ).dataframe

    def load_margin_calls(self) -> pd.DataFrame:
        return MarginCallImporter().import_file(
            self._source("margin_calls", settings.MARGIN_CALLS_FILE)
        ).dataframe

    def load_aladdin_bnp_gs_ms_positions(self) -> pd.DataFrame | None:
        source = self.file_overrides.get("posicion_bnp_gs_ms")
        if source is None:
            return None
        return AladdinBNPGSMSPositionImporter().import_file(source).dataframe

    def load_aladdin_bbva_positions(self) -> pd.DataFrame | None:
        source = self.file_overrides.get("posicion_bbva")
        if source is None:
            return None
        return AladdinBBVAPositionImporter().import_file(source).dataframe

    def load_aladdin_otc_positions(self) -> pd.DataFrame | None:
        source = self.file_overrides.get("posicion_otc")
        if source is None:
            return None
        return AladdinOTCPositionImporter().import_file(source).dataframe

    def load_aladdin_otc_movements(self) -> pd.DataFrame | None:
        source = self.file_overrides.get("movimientos_otc")
        if source is None:
            return None
        return AladdinOTCMovementImporter().import_file(source).dataframe

    def load_aladdin_cash_movements(self) -> pd.DataFrame | None:
        source = self.file_overrides.get("movimientos_cash")
        if source is None:
            return None
        return AladdinCashMovementImporter().import_file(source).dataframe

    def load_validation_workbook_sheet(self, sheet_name: str) -> pd.DataFrame | None:
        source = self.file_overrides.get("validaciones_otc")
        if source is None:
            return None
        if hasattr(source, "seek"):
            source.seek(0)
        return pd.read_excel(source, sheet_name=sheet_name)


class MappingService:
    @staticmethod
    def positions_from_dataframe(df: pd.DataFrame) -> list[CollateralPositionInput]:
        return [
            CollateralPositionInput(
                position_id=row.position_id,
                counterparty_code=row.counterparty_code,
                fund_code=row.fund_code,
                portfolio_code=row.portfolio_code,
                instrument_code=row.instrument_code,
                quantity=row.quantity,
                valuation_date=row.valuation_date,
                source=row.source,
            )
            for row in df.itertuples(index=False)
        ]

    @staticmethod
    def prices_from_dataframe(df: pd.DataFrame) -> list[MarketPrice]:
        return [
            MarketPrice(
                price_id=row.price_id,
                emission_code=row.emission_code,
                dirty_price=row.dirty_price,
                currency=row.currency,
                valuation_date=row.valuation_date,
                source=row.source,
                isin=None if pd.isna(row.isin) else row.isin,
            )
            for row in df.itertuples(index=False)
        ]

    @staticmethod
    def fx_from_dataframe(df: pd.DataFrame) -> FXRate:
        row = df.iloc[0]
        return FXRate(
            rate_date=row["rate_date"],
            base_currency=row["base_currency"],
            quote_currency=row["quote_currency"],
            rate=row["rate"],
            source=row["source"],
        )

    @staticmethod
    def haircut_rules_from_dataframe(df: pd.DataFrame) -> list[HaircutRule]:
        rules: list[HaircutRule] = []
        for row in df.itertuples(index=False):
            min_days = None if pd.isna(row.min_days_to_maturity) else int(row.min_days_to_maturity)
            max_days = None if pd.isna(row.max_days_to_maturity) else int(row.max_days_to_maturity)
            rules.append(
                HaircutRule(
                    rule_id=row.rule_id,
                    counterparty_pattern=row.counterparty_pattern,
                    match_type=row.match_type,
                    min_days_to_maturity=min_days,
                    max_days_to_maturity=max_days,
                    factor=row.factor,
                    priority=row.priority,
                    description=row.description,
                )
            )
        return rules

    @staticmethod
    def inventory_from_dataframe(df: pd.DataFrame) -> list[InventoryItem]:
        return [
            InventoryItem(
                inventory_id=row.inventory_id,
                asset_id=row.asset_id,
                counterparty_code=row.counterparty_code,
                fund_code=row.fund_code,
                asset_type=row.asset_type,
                currency=row.currency,
                available_quantity=row.available_quantity,
                unit_collateral_value=row.unit_collateral_value,
                is_cash=row.is_cash,
                is_eligible=row.is_eligible,
                opportunity_cost=row.opportunity_cost,
                settlement_lag_days=row.settlement_lag_days,
            )
            for row in df.itertuples(index=False)
        ]

    @staticmethod
    def margin_calls_from_dataframe(df: pd.DataFrame) -> list[MarginCall]:
        return [
            MarginCall(
                margin_call_id=row.margin_call_id,
                counterparty_code=row.counterparty_code,
                csa_id=row.csa_id,
                required_amount=row.required_amount,
                currency=row.currency,
                direction=row.direction,
                due_date=row.due_date,
            )
            for row in df.itertuples(index=False)
        ]


class ValuationService:
    def __init__(self, file_overrides: dict[str, Any] | None = None) -> None:
        self.file_overrides = file_overrides or {}

    @staticmethod
    def _display_number(value: object) -> float | None:
        if pd.isna(value):
            return None
        return float(value)

    def run_collateral_valuation(self) -> pd.DataFrame:
        loader = DataLoadService(self.file_overrides)
        mapper = MappingService()
        positions = mapper.positions_from_dataframe(loader.load_collateral_positions())
        prices = mapper.prices_from_dataframe(loader.load_market_prices())
        fx_rate = mapper.fx_from_dataframe(loader.load_fx_rates())
        rules = mapper.haircut_rules_from_dataframe(loader.load_haircut_rules())
        engine = CollateralValuationEngine()
        results = [engine.value_position(position, prices, fx_rate, rules) for position in positions]
        return pd.DataFrame(
            [
                {
                    "position_id": result.position_id,
                    "counterparty_code": result.counterparty_code,
                    "fund_code": result.fund_code,
                    "instrument_code": result.instrument_code,
                    "quantity": self._display_number(result.quantity),
                    "dirty_price": self._display_number(result.dirty_price),
                    "price_usd": self._display_number(result.price_usd),
                    "days_to_maturity": result.days_to_maturity,
                    "haircut_factor": self._display_number(result.haircut_factor),
                    "haircut_price": self._display_number(result.haircut_price),
                    "collateral_value": self._display_number(result.collateral_value),
                    "status": result.status,
                    "warnings": "; ".join(result.warnings),
                }
                for result in results
            ]
        )


class OptimizationService:
    def __init__(self, file_overrides: dict[str, Any] | None = None) -> None:
        self.file_overrides = file_overrides or {}

    def optimize_first_margin_call(
        self,
        preserve_cash: bool = True,
        counterparty_required_amount: float | None = None,
    ) -> tuple[pd.DataFrame, dict[str, str]]:
        loader = DataLoadService(self.file_overrides)
        mapper = MappingService()
        margin_calls = mapper.margin_calls_from_dataframe(loader.load_margin_calls())
        inventory = mapper.inventory_from_dataframe(loader.load_inventory())
        margin_call = margin_calls[0]
        if counterparty_required_amount is not None:
            margin_call = MarginCall(
                margin_call_id=margin_call.margin_call_id,
                counterparty_code=margin_call.counterparty_code,
                csa_id=margin_call.csa_id,
                required_amount=Decimal(str(counterparty_required_amount)),
                currency=margin_call.currency,
                direction=margin_call.direction,
                due_date=margin_call.due_date,
            )
        engine = CollateralOptimizationEngine()
        result = engine.optimize_margin_call(
            margin_call=margin_call,
            inventory=inventory,
            objective=OptimizationObjective(preserve_cash=preserve_cash),
        )
        allocations = pd.DataFrame([asdict(allocation) for allocation in result.allocations])
        for column in ["quantity", "collateral_value"]:
            if column in allocations.columns:
                allocations[column] = allocations[column].astype(float)
        summary = {
            "status": result.status,
            "required_amount": str(result.required_amount),
            "covered_amount": str(result.covered_amount),
            "overcollateralization": str(result.overcollateralization),
            "warnings": "; ".join(result.warnings),
        }
        return allocations, summary


class ReportingService:
    def __init__(self, file_overrides: dict[str, Any] | None = None) -> None:
        self.file_overrides = file_overrides or {}

    def workbook_preview(self) -> dict[str, pd.DataFrame]:
        loader = DataLoadService(self.file_overrides)
        sheets: dict[str, pd.DataFrame] = {}
        for sheet_name in ["CASH", "POSICIONES", "TOTALES", "VALUACION", "COLATERALES"]:
            try:
                dataframe = loader.load_validation_workbook_sheet(sheet_name)
            except Exception:
                dataframe = None
            if dataframe is not None:
                sheets[sheet_name] = dataframe
        return sheets

    def export_session_workbook(self, output_path: Path) -> Path:
        loader = DataLoadService(self.file_overrides)
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            workbook_sheets = self.workbook_preview()
            if workbook_sheets:
                for sheet_name, dataframe in workbook_sheets.items():
                    dataframe.to_excel(writer, sheet_name=sheet_name[:31], index=False)
            else:
                loader.load_collateral_positions().to_excel(writer, sheet_name="POSICIONES_INPUT", index=False)
                loader.load_market_prices().to_excel(writer, sheet_name="PRECIOS_INPUT", index=False)
                loader.load_fx_rates().to_excel(writer, sheet_name="FX_INPUT", index=False)
                loader.load_haircut_rules().to_excel(writer, sheet_name="HAIRCUTS_INPUT", index=False)

            for sheet_name, dataframe in [
                ("ALADDIN_OTC", loader.load_aladdin_otc_positions()),
                ("ALADDIN_COLATERAL", loader.load_aladdin_bnp_gs_ms_positions()),
                ("ALADDIN_BBVA", loader.load_aladdin_bbva_positions()),
                ("MOV_OTC", loader.load_aladdin_otc_movements()),
                ("MOV_CASH", loader.load_aladdin_cash_movements()),
            ]:
                if dataframe is not None:
                    dataframe.to_excel(writer, sheet_name=sheet_name, index=False)

            try:
                ValuationService(self.file_overrides).run_collateral_valuation().to_excel(
                    writer, sheet_name="VALUACION_APP", index=False
                )
            except Exception:
                pass
        return output_path


class OperationalAnalyticsService:
    DELIVERY_THRESHOLD_USD = 400_000.0
    BBVA_DELIVERY_THRESHOLD_MXN = 10_000_000.0

    COUNTERPARTY_ALIASES = {
        "CBGSMX": "GOLDMAN",
        "GOLDMAN": "GOLDMAN",
        "GOLDMAN SACHS": "GOLDMAN",
        "DBBNP": "BNP",
        "BNP": "BNP",
        "BNP PARIBAS": "BNP",
        "DMSPLC": "MORGAN",
        "MORGAN": "MORGAN",
        "MORGAN STANLEY": "MORGAN",
        "BBVA": "BBVA",
    }

    def __init__(self, file_overrides: dict[str, Any] | None = None) -> None:
        self.file_overrides = file_overrides or {}
        self.reporting = ReportingService(file_overrides)

    def _sheets(self) -> dict[str, pd.DataFrame]:
        return self.reporting.workbook_preview()

    def valuation_fx_rate(self) -> float:
        source = self.file_overrides.get("validaciones_otc")
        if source is None:
            return 1.0
        if hasattr(source, "seek"):
            source.seek(0)
        raw = pd.read_excel(source, sheet_name="VALUACION", header=None, nrows=1)
        value = pd.to_numeric(pd.Series([raw.iloc[0, 0]]), errors="coerce").iloc[0]
        if pd.isna(value) or float(value) == 0.0:
            return 1.0
        return float(value)

    @staticmethod
    def _num(series: pd.Series) -> pd.Series:
        return pd.to_numeric(series, errors="coerce").fillna(0.0)

    @classmethod
    def _counterparty(cls, value: object) -> str:
        key = str(value or "").strip().upper()
        return cls.COUNTERPARTY_ALIASES.get(key, key)

    @staticmethod
    def _fund(value: object) -> str:
        key = str(value or "").strip().upper()
        replacements = {
            "SIEFORE 60": "INVER60",
            "SIEFORE 65": "INVER65",
            "SIEFORE 70": "INVER70",
            "SIEFORE 75": "INVER75",
            "SIEFORE 80": "INVER80",
            "SIEFORE 85": "INVER85",
            "SIEFORE 90": "INVER90",
            "SIEFORE 95": "INVER95",
            "SIEFORE IN": "INVERIN",
        }
        if key in replacements:
            return replacements[key]
        if key.startswith("SIEFORE "):
            suffix = key.replace("SIEFORE ", "", 1).strip()
            return f"INVER{suffix}"
        return key

    @classmethod
    def _normalize_counterparty_column(cls, df: pd.DataFrame) -> pd.DataFrame:
        normalized = df.copy()
        if "CONTRAPARTE" in normalized.columns:
            normalized["CONTRAPARTE"] = normalized["CONTRAPARTE"].map(cls._counterparty)
        if "SIEFORE" in normalized.columns:
            normalized["SIEFORE"] = normalized["SIEFORE"].map(cls._fund)
        return normalized

    def derivative_valuations(self) -> pd.DataFrame:
        posiciones = self._sheets().get("POSICIONES")
        if posiciones is None or posiciones.empty:
            return pd.DataFrame()
        df = self._normalize_counterparty_column(posiciones)
        df["VALUACION"] = self._num(df["VALUACION"])
        fx_rate = self.valuation_fx_rate()
        df["VALUACION_USD"] = df["VALUACION"] / fx_rate
        return (
            df.groupby(["CONTRAPARTE", "SIEFORE"], dropna=False)["VALUACION_USD"]
            .sum()
            .reset_index()
            .rename(columns={"VALUACION_USD": "VALUACION_OTC_USD"})
        )

    def collateral_valuations(self) -> pd.DataFrame:
        totales = self._sheets().get("TOTALES")
        if totales is None or totales.empty:
            return pd.DataFrame()
        df = self._normalize_counterparty_column(totales)
        df["VALUACION"] = self._num(df["VALUACION"])
        return (
            df.groupby(["CONTRAPARTE", "SIEFORE"], dropna=False)["VALUACION"]
            .sum()
            .reset_index()
            .rename(columns={"VALUACION": "VALUACION_COLATERAL_USD"})
        )

    def cash_valuations(self) -> pd.DataFrame:
        cash = self._sheets().get("CASH")
        if cash is None or cash.empty:
            return pd.DataFrame(columns=["CONTRAPARTE", "SIEFORE", "VALUACION_CASH_USD"])
        fund_columns = [column for column in cash.columns if str(column).startswith("SIEFORE")]
        if not fund_columns:
            return pd.DataFrame(columns=["CONTRAPARTE", "SIEFORE", "VALUACION_CASH_USD"])
        long_df = cash.melt(
            id_vars=["MOVIMIENTO", "CONTRAPARTE", "FECHA"],
            value_vars=fund_columns,
            var_name="SIEFORE",
            value_name="MONTO",
        )
        long_df["MONTO"] = self._num(long_df["MONTO"])
        long_df["CONTRAPARTE"] = long_df["CONTRAPARTE"].map(self._counterparty)
        long_df["SIEFORE"] = long_df["SIEFORE"].map(self._fund)
        long_df["SIGNO"] = long_df["MOVIMIENTO"].astype(str).str.upper().map({"ENVIO": 1.0, "RECEP": -1.0}).fillna(0.0)
        long_df["VALUACION_CASH_USD"] = long_df["MONTO"] * long_df["SIGNO"]
        return (
            long_df.groupby(["CONTRAPARTE", "SIEFORE"], dropna=False)["VALUACION_CASH_USD"]
            .sum()
            .reset_index()
        )

    def counterparty_calls(self) -> pd.DataFrame:
        source = self.file_overrides.get("validaciones_otc")
        if source is None:
            return pd.DataFrame(
                columns=[
                    "CONTRAPARTE",
                    "SIEFORE",
                    "MONTO_CONTRAPARTE_USD",
                    "MONTO_CONTRAPARTE_MXN",
                    "MONEDA_CONTRAPARTE",
                ]
            )
        if hasattr(source, "seek"):
            source.seek(0)
        fx_rate = self.valuation_fx_rate()
        raw = pd.read_excel(source, sheet_name="VALUACION", header=None)
        records: list[dict[str, Any]] = []
        current_counterparty: str | None = None
        for _, row in raw.iterrows():
            second_col = row.iloc[1] if len(row) > 1 else None
            amount = row.iloc[6] if len(row) > 6 else None
            if isinstance(second_col, str) and second_col.strip().upper() in {"CBGSMX", "DBBNP", "DMSPLC", "BBVA"}:
                current_counterparty = self._counterparty(second_col)
                continue
            if current_counterparty and isinstance(second_col, str) and second_col.strip().upper().startswith("INVER"):
                numeric_amount = pd.to_numeric(pd.Series([amount]), errors="coerce").iloc[0]
                if pd.notna(numeric_amount) and float(numeric_amount) != 0.0:
                    amount_value = float(numeric_amount)
                    is_bbva = current_counterparty == "BBVA"
                    records.append(
                        {
                            "CONTRAPARTE": current_counterparty,
                            "SIEFORE": self._fund(second_col),
                            "MONTO_CONTRAPARTE_USD": amount_value / fx_rate if is_bbva else amount_value,
                            "MONTO_CONTRAPARTE_MXN": amount_value if is_bbva else amount_value * fx_rate,
                            "MONEDA_CONTRAPARTE": "MXN" if is_bbva else "USD",
                        }
                    )
        if not records:
            return pd.DataFrame(
                columns=[
                    "CONTRAPARTE",
                    "SIEFORE",
                    "MONTO_CONTRAPARTE_USD",
                    "MONTO_CONTRAPARTE_MXN",
                    "MONEDA_CONTRAPARTE",
                ]
            )
        grouped = (
            pd.DataFrame(records)
            .groupby(["CONTRAPARTE", "SIEFORE", "MONEDA_CONTRAPARTE"], dropna=False)[
                ["MONTO_CONTRAPARTE_USD", "MONTO_CONTRAPARTE_MXN"]
            ]
            .sum()
            .reset_index()
        )
        return grouped

    def valuation_summary(self) -> pd.DataFrame:
        derivatives = self.derivative_valuations()
        collateral = self.collateral_valuations()
        cash = self.cash_valuations()
        calls = self.counterparty_calls()
        if derivatives.empty and collateral.empty and cash.empty and calls.empty:
            return pd.DataFrame()
        frames = []
        for frame in [derivatives, collateral, cash, calls]:
            if not frame.empty:
                frames.append(frame)
        summary = frames[0]
        for frame in frames[1:]:
            summary = summary.merge(frame, on=["CONTRAPARTE", "SIEFORE"], how="outer")
        for column in ["VALUACION_OTC_USD", "VALUACION_COLATERAL_USD", "VALUACION_CASH_USD", "MONTO_CONTRAPARTE_USD"]:
            if column not in summary.columns:
                summary[column] = 0.0
            summary[column] = self._num(summary[column])
        if "MONTO_CONTRAPARTE_MXN" not in summary.columns:
            summary["MONTO_CONTRAPARTE_MXN"] = summary["MONTO_CONTRAPARTE_USD"] * self.valuation_fx_rate()
        else:
            summary["MONTO_CONTRAPARTE_MXN"] = self._num(summary["MONTO_CONTRAPARTE_MXN"])
        if "MONEDA_CONTRAPARTE" not in summary.columns:
            summary["MONEDA_CONTRAPARTE"] = ""
        summary["MONEDA_CONTRAPARTE"] = summary["MONEDA_CONTRAPARTE"].fillna("")
        summary["VALUACION_TOTAL_INTERNA_USD"] = (
            summary["VALUACION_OTC_USD"] - summary["VALUACION_COLATERAL_USD"] + summary["VALUACION_CASH_USD"]
        )
        summary["DIFERENCIA_VS_CONTRAPARTE_USD"] = summary["VALUACION_TOTAL_INTERNA_USD"] - summary["MONTO_CONTRAPARTE_USD"]
        fx_rate = self.valuation_fx_rate()
        summary["MONTO_A_ENTREGAR_INTERNO_USD"] = summary["VALUACION_TOTAL_INTERNA_USD"].clip(lower=0.0)
        summary["MONTO_A_ENTREGAR_INTERNO_MXN"] = summary["MONTO_A_ENTREGAR_INTERNO_USD"] * fx_rate
        numeric_columns = [
            "VALUACION_OTC_USD",
            "VALUACION_COLATERAL_USD",
            "VALUACION_CASH_USD",
            "MONTO_CONTRAPARTE_USD",
            "MONTO_CONTRAPARTE_MXN",
            "VALUACION_TOTAL_INTERNA_USD",
            "DIFERENCIA_VS_CONTRAPARTE_USD",
            "MONTO_A_ENTREGAR_INTERNO_USD",
            "MONTO_A_ENTREGAR_INTERNO_MXN",
        ]
        summary = (
            summary.groupby(["CONTRAPARTE", "SIEFORE"], dropna=False)[numeric_columns]
            .sum()
            .reset_index()
            .sort_values(["CONTRAPARTE", "SIEFORE"])
            .reset_index(drop=True)
        )
        summary["MONEDA_UMBRAL"] = summary["CONTRAPARTE"].map(lambda value: "MXN" if value == "BBVA" else "USD")
        summary["MONTO_SEMAFORO"] = summary.apply(
            lambda row: row["MONTO_A_ENTREGAR_INTERNO_MXN"]
            if row["CONTRAPARTE"] == "BBVA"
            else row["MONTO_A_ENTREGAR_INTERNO_USD"],
            axis=1,
        )
        summary["UMBRAL_APLICABLE"] = summary["CONTRAPARTE"].map(
            lambda value: self.BBVA_DELIVERY_THRESHOLD_MXN if value == "BBVA" else self.DELIVERY_THRESHOLD_USD
        )
        summary["SEMAFORO"] = summary.apply(
            lambda row: "ROJO" if float(row["MONTO_SEMAFORO"]) >= float(row["UMBRAL_APLICABLE"]) else "VERDE",
            axis=1,
        )
        summary["ESTATUS_ENTREGA"] = summary["SEMAFORO"].map(
            {"ROJO": "Revisar entrega", "VERDE": "Dentro de umbral"}
        )
        non_zero = summary[numeric_columns].abs().sum(axis=1) != 0
        return summary[non_zero].reset_index(drop=True)

    def collateral_positions(self) -> pd.DataFrame:
        totales = self._sheets().get("TOTALES")
        if totales is None:
            return pd.DataFrame()
        return self._normalize_counterparty_column(totales)

    def derivative_positions(self) -> pd.DataFrame:
        posiciones = self._sheets().get("POSICIONES")
        if posiciones is None:
            return pd.DataFrame()
        return self._normalize_counterparty_column(posiciones)

    def collateral_recommendation(
        self,
        counterparty: str,
        fund: str,
        amount: float,
        preserve_cash: bool = True,
    ) -> pd.DataFrame:
        collateral = self.collateral_positions()
        if collateral.empty:
            return pd.DataFrame()
        normalized_counterparty = self._counterparty(counterparty)
        currency = "MXN" if normalized_counterparty == "BBVA" else "USD"
        df = collateral[
            (collateral["CONTRAPARTE"].astype(str).str.upper() == normalized_counterparty)
            & (collateral["SIEFORE"].astype(str).str.upper() == self._fund(fund))
        ].copy()
        if df.empty:
            return pd.DataFrame()
        df["VALUACION"] = self._num(df["VALUACION"])
        df["TITULOS"] = self._num(df["TITULOS"])
        df["PRECIO_CON_HAIRCUT"] = self._num(df["PRECIO_CON_HAIRCUT"])
        df = df.sort_values("VALUACION", ascending=False)
        remaining = float(amount)
        rows = []
        for _, row in df.iterrows():
            if remaining <= 0:
                break
            value = float(row["VALUACION"])
            if value <= 0:
                continue
            price = float(row["PRECIO_CON_HAIRCUT"]) if float(row["PRECIO_CON_HAIRCUT"]) != 0 else 1.0
            available_titles = max(0, int(math.floor(float(row["TITULOS"]))))
            if available_titles == 0:
                continue
            needed_titles = max(1, int(math.ceil(remaining / price)))
            suggested_titles = min(available_titles, needed_titles)
            covered_value = suggested_titles * price
            rows.append(
                {
                    "CONTRAPARTE": normalized_counterparty,
                    "SIEFORE": self._fund(fund),
                    "INSTRUMENTO": row["INSTRUMENTO"],
                    "TITULOS_DISPONIBLES": available_titles,
                    "TITULOS_SUGERIDOS": suggested_titles,
                    "NOCIONAL_SUGERIDO": suggested_titles * 100,
                    "VALUACION_CUBIERTA": round(covered_value, 2),
                    "PRECIO_CON_HAIRCUT": round(price, 6),
                    "HAIRCUT": row.get("HAIRCUT", ""),
                    "MONEDA": currency,
                }
            )
            remaining -= covered_value
        result = pd.DataFrame(rows)
        if not result.empty:
            result["MONTO_SOLICITADO"] = amount
            result["FALTANTE"] = max(0.0, remaining)
            result["EXCESO"] = max(0.0, -remaining)
            result["POLITICA"] = "Preservar efectivo" if preserve_cash else "Permitir efectivo"
        return result
