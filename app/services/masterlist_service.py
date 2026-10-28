"""Student masterlist CSV import: parsing, validation, atomic replacement.

CSV header assumptions (documented in README):
- Canonical headers: student_number, first_name, last_name, middle_initial,
  telephone, email (case-insensitive; spaces/dashes treated as underscores).
- Common aliases are accepted (see HEADER_ALIASES); anything else is offered
  in the column-mapping UI.
- Only first_name and last_name must be present (mapped); all other columns
  are optional.
"""
import csv
import io
import json
import logging
from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.masterlist import (
    ImportBatch,
    MasterlistImportLock,
    MasterlistStagingBatch,
    MasterlistStagingRow,
    StudentMasterlist,
)

logger = logging.getLogger("enrollment.masterlist")

CANONICAL_FIELDS = [
    "student_number",
    "first_name",
    "last_name",
    "middle_initial",
    "telephone",
    "email",
]
REQUIRED_FIELDS = {"first_name", "last_name"}
FIELD_LIMITS = {
    "student_number": 50,
    "first_name": 100,
    "last_name": 100,
    "middle_initial": 10,
    "telephone": 50,
    "email": 255,
}
HEADER_ALIASES = {
    "student_number": {"student_number", "student_no", "student_no_", "studentid", "student_id", "id_no", "lrn"},
    "first_name": {"first_name", "firstname", "given_name", "first"},
    "last_name": {"last_name", "lastname", "surname", "family_name", "last"},
    "middle_initial": {"middle_initial", "middleinitial", "mi", "middle_name", "middlename"},
    "telephone": {"telephone", "phone", "phone_number", "mobile", "contact_number", "contact"},
    "email": {"email", "email_address", "e_mail"},
}
VALIDATION_CHUNK = 100
LOCK_ID = 1


def normalize_header(header: str) -> str:
    normalized = header.strip().lower().replace(" ", "_").replace("-", "_")
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    return normalized


def auto_map(headers: list[str]) -> dict[str, str]:
    """Map canonical fields to the best-matching header; only full matches."""
    normalized = {normalize_header(h): h for h in headers}
    mapping: dict[str, str] = {}
    for field, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                mapping[field] = normalized[alias]
                break
    return mapping


def mapping_is_complete(mapping: dict[str, str]) -> bool:
    return all(f in mapping and mapping[f] for f in REQUIRED_FIELDS)


def parse_csv_bytes(data: bytes) -> tuple[list[str] | None, list[list[str]] | None, str | None]:
    """Return (headers, data_rows, error_message). Never log file contents."""
    settings = get_settings()
    if len(data) > settings.masterlist_max_upload_bytes:
        mb = settings.masterlist_max_upload_bytes // (1024 * 1024)
        return None, None, f"File exceeds the {mb} MB upload limit."
    if not data:
        return None, None, "File is empty."
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None, None, "File must be UTF-8 encoded."
    if "\x00" in text:
        return None, None, "File contains binary data and was rejected."
    stripped = text.lstrip().lower()
    if stripped.startswith("<!doctype html") or stripped.startswith("<html"):
        return None, None, "File does not look like a CSV document."
    try:
        rows = list(csv.reader(io.StringIO(text)))
    except csv.Error:
        return None, None, "File could not be parsed as CSV."
    rows = [r for r in rows if any(cell.strip() for cell in r)]
    if not rows:
        return None, None, "CSV contains no rows."
    headers = [h.strip() for h in rows[0]]
    if not any(headers):
        return None, None, "CSV header row is empty."
    return headers, rows[1:], None


