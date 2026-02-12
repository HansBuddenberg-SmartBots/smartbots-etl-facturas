# Plan: Append-Only Excel Writing with Template Support

## TL;DR

Modify the ETL system to write consolidated data in **append-only mode**, preserving Excel file structure (rows 1-10: template/images, row 11: headers, rows 12+: data). Only INSERT records are appended — existing rows in Excel are never modified.

---

## Context

### User Request
- Consolidated Excel file has an **image in rows 1-10** (template)
- **Headers at row 11**
- **Data starts at row 12**
- **Only append new records** after the last written row — never modify existing rows
- Preserving the template/image is critical

### Current Behavior
- `df.to_excel()` creates a **brand new workbook** — destroys images, format, other sheets
- All records (INSERT + UPDATE + UNCHANGED) are written to the file, overwriting everything

### Desired Behavior
- Open existing workbook with openpyxl
- Preserve rows 1-11 (template + headers)
- Find the last row with data
- **Append only INSERT records** after existing data
- UPDATE/UNCHANGED records are logged to SQLite but NOT written to Excel

---

## Work Objectives

### Core Objective
Implement append-only Excel writing that preserves template structure (images in rows 1-10, headers at row 11).

### Concrete Deliverables
1. `ExcelConfig` with `header_row` and `data_start_row` fields
2. `OpenpyxlExcelHandler.read()` supporting custom header row
3. `OpenpyxlExcelHandler.write()` in append-only mode
4. `ConsolidateInvoicesUseCase` filtering to write only INSERTs
5. `configuration.yaml` updated with new fields
6. Tests updated to reflect append-only behavior

### Definition of Done
- [ ] All 83 tests pass
- [ ] Integration tests verify append-only behavior (rows accumulate, not replaced)
- [ ] Template structure preserved (not verified by tests, but code structure correct)

### Must Have
- Append-only writing (no existing row modification)
- Template preservation (rows 1-11 untouched)
- Configurable header/data row positions
- Source files still use default `header=0` (pandas 0-indexed)

### Must NOT Have
- `df.to_excel()` for consolidated files (destroys template)
- In-place cell updates for existing rows
- Clear-all-and-rewrite behavior

---

## Verification Strategy

### Test Decision
- **Infrastructure exists**: YES
- **Automated tests**: YES (tests-after)
- **Framework**: pytest
- **Agent-Executed QA**: YES (run pytest after each change)

### Agent-Executed QA Scenarios

**Scenario: Append-only mode accumulates rows**
  Tool: Bash (pytest)
  Preconditions: Code changes applied
  Steps:
    1. Run: `.venv/bin/python -m pytest tests/integration/test_consolidation_flow.py::TestSuccessFreshConsolidation -v`
    2. Run: `.venv/bin/python -m pytest tests/integration/test_consolidation_flow.py::TestUpsertUpdatesAndPreserves -v`
  Expected Result: All integration tests pass, verifying append behavior

**Scenario: All 83 tests pass**
  Tool: Bash (pytest)
  Steps:
    1. Run: `.venv/bin/python -m pytest tests/ -v`
  Expected Result: 83/83 passing

---

## Execution Strategy

### Single File Changes (Sequential)

Each file change is independent. Run pytest after each.

| Step | File | Change |
|------|------|--------|
| 1 | `src/application/config.py` | Add `header_row: int = 11`, `data_start_row: int = 12` to `ExcelConfig` |
| 2 | `configs/configuration.yaml` | Add `header_row: 11`, `data_start_row: 12` under `excel:` section |
| 3 | `src/application/ports/excel_handler.py` | Update `ExcelReader.read()` and `ExcelWriter.write()` protocols with optional `header_row` parameter |
| 4 | `src/infrastructure/excel_handler.py` | Implement `read(header_row=None)` and append-only `write(df, sheet_name, header_row, data_start_row)` |
| 5 | `src/application/use_cases/consolidate_invoices.py` | Use `header_row=config.excel.header_row` when reading consolidated; filter `only INSERTs` before write |
| 6 | `tests/integration/conftest.py` | Update `create_consolidated_xlsx()` to accept `header_row` parameter |
| 7 | `tests/integration/test_consolidation_flow.py` | Update tests to reflect append-only behavior |

