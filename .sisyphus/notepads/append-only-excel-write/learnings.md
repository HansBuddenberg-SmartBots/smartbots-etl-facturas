- Updated ExcelConfig with header_row=11 and data_start_row=12 in smartbots-etl/src/application/config.py
## Pattern: YAML Config Update
- Added row indices to  section in .
- Fields: , .
## Pattern: YAML Config Update
- Added row indices to `excel` section in `configuration.yaml`.
- Fields: `header_row: 11`, `data_start_row: 12`.
Updated ExcelReader protocol in smartbots-etl/src/application/ports/excel_handler.py to include optional header_row parameter in read() method.
## Protocol Update
Updated  protocol in  to include  and  in the  method. Defaults were set to 0 and 1 respectively to maintain compatibility with existing call sites.
## Protocol Update
Updated ExcelWriter protocol in smartbots-etl/src/application/ports/excel_handler.py to include header_row and data_start_row in the write method. Defaults were set to 0 and 1 respectively to maintain compatibility with existing call sites.
Updated integration test helper `create_consolidated_xlsx()` in `smartbots-etl/tests/integration/conftest.py` to support optional `header_row` parameter.
Updated integration test helper `create_consolidated_xlsx()` in `smartbots-etl/tests/integration/conftest.py` to support optional `header_row` parameter.
