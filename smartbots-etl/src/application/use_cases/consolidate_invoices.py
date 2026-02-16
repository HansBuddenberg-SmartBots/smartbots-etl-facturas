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
from src.infrastructure.official_format_extractor import OfficialFormatExtractor

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

        # Limpiar carpeta de descargas antes de iniciar
        self._clean_downloads_folder()

        try:
            self.tracker.start_run(run_id)

            # ============================================================
            # DEBUG: Resolver rutas de carpetas en Google Drive
            # ============================================================
            logger.debug(
                "debug_resolve_folders",
                source_path=self.config.drive.source_path,
                consolidated_path=self.config.drive.consolidated_path,
            )
            logger.debug(f"{'=' * 80}\n")
            logger.debug(f"{'=' * 80}")
            logger.debug("DEBUG: Resolviendo carpetas en Google Drive...")
            logger.debug(f"  → Carpeta origen (source): {self.config.drive.source_path}")
            logger.debug(f"  → Carpeta consolidado: {self.config.drive.consolidated_path}")

            source_folder_id = self.path_resolver.ensure_path(self.config.drive.source_path)
            logger.debug(f"  → ID carpeta origen: {source_folder_id}")

            consolidated_folder_id = self.path_resolver.ensure_path(
                self.config.drive.consolidated_path
            )
            logger.debug(f"  → ID carpeta consolidado: {consolidated_folder_id}")
            logger.debug(f"{'=' * 80}\n")

            logger.debug(f"{'=' * 80}")
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
                logger.debug("debug_no_files_found", source_path=self.config.drive.source_path)
                logger.debug(f"{'=' * 80}\n")
                logger.debug("DEBUG: No se encontraron archivos en la carpeta de origen")
                logger.debug("  → Fin de ejecución")
                logger.debug(f"{'=' * 80}\n")
                return report

            logger.debug(
                "debug_files_found",
                count=len(source_files),
                files=[f["name"] for f in source_files],
            )
            logger.debug(f"{'=' * 80}\n")

            logger.debug(f"{'=' * 80}")
            logger.debug("DEBUG: Archivos encontrados en carpeta de origen:")
            for f in source_files:
                logger.debug(f"  → {f['name']} (ID: {f['file_id']})")
            logger.debug(f"{'=' * 80}\n")

            report.source_files = [f["name"] for f in source_files]
            report.total_files = len(source_files)

            logger.debug(f"{'=' * 80}")
            # Inicializar folder de backup con fecha/hora de esta ejecución
            self.lifecycle.init_backup_folder()

            # Crear backup del consolidado en Respaldo/yyyy-mm-dd/hh.mi.ss/
            backup_folder_id = self.lifecycle.backup_consolidated(consolidated_file_id, run_id)
            report.backup_folder_id = backup_folder_id

            # Inicializar transformer de filas
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

    def _clean_downloads_folder(self) -> None:
        """Limpia la carpeta de descargas antes de iniciar una nueva ejecución."""
        downloads_path = Path(self.config.downloads.temp_path)

        if downloads_path.exists():
            # Eliminar todos los archivos en la carpeta (pero no la carpeta misma)
            for file in downloads_path.iterdir():
                if file.is_file():
                    try:
                        file.unlink()
                        logger.debug("debug_deleted_old_file", path=str(file))
                    except Exception as e:
                        logger.warning("warn_failed_to_delete_file", path=str(file), error=str(e))

            logger.info("downloads_folder_cleaned", path=str(downloads_path))
        else:
            # Crear la carpeta si no existe
            downloads_path.mkdir(parents=True, exist_ok=True)
            logger.debug("downloads_folder_created", path=str(downloads_path))

    def _process_file(
        self,
        source_file: dict,
        source_folder_id: str,
        consolidated_file_id: str,
        transformer: RowTransformer,
        run_id: str,
        report: ExecutionReport,
    ) -> None:
        """Orquestador principal que coordina el procesamiento de un archivo."""
        file_log_id: int | None = None
        try:
            # 1. Verificar si el archivo ya fue procesado (idempotencia)
            if self._is_file_already_processed(source_file):
                return

            # 2. Iniciar procesamiento: loguear inicio y mover a carpeta "en proceso"
            file_log_id = self._initiate_file_processing(source_file, run_id, source_folder_id)

            # 3. Descargar archivo fuente y extraer registros
            source_records, row_errors = self._download_and_extract_source(source_file)

            # 4. Validar registros fuente y actualizar reporte
            self._validate_source_records(source_records, row_errors, file_log_id, report)

            # 5. Descargar y leer archivo consolidado
            df_consolidated = self._download_consolidated(consolidated_file_id)

            # 6. Convertir consolidado a registros y realizar upsert
            upsert_result = self._merge_and_upsert(
                df_consolidated, source_records, transformer, run_id, file_log_id, row_errors
            )

            # 7. Reconciliar y escribir resultados
            self._reconcile_and_write(source_records, upsert_result, consolidated_file_id, report)

            # 8. Finalizar: mover a backup y loguear completitud
            self._finalize_file_processing(source_file, file_log_id, source_records, row_errors)

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

    def _is_file_already_processed(self, source_file: dict) -> bool:
        """Verifica si el archivo ya fue procesado previamente (idempotencia)."""
        if self.tracker.is_file_processed(source_file["name"], source_file["modified_time"]):
            logger.info("file_skipped_idempotent", name=source_file["name"])
            return True
        return False

    def _initiate_file_processing(
        self, source_file: dict, run_id: str, source_folder_id: str
    ) -> int:
        """Inicia el procesamiento: loguea inicio y mueve archivo a carpeta en proceso."""
        logger.debug(
            "debug_processing_file", filename=source_file["name"], file_id=source_file["file_id"]
        )
        logger.debug("=" * 80 + "\n")
        logger.debug(f"{'=' * 80}")
        logger.debug(f"DEBUG: Procesando archivo: {source_file['name']}")

        file_log_id = self.tracker.log_file_start(
            run_id,
            source_file["name"],
            source_file["file_id"],
            source_file.get("modified_time"),
        )

        self.lifecycle.move_to_in_process(source_file["file_id"], source_folder_id)
        return file_log_id

    def _download_and_extract_source(
        self, source_file: dict
    ) -> tuple[list[InvoiceRecord], list[dict]]:
        """Descarga el archivo fuente desde Drive y extrae los registros."""
        logger.debug(f"  → Descargando de Google Drive...")

        local_source = Path(f"{self.config.downloads.temp_path}/{source_file['name']}")
        local_source.parent.mkdir(parents=True, exist_ok=True)
        self.drive.download_file(source_file["file_id"], local_source)
        logger.debug("debug_file_downloaded", path=str(local_source))
        logger.debug(f"  → Archivo descargado en: {local_source}")
        logger.debug(f"  → Extrayendo datos del Excel (hoja: {self.config.excel.source_sheet})...")

        extractor = OfficialFormatExtractor(self.config.excel)
        source_records = extractor.extract(local_source)
        row_errors = extractor.validation_errors

        logger.debug(
            "debug_extraction_result",
            records=len(source_records),
            errors=len(row_errors),
        )
        logger.debug(f"  → Registros extraídos: {len(source_records)}")
        if source_records:
            logger.debug(f"  → Primer registro: {source_records[0]}")
        if row_errors:
            logger.debug(f"  → Errores de validación: {len(row_errors)}")
            for err in row_errors[:3]:
                logger.debug(f"      - {err}")
        logger.debug("=" * 80 + "\n")

        return source_records, row_errors

    def _validate_source_records(
        self,
        source_records: list[InvoiceRecord],
        row_errors: list[dict],
        file_log_id: int,
        report: ExecutionReport,
    ) -> None:
        """Valida los registros fuente y actualiza el reporte."""
        is_valid = len(row_errors) == 0
        missing = []
        extra = []
        self.tracker.log_file_schema(file_log_id, is_valid, missing, extra)
        report.source_row_count += len(source_records)
        report.valid_row_count += len(source_records)
        report.validation_errors.extend(row_errors)

    def _download_consolidated(self, consolidated_file_id: str) -> pd.DataFrame:
        """Descarga el archivo consolidado desde Drive y lo retorna como DataFrame."""
        local_consolidated = Path(f"{self.config.downloads.temp_path}/consolidado.xlsx")
        local_consolidated.parent.mkdir(parents=True, exist_ok=True)
        logger.debug("debug_downloading_consolidated")
        logger.debug(f"  → Descargando archivo consolidado...")
        self.drive.download_file(consolidated_file_id, local_consolidated)
        logger.debug(f"  → Leyendo hoja: {self.config.excel.consolidated_sheet}")

        df_consolidated = self.reader.read(
            local_consolidated,
            self.config.excel.consolidated_sheet,
            header_row=self.config.excel.header_row,
        )
        logger.debug("debug_consolidated_read", rows=len(df_consolidated))
        logger.debug(f"  → Registros en consolidado: {len(df_consolidated)}")

        return df_consolidated

    def _merge_and_upsert(
        self,
        df_consolidated: pd.DataFrame,
        source_records: list[InvoiceRecord],
        transformer: RowTransformer,
        run_id: str,
        file_log_id: int,
        row_errors: list[dict],
    ) -> UpsertResult:
        """Convierte consolidado a registros, realiza upsert y loguea resultados."""
        consolidated_records = self._dataframe_to_records(df_consolidated, transformer)
        logger.debug(f"  → Registros parseados: {len(consolidated_records)}")
        logger.debug("=" * 80 + "\n")

        upsert_result = self._upsert(consolidated_records, source_records)
        self._log_upsert_records(run_id, file_log_id, source_records, upsert_result)

        logger.debug(
            "debug_upsert_result",
            filename=None,
            inserted=upsert_result.inserted,
            updated=upsert_result.updated,
            unchanged=upsert_result.unchanged,
        )
        logger.debug("\n" + "=" * 80)
        logger.debug(f"DEBUG: Resultado del upsert:")
        logger.debug(f"  → Insertados: {upsert_result.inserted}")
        logger.debug(f"  → Actualizados: {upsert_result.updated}")
        logger.debug(f"  → Sin cambios: {upsert_result.unchanged}")
        logger.debug("=" * 80 + "\n")

        # Log validation errors to tracker
        if row_errors:
            error_batch = [
                {
                    "run_uuid": run_id,
                    "file_log_id": file_log_id,
                    "row_index": err["row_index"],
                    "invoice_number": None,
                    "reference_number": None,
                    "action": "VALIDATION_ERROR",
                    "error_message": err["error"],
                }
                for err in row_errors
            ]
            self.tracker.log_records_batch(error_batch)

        return upsert_result

    def _reconcile_and_write(
        self,
        source_records: list[InvoiceRecord],
        upsert_result: UpsertResult,
        consolidated_file_id: str,
        report: ExecutionReport,
    ) -> None:
        """Realiza reconciliación, escribe nuevos registros y actualiza Drive."""
        self._reconcile(report, source_records, upsert_result)

        new_records = [r for r in upsert_result.all_records if r.status == RecordStatus.NEW]
        df_inserts = self._records_to_dataframe(new_records)

        if not df_inserts.empty:
            local_consolidated = Path(f"{self.config.downloads.temp_path}/consolidado.xlsx")
            self.writer.write(
                df_inserts,
                local_consolidated,
                self.config.excel.consolidated_sheet,
                header_row=self.config.excel.header_row,
                data_start_row=self.config.excel.data_start_row,
            )
            self.drive.update_file(consolidated_file_id, local_consolidated)

        report.inserted_count += upsert_result.inserted
        report.updated_count += upsert_result.updated
        report.unchanged_count += upsert_result.unchanged

    def _finalize_file_processing(
        self,
        source_file: dict,
        file_log_id: int,
        source_records: list[InvoiceRecord],
        row_errors: list[dict],
    ) -> None:
        """Finaliza el procesamiento: mueve archivo a backup y loguea completitud."""
        self.lifecycle.move_to_backup(source_file["file_id"])

        self.tracker.log_file_finish(
            file_log_id,
            "COMPLETED",
            rows_total=len(source_records),
            rows_valid=len(source_records),
            rows_error=len(row_errors),
            error_message=None,
        )

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

        logger.debug("upsert_start", existing_count=len(existing), incoming_count=len(incoming))

        # Solo insertar nuevos registros, ignorar actualizaciones
        for record in incoming:
            pk = record.primary_key
            if pk in existing_map:
                # Ignorar registros existentes (no actualizar ni borrar)
                logger.debug("upsert_skipped_existing", pk=pk)
                continue

            # Solo insertar nuevos registros
            existing_map[pk] = record
            result.inserted += 1

            # Loguear todos los campos del registro insertado en modo debug
            logger.debug(
                "upsert_inserted_new_record",
                pk=pk,
                invoice=record.invoice_number,
                ref=record.reference_number,
                carrier=record.carrier_name,
                ship=record.ship_name,
                guides=record.dispatch_guides,
                date=record.invoice_date.isoformat(),
                description=record.description,
                net_amount=float(record.net_amount),
                tax_amount=float(record.tax_amount),
                total_amount=float(record.total_amount),
                currency=record.currency,
            )

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
                record = transformer.transform_row(row.to_dict(), source_name="consolidado")
                records.append(record)
            except Exception:
                continue
        return records

    def _records_to_dataframe(self, records: list[InvoiceRecord]) -> pd.DataFrame:
        CONSOLIDATED_COLUMNS = [
            "N° Factura",
            "Empresa Transporte",
            "Nave",
            "Órdenes de Embarque",
            "Guías de Despacho",
            "Total Servicio ($)",
            "Fecha Emisión",
            "Fecha Recepción Digital",
            "Aprobado por:",
            "Estado Operaciones",
            "Fecha Aprobación Operaciones",
            "Observaciones",
        ]

        rows = []
        for r in records:
            rows.append(
                {
                    "N° Factura": r.invoice_number,
                    "Empresa Transporte": r.carrier_name,
                    "Nave": r.ship_name,
                    "Órdenes de Embarque": r.reference_number,
                    "Guías de Despacho": r.dispatch_guides,
                    "Total Servicio ($)": float(r.total_amount),
                    "Fecha Emisión": r.invoice_date,
                    "Fecha Recepción Digital": r.fecha_recepcion_digital,
                    "Aprobado por:": r.aprobado_por,
                    "Estado Operaciones": r.estado_operaciones,
                    "Fecha Aprobación Operaciones": r.fecha_aprobacion_operaciones,
                    "Observaciones": r.description,
                }
            )
        return pd.DataFrame(rows, columns=CONSOLIDATED_COLUMNS)

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