def create_staging_batch(
    db: Session, *, file_name: str, uploaded_by: int, headers: list[str], data_rows: list[list[str]]
) -> MasterlistStagingBatch:
    mapping = auto_map(headers)
    complete = mapping_is_complete(mapping)
    batch = MasterlistStagingBatch(
        file_name=file_name[:255],
        uploaded_by=uploaded_by,
        status="uploaded" if complete else "mapping_required",
        headers_json=json.dumps(headers),
        mapping_json=json.dumps(mapping if complete else {}),
        total_rows=len(data_rows),
    )
    db.add(batch)
    db.flush()
    width = len(headers)
    for index, raw in enumerate(data_rows, start=2):  # row 1 is the header
        cells = list(raw[:width]) + [""] * max(width - len(raw), 0)
        values = {
            field: (cells[headers.index(mapping[field])].strip() if field in mapping else "")
            for field in CANONICAL_FIELDS
        }
        db.add(
            MasterlistStagingRow(
                batch_id=batch.id,
                row_number=index,
                student_number=values["student_number"][: FIELD_LIMITS["student_number"]] or None,
                first_name=values["first_name"][: FIELD_LIMITS["first_name"]] or None,
                last_name=values["last_name"][: FIELD_LIMITS["last_name"]] or None,
                middle_initial=values["middle_initial"][: FIELD_LIMITS["middle_initial"]] or None,
                telephone=values["telephone"][: FIELD_LIMITS["telephone"]] or None,
                email=values["email"][: FIELD_LIMITS["email"]] or None,
                status="pending",
                raw_json=json.dumps(cells),
            )
        )
    db.commit()
    return batch


def apply_mapping(db: Session, batch: MasterlistStagingBatch, mapping: dict[str, str]) -> list[str]:
    errors: list[str] = []
    headers: list[str] = json.loads(batch.headers_json)
    for field, header in mapping.items():
        if field not in CANONICAL_FIELDS:
            errors.append(f"Unknown field: {field}.")
        elif header and header not in headers:
            errors.append(f"Header '{header}' does not exist in the uploaded file.")
    if not mapping_is_complete(mapping):
        errors.append("first_name and last_name must be mapped.")
    if errors:
        return errors
    batch.mapping_json = json.dumps({k: v for k, v in mapping.items() if v})
    db.commit()
    return []


def _validate_row_values(row: MasterlistStagingRow) -> list[str]:
    errors: list[str] = []
    if not (row.first_name or "").strip():
        errors.append("first_name is required.")
    if not (row.last_name or "").strip():
        errors.append("last_name is required.")
    for field in CANONICAL_FIELDS:
        value = getattr(row, field) or ""
        if len(value) > FIELD_LIMITS[field]:
            errors.append(f"{field} exceeds {FIELD_LIMITS[field]} characters.")
    if row.email and "@" not in row.email:
        errors.append("email is not a valid address.")
    return errors


