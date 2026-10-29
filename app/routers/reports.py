import csv
import io
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.security import get_current_user
from app.services import program_service, report_service, section_service
from app.templating import render

router = APIRouter(prefix="/reports", tags=["reports"])


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format.")


def _parse_positive_int(value: str | None, *, label: str) -> int | None:
    if value is None or not value.strip():
        return None
    raw = value.strip()
    if not raw.isdigit() or int(raw) < 1:
        raise HTTPException(status_code=400, detail=f"{label} must be a positive integer.")
    return int(raw)


def _parse_filters(request: Request) -> dict:
    params = request.query_params
    date_from = _parse_date(params.get("date_from"))
    date_to = _parse_date(params.get("date_to"))
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from must not be after date_to.")
    year_level = _parse_positive_int(params.get("year_level"), label="Year level")
    if year_level is not None and year_level not in (1, 2, 3, 4):
        raise HTTPException(status_code=400, detail="Invalid year level.")
    section_id = _parse_positive_int(params.get("section_id"), label="Section")
    program_id = _parse_positive_int(params.get("program_id"), label="Program")
    group_by = params.get("group_by", "")
    if group_by not in ("", "program"):
        raise HTTPException(status_code=400, detail="Invalid grouping option.")
    return {
        "date_from": date_from,
        "date_to": date_to,
        "year_level": year_level,
        "section_id": section_id,
        "program_id": program_id,
        "group_by": group_by,
    }


def _query_or_404(db: Session, filters: dict):
    if filters["section_id"] is not None:
        section = section_service.get_section(db, filters["section_id"])
        if section is None:
            raise HTTPException(status_code=400, detail="Selected section does not exist.")
    if filters["program_id"] is not None and program_service.get_program(db, filters["program_id"]) is None:
        raise HTTPException(status_code=400, detail="Selected program does not exist.")
    return report_service.query_students_report(
        db,
        date_from=filters["date_from"],
        date_to=filters["date_to"],
        year_level=filters["year_level"],
        section_id=filters["section_id"],
        program_id=filters["program_id"],
    )


def _template_context(request: Request, db: Session, filters: dict, students: list, **extra) -> dict:
    return {
        "students": students,
        "sections": section_service.list_sections(db, active_only=True),
        "programs": program_service.list_programs(db),
        "has_filters": True,
        "filter_qs": _filter_qs(request),
        "filters": {
            "date_from": request.query_params.get("date_from", ""),
            "date_to": request.query_params.get("date_to", ""),
            "year_level": request.query_params.get("year_level", ""),
            "section_id": request.query_params.get("section_id", ""),
            "program_id": request.query_params.get("program_id", ""),
            "group_by": filters["group_by"],
        },
        **extra,
    }


def _filter_qs(request: Request) -> str:
    """Query string carrying the active filters for print/CSV links."""
    params = request.query_params
    parts = []
    for key in ("date_from", "date_to", "year_level", "section_id", "program_id", "group_by"):
        value = params.get(key, "")
        if value:
            parts.append(f"{key}={value}")
    return "&".join(parts)


@router.get("")
def reports_page(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return render(
        request,
        "reports/index.html",
        {
            "students": [],
            "sections": section_service.list_sections(db, active_only=True),
            "programs": program_service.list_programs(db),
            "has_filters": False,
            "filters": {},
        },
    )


@router.get("/result")
def reports_result(
    request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)
):
    filters = _parse_filters(request)
    students = _query_or_404(db, filters)
    totals = []
    if filters["group_by"] == "program":
        totals = report_service.count_by_program(
            db,
            date_from=filters["date_from"],
            date_to=filters["date_to"],
            year_level=filters["year_level"],
            section_id=filters["section_id"],
            program_id=filters["program_id"],
        )
    return render(
        request,
        "reports/index.html",
        _template_context(request, db, filters, students, totals_by_program=totals),
    )


@router.get("/print")
def reports_print(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    filters = _parse_filters(request)
    students = _query_or_404(db, filters)
    totals = []
    if filters["group_by"] == "program":
        totals = report_service.count_by_program(
            db,
            date_from=filters["date_from"],
            date_to=filters["date_to"],
            year_level=filters["year_level"],
            section_id=filters["section_id"],
            program_id=filters["program_id"],
        )
    context = _template_context(request, db, filters, students, totals_by_program=totals)
    return render(request, "reports/print.html", context)


@router.get("/export.csv")
def reports_csv(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    filters = _parse_filters(request)
    students = _query_or_404(db, filters)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(report_service.CSV_HEADER)
    writer.writerows(report_service.student_report_rows(students))
    output = buffer.getvalue().encode("utf-8-sig")
    filename = f"students_report_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=output,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
