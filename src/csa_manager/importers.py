from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class ImportResult:
    dataframe: pd.DataFrame
    source_file: str
    row_count: int
    warnings: list[str]


class TextNormalizer:
    @staticmethod
    def normalize(value: object, replace_underscores: bool = False) -> str:
        if pd.isna(value):
            return ""
        text = str(value).strip()
        text = "".join(
            ch for ch in unicodedata.normalize("NFD", text)
            if unicodedata.category(ch) != "Mn"
        )
        if replace_underscores:
            text = text.replace("_", " ")
        return " ".join(text.upper().split())


def normalize_movement_code(value: object) -> str:
    text = TextNormalizer.normalize(value)
    if text.startswith("CIN RETURN"):
        return "ENVIO"
    if text.startswith("CIN"):
        return "RECEP"
    return text


class CSVImporter:
    required_columns: tuple[str, ...] = ()

    def read_table(self, file_path: Path | Any) -> pd.DataFrame:
        if isinstance(file_path, Path) and not file_path.exists():
            raise FileNotFoundError(f"Input file not found: {file_path}")
        source_name = getattr(file_path, "name", str(file_path))
        suffix = Path(source_name).suffix.lower()
        if hasattr(file_path, "seek"):
            file_path.seek(0)
        if suffix in {".xlsx", ".xlsm", ".xls"}:
            df = pd.read_excel(file_path)
        else:
            df = pd.read_csv(file_path)
        missing = [col for col in self.required_columns if col not in df.columns]
        if missing:
            raise ValueError(f"Missing required columns in {source_name}: {missing}")
        return df

    def source_name(self, file_path: Path | Any) -> str:
        return getattr(file_path, "name", str(file_path))


class CollateralPositionImporter(CSVImporter):
    required_columns = (
        "position_id",
        "counterparty_code",
        "fund_code",
        "portfolio_code",
        "instrument_code",
        "quantity",
        "valuation_date",
    )

    def import_file(self, file_path: Path) -> ImportResult:
        df = self.read_table(file_path)
        source_name = getattr(file_path, "name", str(file_path))
        normalized = pd.DataFrame()
        normalized["position_id"] = df["position_id"].astype(str)
        normalized["counterparty_code"] = df["counterparty_code"].map(TextNormalizer.normalize)
        normalized["fund_code"] = df["fund_code"].map(TextNormalizer.normalize)
        normalized["portfolio_code"] = df["portfolio_code"].map(TextNormalizer.normalize)
        normalized["instrument_code"] = df["instrument_code"].map(
            lambda x: TextNormalizer.normalize(x, replace_underscores=True)
        )
        normalized["quantity"] = df["quantity"].map(lambda x: Decimal(str(x)))
        normalized["valuation_date"] = pd.to_datetime(df["valuation_date"]).dt.date
        normalized["source"] = source_name
        return ImportResult(normalized, str(file_path), len(normalized), [])


class AladdinBNPGSMSPositionImporter(CSVImporter):
    required_columns = (
        "Tran Type",
        "Counterparty Ticker",
        "Portfolio",
        "Tipo Valor (Mexico)",
        "Titulos",
        "CUSIP(Aladdin ID)",
    )

    def import_file(self, file_path: Path | Any) -> ImportResult:
        df = self.read_table(file_path)
        source_name = self.source_name(file_path)
        df = df[df["Portfolio"].astype(str).str.contains(r"\(\d+/\d+\)", regex=True) == False]
        normalized = pd.DataFrame()
        normalized["position_id"] = [f"{source_name}:{index + 1}" for index in range(len(df))]
        normalized["counterparty_code"] = df["Counterparty Ticker"].map(TextNormalizer.normalize)
        normalized["fund_code"] = df["Portfolio"].map(TextNormalizer.normalize)
        normalized["portfolio_code"] = normalized["fund_code"]
        normalized["movement_code"] = df["Tran Type"].map(normalize_movement_code)
        normalized["instrument_code"] = df["Tipo Valor (Mexico)"].map(
            lambda x: TextNormalizer.normalize(x, replace_underscores=True)
        )
        normalized["quantity"] = df["Titulos"].map(lambda x: Decimal(str(x)))
        normalized["cusip"] = df["CUSIP(Aladdin ID)"].astype(str)
        normalized["source"] = source_name
        return ImportResult(normalized, source_name, len(normalized), [])


