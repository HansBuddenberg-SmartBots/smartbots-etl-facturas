"""Caso de uso principal: consolida facturas desde archivos XLSX en Google Drive."""

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
import uuid

import pandas as pd
import structlog

from src.domain.entities import InvoiceRecord, RecordStatus
from src.domain.exceptions import ReconciliationError, SchemaValidationError
from src.application.config import AppConfig
from src.application.ports.drive_repository import DriveRepository
from src.application.ports.excel_handler import ExcelReader, ExcelWriter
from src.application.ports.notifier import Notifier
from src.application.ports.tracker import Tracker
from src.application.dtos import ExecutionReport, UpsertResult
from src.application.transformers import RowTransformer
from src.infrastructure.drive_path_resolver import DrivePathResolver
from src.infrastructure.file_lifecycle_manager import FileLifecycleManager

logger = structlog.get_logger()

TEMPLATE_MAP = {
    "SUCCESS": "success",
    "PARTIAL": "partial",
    "ERROR": "error",
    "NO_FILES": "empty",
}


@dataclass(frozen=True)
class ConsolidateInvoicesUseCase:
    drive: DriveRepository
    reader: ExcelReader
    writer: ExcelWriter
    notifier: Notifier
    tracker: Tracker
    config: AppConfig
    path_resolver: DrivePathResolver
    lifecycle: FileLifecycleManager

    def execute(self) -> ExecutionReport:
        run_id = str(uuid.uuid4())
        report = ExecutionReport(run_id=run_id)
        consolidated_file_id: str | None = None
        backup_file_id: str | None = None

        try:
            self.tracker.start_run(run_id)

            source_folder_id = self.path_resolver.resolve_path(self.config.drive.source_path)
            consolidated_folder_id = self.path_resolver.resolve_path(
                self.config.drive.consolidated_path
            )

            consolidated_file_id = self.drive.find_file_in_folder(
                consolidated_folder_id, self.config.drive.consolidated_filename
            )
            if not consolidated_file_id:
                raise FileNotFoundError(
                    f"Consolidado '{self.config.drive.consolidated_filename}' "
                    f"no encontrado en '{self.config.drive.consolidated_path}'"
                )

            source_files = self.drive.list_source_files(source_folder_id)
            if not source_files:
                report.status = "NO_FILES"
                return report

            report.source_files = [f["name"] for f in source_files]
            report.total_files = len(source_files)

            backup_file_id = self.drive.create_backup(
                consolidated_file_id,
                f"consolidado_backup_{run_id[:8]}.xlsx",
            )
            report.backup_file_id = backup_file_id

            transformer = RowTransformer(self.config.excel)

            for source_file in source_files:
                self._process_file(
                    source_file,
                    source_folder_id,
                    consolidated_file_id,
                    transformer,
                    run_id,
                    report,
                )

            if not report.files_with_errors:
                report.status = "SUCCESS"
            elif len(report.files_with_errors) < len(source_files):
                report.status = "PARTIAL"
            else:
                report.status = "ERROR"

        except Exception as e:
            report.status = "ERROR"
            logger.error("consolidation_fatal_error", error=str(e))
            if backup_file_id and consolidated_file_id:
                try:
                    self.drive.restore_backup(backup_file_id, consolidated_file_id)
                    report.rollback_executed = True
                except Exception as rb_err:
                    logger.error("rollback_failed", error=str(rb_err))

        finally:
            self._finish(run_id, report)

        return report

    def _process_file(
        self,
        source_file: dict,
        source_folder_id: str,
        consolidated_file_id: str,
        transformer: RowTransformer,
        run_id: str,
        report: ExecutionReport,
    ) -> None:
        file_log_id: int | None = None
        try:
            if self.tracker.is_file_processed(source_file["name"], source_file["modified_time"]):
                logger.info("file_skipped_idempotent", name=source_file["name"])
                return

            file_log_id = self.tracker.log_file_start(
                run_id,
                source_file["name"],
                source_file["file_id"],
                source_file.get("modified_time"),
            )

            self.lifecycle.move_to_in_process(source_file["file_id"], source_folder_id)

            local_source = Path(f"/tmp/{source_file['name']}")
            self.drive.download_file(source_file["file_id"], local_source)

            df_source = self.reader.read(local_source, self.config.excel.source_sheet)
            is_valid, missing, extra = self.reader.validate_schema(
                df_source, list(self.config.excel.expected_columns)
            )
            self.tracker.log_file_schema(file_log_id, is_valid, missing, extra)

            if not is_valid:
                raise SchemaValidationError(missing, extra)

            source_records, row_errors = self._validate_and_transform(
                df_source,
                source_file["name"],
                transformer,
                run_id,
                file_log_id,
            )
            report.source_row_count += len(df_source)
            report.valid_row_count += len(source_records)
            report.validation_errors.extend(row_errors)

            local_consolidated = Path("/tmp/consolidado.xlsx")
            self.drive.download_file(consolidated_file_id, local_consolidated)
            df_consolidated = self.reader.read(
                local_consolidated, self.config.excel.consolidated_sheet
            )
            consolidated_records = self._dataframe_to_records(df_consolidated, transformer)

            upsert_result = self._upsert(consolidated_records, source_records)
            self._log_upsert_records(run_id, file_log_id, source_records, upsert_result)
            self._reconcile(report, source_records, upsert_result)

            df_result = self._records_to_dataframe(upsert_result.all_records)
            self.writer.write(
                df_result,
                local_consolidated,
                self.config.excel.consolidated_sheet,
            )
            self.drive.update_file(consolidated_file_id, local_consolidated)

            report.inserted_count += upsert_result.inserted
            report.updated_count += upsert_result.updated
            report.unchanged_count += upsert_result.unchanged

            self.lifecycle.move_to_backup(source_file["file_id"])

            self.tracker.log_file_finish(
                file_log_id,
                "COMPLETED",
                rows_total=len(df_source),
                rows_valid=len(source_records),
                rows_error=len(row_errors),
                error_message=None,
            )

        except SchemaValidationError as e:
            report.files_with_errors.append(source_file["name"])
            report.validation_errors.append(
                {"file": source_file["name"], "row_index": "N/A", "error": str(e)}
            )
            if file_log_id is not None:
                self.tracker.log_file_finish(file_log_id, "SCHEMA_ERROR", 0, 0, 0, str(e))

        except Exception as e:
            report.files_with_errors.append(source_file["name"])
            logger.error("file_processing_error", file=source_file["name"], error=str(e))
            if file_log_id is not None:
                self.tracker.log_file_finish(file_log_id, "ERROR", 0, 0, 0, str(e))

    def _validate_and_transform(
        self,
        df: pd.DataFrame,
        source_name: str,
        transformer: RowTransformer,
        run_uuid: str,
        file_log_id: int,
    ) -> tuple[list[InvoiceRecord], list[dict]]:
        records: list[InvoiceRecord] = []
        errors: list[dict] = []
        error_batch: list[dict] = []

        for idx, row in df.iterrows():
            try:
                record = transformer.transform_row(row, source_name)
                records.append(record)
            except ValueError as e:
                errors.append({"file": source_name, "row_index": idx, "error": str(e)})
                error_batch.append(
                    {
                        "run_uuid": run_uuid,
                        "file_log_id": file_log_id,
                        "row_index": int(idx),
                        "invoice_number": None,
                        "reference_number": None,
                        "action": "VALIDATION_ERROR",
                        "error_message": str(e),
                    }
                )
            except Exception as e:
                errors.append({"file": source_name, "row_index": idx, "error": str(e)})
                error_batch.append(
                    {
                        "run_uuid": run_uuid,
                        "file_log_id": file_log_id,
                        "row_index": int(idx),
                        "invoice_number": None,
                        "reference_number": None,
                        "action": "TRANSFORM_ERROR",
                        "error_message": str(e),
                    }
                )

        if error_batch:
            self.tracker.log_records_batch(error_batch)

        return records, errors

    def _upsert(
        self,
        existing: list[InvoiceRecord],
        incoming: list[InvoiceRecord],
    ) -> UpsertResult:
        existing_map: dict[tuple, InvoiceRecord] = {r.primary_key: r for r in existing}
        result = UpsertResult()

        for record in incoming:
            pk = record.primary_key
            if pk in existing_map:
                old = existing_map[pk]
                if record.has_changes_vs(old):
                    existing_map[pk] = record.with_status(RecordStatus.UPDATED)
                    result.updated += 1
                else:
                    existing_map[pk] = old.with_status(RecordStatus.UNCHANGED)
                    result.unchanged += 1
            else:
                existing_map[pk] = record.with_status(RecordStatus.NEW)
                result.inserted += 1

        result.all_records = list(existing_map.values())
        return result

    def _log_upsert_records(
        self,
        run_uuid: str,
        file_log_id: int,
        incoming: list[InvoiceRecord],
        result: UpsertResult,
    ) -> None:
        status_to_action = {
            RecordStatus.NEW: "INSERT",
            RecordStatus.UPDATED: "UPDATE",
            RecordStatus.UNCHANGED: "UNCHANGED",
        }
        result_map = {r.primary_key: r for r in result.all_records}
        batch: list[dict] = []

        for i, record in enumerate(incoming):
            matched = result_map.get(record.primary_key)
            action = status_to_action.get(matched.status if matched else RecordStatus.NEW, "INSERT")
            batch.append(
                {
                    "run_uuid": run_uuid,
                    "file_log_id": file_log_id,
                    "row_index": i,
                    "invoice_number": record.invoice_number,
                    "reference_number": record.reference_number,
                    "action": action,
                    "error_message": None,
                }
            )

        if batch:
            self.tracker.log_records_batch(batch)

    def _reconcile(
        self,
        report: ExecutionReport,
        source_records: list[InvoiceRecord],
        upsert_result: UpsertResult,
    ) -> None:
        source_pks = {r.primary_key for r in source_records}
        result_pks = {r.primary_key for r in upsert_result.all_records}
        missing = source_pks - result_pks

        if missing:
            raise ReconciliationError(
                data_loss_pct=(len(missing) / len(source_pks)) * 100,
                amount_variance=Decimal("0"),
            )

        source_total = sum((r.total_amount for r in source_records), Decimal("0"))
        result_subset = [r for r in upsert_result.all_records if r.primary_key in source_pks]
        result_total = sum((r.total_amount for r in result_subset), Decimal("0"))

        variance = abs(source_total - result_total)
        if variance > Decimal("1"):
            raise ReconciliationError(data_loss_pct=0, amount_variance=variance)

        report.source_total_amount += source_total
        report.output_total_amount += result_total

    def _dataframe_to_records(
        self, df: pd.DataFrame, transformer: RowTransformer
    ) -> list[InvoiceRecord]:
        records = []
        for _, row in df.iterrows():
            try:
                records.append(transformer.transform_row(row, source_name="consolidado"))
            except Exception:
                continue
        return records

    def _records_to_dataframe(self, records: list[InvoiceRecord]) -> pd.DataFrame:
        from dataclasses import asdict

        rows = []
        for r in records:
            d = asdict(r)
            d["invoice_date"] = r.invoice_date.isoformat()
            d["net_amount"] = float(r.net_amount)
            d["tax_amount"] = float(r.tax_amount)
            d["total_amount"] = float(r.total_amount)
            d.pop("status", None)
            d.pop("processed_at", None)
            rows.append(d)
        return pd.DataFrame(rows)

    def _finish(self, run_id: str, report: ExecutionReport) -> None:
        counters = {
            "total_files": report.total_files,
            "total_records": report.source_row_count,
            "inserted": report.inserted_count,
            "updated": report.updated_count,
            "unchanged": report.unchanged_count,
            "errors": report.error_count,
            "source_total_amount": str(report.source_total_amount),
            "output_total_amount": str(report.output_total_amount),
        }
        try:
            self.tracker.finish_run(run_id, report.status, counters)
        except Exception as e:
            logger.error("tracker_finish_failed", error=str(e))

        self._send_notification(report)

    def _send_notification(self, report: ExecutionReport) -> None:
        template_key = TEMPLATE_MAP.get(report.status, "error")
        template_name = self.config.email.templates.get(
            template_key, "ETL_Consolidacion_Error.html"
        )
        subject = f"{self.config.email.subject_prefix} {report.status} — {report.run_id[:8]}"
        try:
            self.notifier.send(
                subject=subject,
                template_name=template_name,
                template_vars=report.to_template_vars(),
                recipients=list(self.config.email.to),
                cc=list(self.config.email.cc) or None,
                bcc=list(self.config.email.bcc) or None,
            )
        except Exception as e:
            logger.error("notification_failed", error=str(e))