---

## TODOs

- [ ] 1. Update `ExcelConfig` with `header_row` and `data_start_row`

  **What to do**:
  - Add `header_row: int = 11` field
  - Add `data_start_row: int = 12` field
  - These are Excel 1-indexed rows

  **Must NOT do**:
  - Don't change defaults (11 and 12 are correct for template)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: N/A

  **Parallelization**:
  - Sequential

  **References**:
  - `src/application/config.py:28-56` - ExcelConfig dataclass

  **Acceptance Criteria**:
  - [ ] `ExcelConfig` has `header_row: int = 11`
  - [ ] `ExcelConfig` has `data_start_row: int = 12`
  - [ ] Unit test `tests/unit/test_config.py` passes

- [ ] 2. Update `configuration.yaml` with row indices

  **What to do**:
  - Add under `excel:` section:
    ```yaml
    header_row: 11
    data_start_row: 12
    ```

  **References**:
  - `configs/configuration.yaml:21-45` - excel section

  **Acceptance Criteria**:
  - [ ] YAML has `header_row: 11`
  - [ ] YAML has `data_start_row: 12`

- [ ] 3. Update `ExcelReader` protocol with `header_row` parameter

  **What to do**:
  - Add optional `header_row: int | None = None` parameter to `read()` method

  **References**:
  - `src/application/ports/excel_handler.py:7-9` - ExcelReader protocol

  **Acceptance Criteria**:
  - [ ] `ExcelReader.read(self, file_path: Path, sheet_name: str, header_row: int | None = None) -> pd.DataFrame`
  - [ ] mypy/type check passes

- [ ] 4. Update `ExcelWriter` protocol with `header_row` and `data_start_row`

  **What to do**:
  - Add `header_row: int` and `data_start_row: int` parameters to `write()` method

  **References**:
  - `src/application/ports/excel_handler.py:11-13` - ExcelWriter protocol

  **Acceptance Criteria**:
  - [ ] `ExcelWriter.write(self, df: pd.DataFrame, file_path: Path, sheet_name: str, header_row: int, data_start_row: int) -> None`
  - [ ] mypy/type check passes

- [ ] 5. Implement `read(header_row)` in `OpenpyxlExcelHandler`

  **What to do**:
  - If `header_row is None`, use `header=0` (default pandas behavior)
  - If `header_row` provided, convert to 0-indexed: `header=header_row - 1`
  - Pass to `pd.read_excel(..., header=converted)`

  **References**:
  - `src/infrastructure/excel_handler.py:13-24` - current `read()` method
  - `src/application/config.py:31-32` - header_row default is 11

  **Acceptance Criteria**:
  - [ ] `read()` accepts `header_row` parameter
  - [ ] When `header_row=11`, pandas uses `header=10`
  - [ ] When `header_row=None`, pandas uses `header=0`
  - [ ] Unit tests pass

- [ ] 6. Implement append-only `write()` in `OpenpyxlExcelHandler`

  **What to do**:
  - Remove `_write_preserving()` method (no longer needed)
  - Replace `write()` logic:
    1. Load existing workbook with `openpyxl.load_workbook(file_path)`
    2. Get worksheet: `ws = wb[sheet_name]`
    3. Read header row to build column position mapping: iterate columns in row `header_row`
    4. Find last data row: start from `data_start_row`, scan up to find first non-empty row
    5. Append data: write each DataFrame row starting at `last_row + 1`
    6. Save and close workbook
  - Preserve: rows 1 to `header_row-1` (template)

  **References**:
  - `src/infrastructure/excel_handler.py:64-67` - current `write()` (needs complete rewrite)
  - `src/infrastructure/excel_handler.py:47-62` - `_write_preserving` (delete this)
  - `src/application/use_cases/consolidate_invoices.py:173-178` - how write is called

  **Acceptance Criteria**:
  - [ ] `write()` takes `df, file_path, sheet_name, header_row, data_start_row`
  - [ ] Reads headers from row `header_row` to build column mapping
  - [ ] Finds last row with data (starting from `data_start_row`)
  - [ ] Writes DataFrame rows after last data row
  - [ ] Preserves rows 1 to `header_row-1` (template)
  - [ ] `wb.save()` called, `wb.close()` called

