from config import settings
from csa_manager.importers import CollateralPositionImporter


def test_collateral_position_importer_normalizes_text() -> None:
    result = CollateralPositionImporter().import_file(settings.COLLATERAL_POSITIONS_FILE)
    df = result.dataframe
    assert result.row_count == 4
    assert df.loc[0, "counterparty_code"] == "DBBNP"
    assert df.loc[0, "instrument_code"] == "BONO M 260915"