def validate_batch(batch_id: int, mapping: dict[str, str]) -> None:
    """Worker: validate staged rows in chunks, committing real progress."""
    from app.database import SessionLocal  # late import so tests can patch

    db = SessionLocal()
    try:
        batch = db.get(MasterlistStagingBatch, batch_id)
        if batch is None:
            return
        batch.status = "validating"
        batch.processed_rows = 0
        batch.valid_rows = 0
        batch.invalid_rows = 0
        batch.duplicate_count = 0
        batch.error_message = None
        db.commit()

        rows = list(
            db.scalars(
                select(MasterlistStagingRow)
                .where(MasterlistStagingRow.batch_id == batch_id)
                .order_by(MasterlistStagingRow.row_number)
            )
        )
        headers: list[str] = json.loads(batch.headers_json or "[]")
        mapping: dict[str, str] = json.loads(batch.mapping_json or "{}")
        seen_numbers: set[str] = set()
        seen_identities: dict[tuple, int] = {}
        for i, row in enumerate(rows, start=1):
            # Materialize mapped columns from the stored raw cells (the
            # mapping may have been chosen after upload).
            cells = json.loads(row.raw_json) if row.raw_json else []
            for field in CANONICAL_FIELDS:
                header = mapping.get(field)
                value = ""
                if header and header in headers:
                    idx = headers.index(header)
                    if idx < len(cells):
                        value = cells[idx].strip()[: FIELD_LIMITS[field]]
                setattr(row, field, value or None)
            errors = _validate_row_values(row)
            if errors:
                row.status = "invalid"
                row.error_message = "; ".join(errors)[:500]
                row.potential_duplicate = False
                batch.invalid_rows += 1
            else:
                number_key = (row.student_number or "").strip().lower()
                if number_key and number_key in seen_numbers:
                    row.status = "duplicate"
                    row.error_message = "Duplicate student_number within this file."
                    row.potential_duplicate = False
                    batch.duplicate_count += 1
                else:
                    if number_key:
                        seen_numbers.add(number_key)
                    identity = (
                        (row.last_name or "").strip().lower(),
                        (row.first_name or "").strip().lower(),
                        (row.middle_initial or "").strip().lower(),
                        (row.telephone or row.email or "").strip().lower(),
                    )
                    if identity in seen_identities:
                        row.potential_duplicate = True
                        batch.duplicate_count += 1
                    else:
                        seen_identities[identity] = row.id
                        row.potential_duplicate = False
                    row.status = "valid"
                    row.error_message = None
                    batch.valid_rows += 1
            batch.processed_rows = i
            if i % VALIDATION_CHUNK == 0:
                db.commit()
        batch.status = "validated"
        db.commit()
        logger.info(
            "masterlist batch %s validated total=%s valid=%s invalid=%s duplicates=%s",
            batch_id,
            batch.total_rows,
            batch.valid_rows,
            batch.invalid_rows,
            batch.duplicate_count,
        )
    except Exception:
        logger.exception("masterlist validation failed for batch_id=%s", batch_id)
        db.rollback()
        try:
            batch = db.get(MasterlistStagingBatch, batch_id)
            if batch is not None:
                batch.status = "failed"
                batch.error_message = "Validation failed. Please try a different file."
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()


def replace_masterlist(db: Session, *, batch_id: int, actor_id: int) -> ImportBatch:
    """Atomically replace all masterlist rows with the validated batch.

    The singleton lock row is held FOR UPDATE for the whole transaction so
    concurrent replacements cannot interleave. Any error rolls back, leaving
    the previous masterlist untouched.
    """
    batch = db.get(MasterlistStagingBatch, batch_id)
    if batch is None:
        raise ValueError("Import batch not found.")
    if batch.status != "validated":
        raise ValueError("Batch is not ready for import.")
    busy = db.scalar(
        select(MasterlistStagingBatch.id).where(MasterlistStagingBatch.status == "importing")
    )
    if busy is not None:
        raise ValueError("Another import is already in progress.")
    lock = db.get(MasterlistImportLock, LOCK_ID, with_for_update=True)
    if lock is None:
        lock = MasterlistImportLock(id=LOCK_ID, note="masterlist import lock")
        db.add(lock)
        db.flush()
    staged = list(
        db.scalars(
            select(MasterlistStagingRow)
            .where(
                MasterlistStagingRow.batch_id == batch_id,
                MasterlistStagingRow.status == "valid",
            )
            .order_by(MasterlistStagingRow.row_number)
        )
    )
    if not staged:
        raise ValueError("Batch has no valid rows to import.")

    history = ImportBatch(
        file_name=batch.file_name,
        imported_by=actor_id,
        total_rows=batch.total_rows,
        valid_rows=batch.valid_rows,
        invalid_rows=batch.invalid_rows,
        duplicate_count=batch.duplicate_count,
    )
    db.add(history)
    db.flush()
    db.execute(delete(StudentMasterlist))
    for row in staged:
        db.add(
            StudentMasterlist(
                student_number=row.student_number,
                first_name=row.first_name or "",
                last_name=row.last_name or "",
                middle_initial=row.middle_initial,
                telephone=row.telephone,
                email=row.email,
                import_batch_id=history.id,
            )
        )
    batch.status = "completed"
    batch.processed_rows = batch.total_rows
    db.execute(delete(MasterlistStagingRow).where(MasterlistStagingRow.batch_id == batch_id))
    db.commit()
    logger.info(
        "masterlist replaced batch_id=%s history_id=%s rows=%s actor_id=%s",
        batch_id,
        history.id,
        history.valid_rows,
        actor_id,
    )
    return history