- [ ] 7. Update `ConsolidateInvoicesUseCase` for append-only writing

  **What to do**:
  - When reading consolidated: pass `header_row=self.config.excel.header_row`
  - Before writing: filter `upsert_result.all_records` to only `INSERT` status:
    ```python
    insert_records = [r for r in upsert_result.all_records if r.status == RecordStatus.NEW]
    df_inserts = self._records_to_dataframe(insert_records)
    ```
  - When writing: pass `header_row=self.config.excel.header_row, data_start_row=self.config.excel.data_start_row`
  - Only write if `df_inserts` is not empty (skip upload if no new records)

  **References**:
  - `src/application/use_cases/consolidate_invoices.py:162-167` - reading consolidated (add header_row)
  - `src/application/use_cases/consolidate_invoices.py:169-183` - upsert and write (filter INSERTs)
  - `src/domain/entities.py:10-16` - RecordStatus enum (NEW = INSERT)

  **Acceptance Criteria**:
  - [ ] Consolidated read uses `header_row` from config
  - [ ] Only `RecordStatus.NEW` records are written to Excel
  - [ ] `writer.write()` receives `header_row` and `data_start_row`
  - [ ] If no INSERTs, skip `drive.update_file()` call

- [ ] 8. Update integration test helper `create_consolidated_xlsx()`

  **What to do**:
  - Add optional `header_row: int = 0` parameter (0 = default, no template)
  - If `header_row > 0`, create empty rows 1 to `header_row-1`
  - Write headers at row `header_row`
  - Start data at row `header_row + 1`

  **References**:
  - `tests/integration/conftest.py:79-94` - `create_consolidated_xlsx()` function

  **Acceptance Criteria**:
  - [ ] Function accepts `header_row` parameter
  - [ ] When `header_row=11`, creates 10 empty rows + headers at row 11

- [ ] 9. Update integration tests for append-only behavior

  **What to do**:
  - Update `TestSuccessFreshConsolidation`: empty consolidated → 3 rows written at row 12
  - Update `TestUpsertUpdatesAndPreserves`: this test needs adjustment since we only append INSERTs now
    - Existing: 2 records in consolidated
    - Source: 1 UPDATE + 1 INSERT
    - Expected: Only INSERT written, total rows = 3 (2 existing + 1 new)
    - UPDATE record in Excel should have OLD values (unchanged)
  - Other tests: verify they still pass

  **References**:
  - `tests/integration/test_consolidation_flow.py` - all integration tests

  **Acceptance Criteria**:
  - [ ] All integration tests pass
  - [ ] `TestUpsertUpdatesAndPreserves` verifies only INSERT written
  - [ ] UPDATE/UNCHANGED not written to Excel

- [ ] 10. Run full test suite

  **What to do**:
  - Run: `.venv/bin/python -m pytest tests/ -v`

  **Acceptance Criteria**:
  - [ ] 83/83 tests passing
  - [ ] No new errors or warnings

---

## Commit Strategy

| After Step | Message | Files |
|------------|---------|-------|
| 1-3 | `feat(config): add header_row and data_start_row to ExcelConfig` | config.py, configuration.yaml |
| 4-6 | `feat(excel): implement append-only write with template preservation` | ports/excel_handler.py, excel_handler.py |
| 7 | `feat(use-case): filter to INSERT-only for append writing` | consolidate_invoices.py |
| 8-10 | `test(integration): update tests for append-only behavior` | conftest.py, test_consolidation_flow.py |

---

## Success Criteria

### Verification Commands
```bash
.venv/bin/python -m pytest tests/ -v
```

### Final Checklist
- [ ] ExcelConfig has header_row=11, data_start_row=12
- [ ] configuration.yaml updated
- [ ] OpenpyxlExcelHandler.write() is append-only
- [ ] OpenpyxlExcelHandler.read() supports custom header row
- [ ] Use case writes only INSERT records
- [ ] All 83 tests pass
- [ ] Integration tests verify append behavior
