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


class CSVImporter:
    required_columns: tuple[str, ...] = ()

    def read_csv(self, file_path: Path | Any) -> pd.DataFrame:
        if isinstance(file_path, Path) and not file_path.exists():
            raise FileNotFoundError(f"Input file not found: {file_path}")
        df = pd.read_csv(file_path)
        missing = [col for col in self.required_columns if col not in df.columns]
        if missing:
            source_name = getattr(file_path, "name", str(file_path))
            raise ValueError(f"Missing required columns in {source_name}: {missing}")
        return df


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
        df = self.read_csv(file_path)
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
        normalized["source"] = file_path.name
        return ImportResult(normalized, str(file_path), len(normalized), [])


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
        df = self.read_csv(file_path)
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
        df = self.read_csv(file_path)
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
        df = self.read_csv(file_path)
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
        df = self.read_csv(file_path)
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
        df = self.read_csv(file_path)
        normalized = df.copy()
        normalized["counterparty_code"] = normalized["counterparty_code"].map(TextNormalizer.normalize)
        normalized["currency"] = normalized["currency"].map(TextNormalizer.normalize)
        normalized["direction"] = normalized["direction"].map(TextNormalizer.normalize)
        normalized["required_amount"] = normalized["required_amount"].map(lambda x: Decimal(str(x)))
        normalized["due_date"] = pd.to_datetime(normalized["due_date"]).dt.date
        return ImportResult(normalized, str(file_path), len(normalized), [])