def run_replace_job(batch_id: int, actor_id: int) -> None:
    """Background task: replace masterlist or mark the batch failed (no PII logged)."""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        replace_masterlist(db, batch_id=batch_id, actor_id=actor_id)
    except Exception:
        logger.exception("masterlist replace failed for batch_id=%s", batch_id)
        db.rollback()
        try:
            batch = db.get(MasterlistStagingBatch, batch_id)
            if batch is not None and batch.status != "completed":
                batch.status = "failed"
                batch.error_message = "Import failed and the previous masterlist was preserved."
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()


def get_status(db: Session, batch: MasterlistStagingBatch) -> dict[str, Any]:
    total = batch.total_rows or 0
    processed = batch.processed_rows or 0
    progress = int(processed * 100 / total) if total else (100 if batch.status == "validated" else 0)
    mapping = json.loads(batch.mapping_json or "{}")
    headers = json.loads(batch.headers_json or "[]")
    preview = list(
        db.scalars(
            select(MasterlistStagingRow)
            .where(MasterlistStagingRow.batch_id == batch.id)
            .order_by(MasterlistStagingRow.row_number)
            .limit(20)
        )
    )
    return {
        "batch_id": batch.id,
        "status": batch.status,
        "file_name": batch.file_name,
        "total_rows": batch.total_rows,
        "processed_rows": batch.processed_rows,
        "valid_rows": batch.valid_rows,
        "invalid_rows": batch.invalid_rows,
        "duplicate_count": batch.duplicate_count,
        "progress_percent": progress,
        "error_message": batch.error_message,
        "mapping_required": batch.status == "mapping_required",
        "headers": headers,
        "mapping": mapping,
        "preview": [
            {
                "row_number": r.row_number,
                "student_number": r.student_number,
                "first_name": r.first_name,
                "last_name": r.last_name,
                "middle_initial": r.middle_initial,
                "telephone": r.telephone,
                "email": r.email,
                "status": r.status,
                "error_message": r.error_message,
                "potential_duplicate": r.potential_duplicate,
            }
            for r in preview
        ],
    }


def error_report_rows(db: Session, batch: MasterlistStagingBatch) -> list[list[str]]:
    rows = list(
        db.scalars(
            select(MasterlistStagingRow)
            .where(
                MasterlistStagingRow.batch_id == batch.id,
                MasterlistStagingRow.status.in_(("invalid", "duplicate")),
            )
            .order_by(MasterlistStagingRow.row_number)
        )
    )
    return [
        [
            str(r.row_number),
            r.student_number or "",
            r.first_name or "",
            r.last_name or "",
            r.middle_initial or "",
            r.telephone or "",
            r.email or "",
            r.status,
            r.error_message or "",
        ]
        for r in rows
    ]


def lookup_students(
    db: Session, *, q: str, limit: int = 10, offset: int = 0
) -> tuple[list[StudentMasterlist], int]:
    stmt = select(StudentMasterlist)
    term = (q or "").strip()
    if term:
        like = f"%{term}%"
        stmt = stmt.where(
            or_(
                StudentMasterlist.student_number.ilike(like),
                StudentMasterlist.first_name.ilike(like),
                StudentMasterlist.last_name.ilike(like),
                func.concat(StudentMasterlist.first_name, " ", StudentMasterlist.last_name).ilike(like),
                func.concat(StudentMasterlist.last_name, ", ", StudentMasterlist.first_name).ilike(like),
            )
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(
        db.scalars(
            stmt.order_by(StudentMasterlist.last_name, StudentMasterlist.first_name)
            .offset(max(offset, 0))
            .limit(min(max(limit, 1), 25))
        )
    )
    return rows, total
