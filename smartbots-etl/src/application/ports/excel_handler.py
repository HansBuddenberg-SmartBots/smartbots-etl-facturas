from pathlib import Path
from typing import Protocol

import pandas as pd


class ExcelReader(Protocol):
    def read(
        self, file_path: Path, sheet_name: str = "Sheet1", header_row: int | None = None
    ) -> pd.DataFrame: ...

    def validate_schema(
        self, df: pd.DataFrame, expected_columns: list[str]
    ) -> tuple[bool, list[str], list[str]]:
        """Returns: (is_valid, missing_columns, extra_columns)"""
        ...


class ExcelWriter(Protocol):
    def write(
        self,
        df: pd.DataFrame,
        file_path: Path,
        sheet_name: str = "Sheet1",
        header_row: int = 0,
        data_start_row: int = 1,
    ) -> None: ...
