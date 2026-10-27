import csv
import io
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.security import get_current_user
from app.services import report_service, section_service
from app.templating import render

router = APIRouter(prefix="/reports", tags=["reports"])


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format.")


def _parse_filters(request: Request) -> dict:
    params = request.query_params
    date_from = _parse_date(params.get("date_from"))
    date_to = _parse_date(params.get("date_to"))
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from must not be after date_to.")
    year_level = params.get("year_level")
    year_level_int = int(year_level) if year_level else None
    if year_level_int is not None and year_level_int not in (1, 2, 3, 4):
        raise HTTPException(status_code=400, detail="Invalid year level.")
    section_id = params.get("section_id")
    section_id_int = int(section_id) if section_id else None
    return {
        "date_from": date_from,
        "date_to": date_to,
        "year_level": year_level_int,
        "section_id": section_id_int,
    }


def _query_or_404(db: Session, filters: dict):
    if filters["section_id"] is not None:
        section = section_service.get_section(db, filters["section_id"])
        if section is None:
            raise HTTPException(status_code=400, detail="Selected section does not exist.")
    return report_service.query_students_report(db, **filters)


@router.get("")
def reports_page(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    sections = section_service.list_sections(db, active_only=True)
    return render(
        request,
        "reports/index.html",
        {"students": [], "sections": sections, "has_filters": False, "filters": {}},
    )


@router.get("/result")
def reports_result(
    request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)
):
    filters = _parse_filters(request)
    students = _query_or_404(db, filters)
    sections = section_service.list_sections(db, active_only=True)
    return render(
        request,
        "reports/index.html",
        {
            "students": students,
            "sections": sections,
            "has_filters": True,
            "filters": {
                "date_from": request.query_params.get("date_from", ""),
                "date_to": request.query_params.get("date_to", ""),
                "year_level": request.query_params.get("year_level", ""),
                "section_id": request.query_params.get("section_id", ""),
            },
        },
    )


@router.get("/print")
def reports_print(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    filters = _parse_filters(request)
    students = _query_or_404(db, filters)
    return render(
        request,
        "reports/print.html",
        {
            "students": students,
            "filters": {
                "date_from": request.query_params.get("date_from", ""),
                "date_to": request.query_params.get("date_to", ""),
                "year_level": request.query_params.get("year_level", ""),
                "section_id": request.query_params.get("section_id", ""),
            },
        },
    )


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
