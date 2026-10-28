import csv
import io
import json

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.masterlist import ImportBatch, MasterlistStagingBatch, StudentMasterlist
from app.security import require_admin
from app.services import masterlist_service
from app.templating import render

router = APIRouter(prefix="/admin/masterlist", tags=["masterlist"])

CSV_INJECTION_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _sanitize(value: str) -> str:
    if value.startswith(CSV_INJECTION_PREFIXES):
        return "'" + value
    return value


def _get_batch(db: Session, batch_id: int) -> MasterlistStagingBatch:
    # Background jobs mutate batch state in a different session; drop any
    # identity-mapped snapshot so we read current values.
    db.expire_all()
    batch = db.get(MasterlistStagingBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404)
    return batch


@router.get("")
def masterlist_page(request: Request, db: Session = Depends(get_db), admin=Depends(require_admin)):
    batches = list(
        db.scalars(
            select(MasterlistStagingBatch).order_by(MasterlistStagingBatch.id.desc()).limit(10)
        )
    )
    history = list(db.scalars(select(ImportBatch).order_by(ImportBatch.id.desc()).limit(10)))
    from sqlalchemy import func

    total = db.scalar(select(func.count(StudentMasterlist.id))) or 0
    settings = get_settings()
    return render(
        request,
        "admin/masterlist.html",
        {
            "staging_batches": batches,
            "history": history,
            "masterlist_count": total,
            "max_upload_mb": settings.masterlist_max_upload_bytes // (1024 * 1024),
        },
    )


@router.post("/upload")
def upload_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    settings = get_settings()
    file_name = (file.filename or "upload.csv").strip() or "upload.csv"
    if not file_name.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted.")
    data = file.file.read(settings.masterlist_max_upload_bytes + 1)
    if len(data) > settings.masterlist_max_upload_bytes:
        mb = settings.masterlist_max_upload_bytes // (1024 * 1024)
        raise HTTPException(status_code=400, detail=f"File exceeds the {mb} MB upload limit.")
    headers, rows, error = masterlist_service.parse_csv_bytes(data)
    if error:
        raise HTTPException(status_code=400, detail=error)
    batch = masterlist_service.create_staging_batch(
        db, file_name=file_name, uploaded_by=admin.id, headers=headers, data_rows=rows
    )
    if batch.status == "uploaded":
        return {
            "batch_id": batch.id,
            "mapping_required": False,
            "headers": headers,
            "mapping": json.loads(batch.mapping_json),
        }
    return {"batch_id": batch.id, "mapping_required": True, "headers": headers, "mapping": {}}


@router.post("/{batch_id}/validate")
def validate_with_mapping(
    batch_id: int,
    background_tasks: BackgroundTasks,
    mapping: str = Form(...),
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    batch = _get_batch(db, batch_id)
    if batch.status not in ("uploaded", "mapping_required"):
        raise HTTPException(status_code=409, detail="Batch is not awaiting validation.")
    try:
        mapping_dict = json.loads(mapping or "{}")
        if not isinstance(mapping_dict, dict):
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid mapping payload.")
    errors = masterlist_service.apply_mapping(db, batch, mapping_dict)
    if errors:
        return {"batch_id": batch.id, "errors": errors}
    background_tasks.add_task(masterlist_service.validate_batch, batch.id, mapping_dict)
    return {"batch_id": batch.id, "started": True}


@router.post("/{batch_id}/start-validation")
def start_validation_auto(
    batch_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    """Kick off validation for an upload whose headers auto-mapped completely."""
    batch = _get_batch(db, batch_id)
    if batch.status != "uploaded":
        raise HTTPException(status_code=409, detail="Batch is not awaiting validation.")
    mapping_dict = json.loads(batch.mapping_json or "{}")
    background_tasks.add_task(masterlist_service.validate_batch, batch.id, mapping_dict)
    return {"batch_id": batch.id, "started": True}


@router.get("/{batch_id}/status")
def batch_status(
    batch_id: int, db: Session = Depends(get_db), admin=Depends(require_admin)
):
    batch = _get_batch(db, batch_id)
    return masterlist_service.get_status(db, batch)


@router.get("/{batch_id}/errors.csv")
def error_report(
    batch_id: int, db: Session = Depends(get_db), admin=Depends(require_admin)
):
    batch = _get_batch(db, batch_id)
    rows = masterlist_service.error_report_rows(db, batch)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "Row",
            "student_number",
            "first_name",
            "last_name",
            "middle_initial",
            "telephone",
            "email",
            "status",
            "error",
        ]
    )
    for row in rows:
        writer.writerow([_sanitize(cell) for cell in row])
    return Response(
        content=buffer.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="masterlist_errors_batch_{batch_id}.csv"'
        },
    )


@router.post("/{batch_id}/replace")
def replace_masterlist(
    batch_id: int,
    background_tasks: BackgroundTasks,
    confirm: str = Form(...),
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    batch = _get_batch(db, batch_id)
    if confirm != "REPLACE":
        raise HTTPException(
            status_code=400,
            detail="Type REPLACE to confirm replacing the entire masterlist.",
        )
    if batch.status != "validated":
        raise HTTPException(status_code=409, detail="Batch is not ready for import.")
    busy = db.scalar(
        select(MasterlistStagingBatch.id).where(MasterlistStagingBatch.status == "importing")
    )
    if busy is not None:
        raise HTTPException(status_code=409, detail="Another import is already in progress.")
    background_tasks.add_task(masterlist_service.run_replace_job, batch.id, admin.id)
    return {"batch_id": batch.id, "started": True}