class AladdinBBVAPositionImporter(CSVImporter):
    required_columns = (
        "Tran Type",
        "Counterparty Ticker",
        "Portfolio",
        "Tipo Valor (Mexico)",
        "Orig. Face",
        "CUSIP(Aladdin ID)",
    )

    def import_file(self, file_path: Path | Any) -> ImportResult:
        df = self.read_table(file_path)
        source_name = self.source_name(file_path)
        df = df[df["Portfolio"].astype(str).str.contains(r"\(\d+/\d+\)", regex=True) == False]
        normalized = pd.DataFrame()
        normalized["position_id"] = [f"{source_name}:{index + 1}" for index in range(len(df))]
        normalized["counterparty_code"] = df["Counterparty Ticker"].map(TextNormalizer.normalize)
        normalized["fund_code"] = df["Portfolio"].map(TextNormalizer.normalize)
        normalized["portfolio_code"] = normalized["fund_code"]
        normalized["movement_code"] = df["Tran Type"].map(normalize_movement_code)
        normalized["instrument_code"] = df["Tipo Valor (Mexico)"].map(
            lambda x: TextNormalizer.normalize(x, replace_underscores=True)
        )
        normalized["quantity"] = df["Orig. Face"].map(lambda x: Decimal(str(x)))
        normalized["cusip"] = df["CUSIP(Aladdin ID)"].astype(str)
        normalized["source"] = source_name
        return ImportResult(normalized, source_name, len(normalized), [])


class AladdinOTCPositionImporter(CSVImporter):
    required_columns = (
        "CUSIP(Aladdin ID)",
        "Counterparty Ticker",
        "Portfolio",
        "Tipo Valor (Mexico)",
        "Notional Face (Title)",
    )

    def import_file(self, file_path: Path | Any) -> ImportResult:
        df = self.read_table(file_path)
        source_name = self.source_name(file_path)
        df = df[df["Portfolio"].astype(str).str.contains(r"\(\d+/\d+\)", regex=True) == False]
        normalized = pd.DataFrame()
        normalized["position_id"] = [f"{source_name}:{index + 1}" for index in range(len(df))]
        normalized["counterparty_code"] = df["Counterparty Ticker"].map(TextNormalizer.normalize)
        normalized["fund_code"] = df["Portfolio"].map(TextNormalizer.normalize)
        normalized["portfolio_code"] = normalized["fund_code"]
        normalized["instrument_code"] = df["Tipo Valor (Mexico)"].map(
            lambda x: TextNormalizer.normalize(x, replace_underscores=True)
        )
        normalized["notional_contracts"] = df["Notional Face (Title)"].map(lambda x: Decimal(str(x)))
        normalized["cusip"] = df["CUSIP(Aladdin ID)"].astype(str)
        normalized["source"] = source_name
        return ImportResult(normalized, source_name, len(normalized), [])


class AladdinOTCMovementImporter(CSVImporter):
    required_columns = (
        "Counterparty",
        "Trade Date",
        "Fund",
        "IVC",
        "Quantity",
        "Tran Type",
        "Td Num",
    )

    def import_file(self, file_path: Path | Any) -> ImportResult:
        df = self.read_table(file_path)
        source_name = self.source_name(file_path)
        normalized = pd.DataFrame()
        normalized["movement_id"] = df["Td Num"].astype(str)
        normalized["counterparty_code"] = df["Counterparty"].map(TextNormalizer.normalize)
        normalized["trade_date"] = pd.to_datetime(df["Trade Date"]).dt.date
        normalized["fund_code"] = df["Fund"].map(TextNormalizer.normalize)
        normalized["instrument_code"] = df["IVC"].map(lambda x: TextNormalizer.normalize(x, replace_underscores=True))
        normalized["quantity_original"] = df["Quantity"].map(lambda x: Decimal(str(x)))
        normalized["quantity_abs"] = normalized["quantity_original"].map(abs)
        normalized["movement_code"] = df["Tran Type"].map(normalize_movement_code)
        normalized["source"] = source_name
        return ImportResult(normalized, source_name, len(normalized), [])


