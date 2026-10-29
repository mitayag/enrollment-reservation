from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Section(Base):
    __tablename__ = "sections"
    __table_args__ = (
        CheckConstraint("year_level >= 1 AND year_level <= 4", name="ck_sections_year_level"),
        # Active sections are unique by (program, name); legacy sections
        # without an assigned program are exempt until migration finalize.
        Index(
            "uq_sections_program_name",
            "program_id",
            "name",
            unique=True,
            postgresql_where=text("is_active AND program_id IS NOT NULL"),
            sqlite_where=text("is_active AND program_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    year_level: Mapped[int]
    # Nullable until an administrator assigns programs to pre-existing
    # sections; the finalize migration enforces NOT NULL afterwards.
    program_id: Mapped[int | None] = mapped_column(
        ForeignKey("programs.id", ondelete="RESTRICT"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))

    program: Mapped["Program | None"] = relationship("Program", back_populates="sections")
    students: Mapped[list["Student"]] = relationship("Student", back_populates="section")
    creator: Mapped["User"] = relationship("User")


from app.models.program import Program  # noqa: E402
from app.models.student import Student  # noqa: E402
