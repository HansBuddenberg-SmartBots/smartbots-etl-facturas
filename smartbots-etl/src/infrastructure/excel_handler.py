from pathlib import Path

import openpyxl
import pandas as pd
import structlog

logger = structlog.get_logger()

_FALLBACK_SHEET = "Sheet1"


class OpenpyxlExcelHandler:
    def read(
        self, file_path: Path, sheet_name: str = "Sheet1", header_row: int | None = None
    ) -> pd.DataFrame:
        actual_sheet = self._resolve_sheet(file_path, sheet_name)

        # pandas header is 0-indexed. header_row is 1-indexed (Excel).
        # header_row=None -> header=0 (default)
        header_arg = 0 if header_row is None else header_row - 1

        df = pd.read_excel(file_path, sheet_name=actual_sheet, header=header_arg, engine="openpyxl")
        logger.info(
            "excel_read",
            path=str(file_path),
            sheet=actual_sheet,
            requested_sheet=sheet_name,
            header_row=header_row,
            rows=len(df),
            columns=list(df.columns),
        )
        return df

    def write(
        self,
        df: pd.DataFrame,
        file_path: Path,
        sheet_name: str = "Sheet1",
        header_row: int = 0,
        data_start_row: int = 1,
    ) -> None:
        if not file_path.exists():
            df.to_excel(file_path, sheet_name=sheet_name, index=False, engine="openpyxl")
            logger.info("excel_created", path=str(file_path), rows=len(df))
            return

        wb = openpyxl.load_workbook(file_path)
        try:
            if sheet_name not in wb.sheetnames:
                ws = wb.create_sheet(sheet_name)
                # Write headers at header_row (or 1)
                h_row = header_row if header_row > 0 else 1
                for col_idx, col_name in enumerate(df.columns, start=1):
                    ws.cell(row=h_row, column=col_idx, value=col_name)
                next_row = data_start_row if data_start_row > h_row else h_row + 1
            else:
                ws = wb[sheet_name]
                next_row = self._find_next_empty_row(ws, min_row=data_start_row)

            for row_idx, row in enumerate(df.itertuples(index=False), start=next_row):
                for col_idx, value in enumerate(row, start=1):
                    ws.cell(row=row_idx, column=col_idx, value=value)

            wb.save(file_path)
            logger.info(
                "excel_appended",
                path=str(file_path),
                rows_appended=len(df),
                start_row=next_row,
            )

        finally:
            wb.close()

    @staticmethod
    def _find_next_empty_row(ws, min_row: int) -> int:
        """Encuentra la siguiente fila vacía, respetando min_row."""
        if ws.max_row < min_row:
            return min_row

        # Buscar hacia arriba desde max_row hasta min_row
        for r in range(ws.max_row, min_row - 1, -1):
            if any(cell.value is not None for cell in ws[r]):
                return r + 1

        return min_row

    @staticmethod
    def _resolve_sheet(file_path: Path, requested: str) -> str:
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        try:
            sheets = wb.sheetnames
            if requested in sheets:
                return requested
            if _FALLBACK_SHEET in sheets:
                logger.warning(
                    "sheet_fallback",
                    path=str(file_path),
                    requested=requested,
                    fallback=_FALLBACK_SHEET,
                )
                return _FALLBACK_SHEET
            raise ValueError(
                f"Sheet '{requested}' no encontrado en {file_path}. Sheets disponibles: {sheets}"
            )
        finally:
            wb.close()

    def validate_schema(
        self, df: pd.DataFrame, expected_columns: list[str]
    ) -> tuple[bool, list[str], list[str]]:
        actual = set(df.columns)
        expected = set(expected_columns)
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        is_valid = len(missing) == 0

        logger.info(
            "schema_validation",
            is_valid=is_valid,
            missing=missing,
            extra=extra,
        )
        return is_valid, missing, extra