class MarketPriceImporter(CSVImporter):
    required_columns = (
        "price_id",
        "emission_code",
        "dirty_price",
        "currency",
        "valuation_date",
        "source",
    )

    def import_file(self, file_path: Path) -> ImportResult:
        df = self.read_table(file_path)
        normalized = pd.DataFrame()
        normalized["price_id"] = df["price_id"].astype(str)
        normalized["emission_code"] = df["emission_code"].map(
            lambda x: TextNormalizer.normalize(x, replace_underscores=True)
        )
        normalized["dirty_price"] = df["dirty_price"].map(lambda x: Decimal(str(x)))
        normalized["currency"] = df["currency"].map(TextNormalizer.normalize)
        normalized["valuation_date"] = pd.to_datetime(df["valuation_date"]).dt.date
        normalized["source"] = df["source"].astype(str)
        if "isin" in df.columns:
            normalized["isin"] = df["isin"].where(df["isin"].notna(), None)
        else:
            normalized["isin"] = None
        return ImportResult(normalized, str(file_path), len(normalized), [])


class FXRateImporter(CSVImporter):
    required_columns = ("rate_date", "base_currency", "quote_currency", "rate", "source")

    def import_file(self, file_path: Path) -> ImportResult:
        df = self.read_table(file_path)
        normalized = pd.DataFrame()
        normalized["rate_date"] = pd.to_datetime(df["rate_date"]).dt.date
        normalized["base_currency"] = df["base_currency"].map(TextNormalizer.normalize)
        normalized["quote_currency"] = df["quote_currency"].map(TextNormalizer.normalize)
        normalized["rate"] = df["rate"].map(lambda x: Decimal(str(x)))
        normalized["source"] = df["source"].astype(str)
        return ImportResult(normalized, str(file_path), len(normalized), [])


class HaircutRuleImporter(CSVImporter):
    required_columns = (
        "rule_id",
        "counterparty_pattern",
        "match_type",
        "min_days_to_maturity",
        "max_days_to_maturity",
        "factor",
        "priority",
        "description",
    )

    def import_file(self, file_path: Path) -> ImportResult:
        df = self.read_table(file_path)
        normalized = df.copy()
        normalized["counterparty_pattern"] = normalized["counterparty_pattern"].map(TextNormalizer.normalize)
        normalized["match_type"] = normalized["match_type"].map(TextNormalizer.normalize)
        normalized["min_days_to_maturity"] = normalized["min_days_to_maturity"].where(
            normalized["min_days_to_maturity"].notna(), None
        )
        normalized["max_days_to_maturity"] = normalized["max_days_to_maturity"].where(
            normalized["max_days_to_maturity"].notna(), None
        )
        normalized["factor"] = normalized["factor"].map(lambda x: Decimal(str(x)))
        normalized["priority"] = normalized["priority"].astype(int)
        return ImportResult(normalized, str(file_path), len(normalized), [])


class InventoryImporter(CSVImporter):
    required_columns = (
        "inventory_id",
        "asset_id",
        "counterparty_code",
        "fund_code",
        "asset_type",
        "currency",
        "available_quantity",
        "unit_collateral_value",
        "is_cash",
        "is_eligible",
        "opportunity_cost",
        "settlement_lag_days",
    )

    def import_file(self, file_path: Path) -> ImportResult:
        df = self.read_table(file_path)
        normalized = df.copy()
        for col in ["counterparty_code", "fund_code", "asset_type", "currency"]:
            normalized[col] = normalized[col].map(TextNormalizer.normalize)
        for col in ["available_quantity", "unit_collateral_value", "opportunity_cost"]:
            normalized[col] = normalized[col].map(lambda x: Decimal(str(x)))
        normalized["is_cash"] = normalized["is_cash"].astype(bool)
        normalized["is_eligible"] = normalized["is_eligible"].astype(bool)
        normalized["settlement_lag_days"] = normalized["settlement_lag_days"].astype(int)
        return ImportResult(normalized, str(file_path), len(normalized), [])


class MarginCallImporter(CSVImporter):
    required_columns = (
        "margin_call_id",
        "counterparty_code",
        "csa_id",
        "required_amount",
        "currency",
        "direction",
        "due_date",
    )

    def import_file(self, file_path: Path) -> ImportResult:
        df = self.read_table(file_path)
        normalized = df.copy()
        normalized["counterparty_code"] = normalized["counterparty_code"].map(TextNormalizer.normalize)
        normalized["currency"] = normalized["currency"].map(TextNormalizer.normalize)
        normalized["direction"] = normalized["direction"].map(TextNormalizer.normalize)
        normalized["required_amount"] = normalized["required_amount"].map(lambda x: Decimal(str(x)))
        normalized["due_date"] = pd.to_datetime(normalized["due_date"]).dt.date
        return ImportResult(normalized, str(file_path), len(normalized), [])
