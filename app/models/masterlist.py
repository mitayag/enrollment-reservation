from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class StudentMasterlist(Base):
    """Staging-free masterlist of students imported from administrator CSV uploads.

    Rows are replaced wholesale by each confirmed import batch; enrollment
    reservations in `students` keep their own copy of key fields plus the
    stable student_number, so replacement never breaks existing reservations.
    """

    __tablename__ = "student_masterlist"
    __table_args__ = (
        Index("ix_student_masterlist_student_number", "student_number"),
        Index("ix_student_masterlist_last_first", "last_name", "first_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    middle_initial: Mapped[str | None] = mapped_column(String(10), nullable=True)
    telephone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    import_batch_id: Mapped[int] = mapped_column(ForeignKey("import_batches.id", ondelete="RESTRICT"))


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    file_name: Mapped[str] = mapped_column(String(255))
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    imported_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    valid_rows: Mapped[int] = mapped_column(Integer, default=0)
    invalid_rows: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)


class MasterlistStagingBatch(Base):
    """DB-backed state for an uploaded CSV pending validation/import."""

    __tablename__ = "masterlist_staging_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    file_name: Mapped[str] = mapped_column(String(255))
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # uploaded -> mapping_required -> validating -> validated -> importing -> completed / failed
    status: Mapped[str] = mapped_column(String(30), default="uploaded")
    headers_json: Mapped[str] = mapped_column(Text, default="[]")
    mapping_json: Mapped[str] = mapped_column(Text, default="{}")
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    processed_rows: Mapped[int] = mapped_column(Integer, default=0)
    valid_rows: Mapped[int] = mapped_column(Integer, default=0)
    invalid_rows: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(String(255), nullable=True)

    rows: Mapped[list["MasterlistStagingRow"]] = relationship(
        "MasterlistStagingRow", back_populates="batch", cascade="all, delete-orphan"
    )


class MasterlistStagingRow(Base):
    __tablename__ = "masterlist_staging_rows"
    __table_args__ = (Index("ix_masterlist_staging_rows_batch", "batch_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("masterlist_staging_batches.id", ondelete="CASCADE")
    )
    row_number: Mapped[int] = mapped_column(Integer)
    student_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    middle_initial: Mapped[str | None] = mapped_column(String(10), nullable=True)
    telephone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/valid/invalid/duplicate
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    potential_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    batch: Mapped[MasterlistStagingBatch] = relationship("MasterlistStagingBatch", back_populates="rows")


class MasterlistImportLock(Base):
    """Singleton row used to serialize masterlist replacement imports."""

    __tablename__ = "masterlist_import_lock"

    id: Mapped[int] = mapped_column(primary_key=True)
    note: Mapped[str | None] = mapped_column(String(50), nullable=True)
