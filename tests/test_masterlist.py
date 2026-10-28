import json

from app.models.masterlist import ImportBatch, MasterlistStagingBatch, MasterlistStagingRow, StudentMasterlist
from app.services import masterlist_service
from tests.conftest import csrf_from, login, make_section

CANONICAL = "student_number,first_name,last_name,middle_initial,telephone,email\n"


def upload_csv(client, content: bytes, filename: str = "students.csv", token: str | None = None):
    token = token or csrf_from(client, "/admin/masterlist")
    if isinstance(content, str):
        content = content.encode("utf-8")
    return client.post(
        "/admin/masterlist/upload",
        files={"file": (filename, content, "text/csv")},
        data={"_csrf": token},
    )


def run_validation(client, db_session, batch_id: int, mapping: dict | None = None):
    """Trigger validation (background task runs synchronously under TestClient)."""
    if mapping is None:
        resp = client.post(f"/admin/masterlist/{batch_id}/start-validation", data={"_csrf": csrf_from(client, "/admin/masterlist")})
    else:
        resp = client.post(
            f"/admin/masterlist/{batch_id}/validate",
            data={"mapping": json.dumps(mapping), "_csrf": csrf_from(client, "/admin/masterlist")},
        )
    assert resp.status_code == 200, resp.text
    status = client.get(f"/admin/masterlist/{batch_id}/status").json()
    return status


class TestMasterlistAccessControl:
    def test_faculty_blocked_from_masterlist(self, client, seed_users):
        login(client, "facultya@test.local", "faculty-secret-pw-1")
        assert client.get("/admin/masterlist", follow_redirects=False).status_code == 403
        assert upload_csv(client, CANONICAL + "1,A,B\n", token=csrf_from(client, "/")).status_code == 403

    def test_anonymous_redirected(self, client):
        assert client.get("/admin/masterlist", follow_redirects=False).status_code == 303

    def test_admin_page_loads(self, client, seed_users):
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = client.get("/admin/masterlist")
        assert resp.status_code == 200
        assert "Student Masterlist" in resp.text


class TestUploadValidation:
    def test_rejects_non_csv_extension(self, client, seed_users):
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = upload_csv(client, b"a,b\n1,2\n", filename="students.xlsx")
        assert resp.status_code == 400

    def test_rejects_invalid_utf8(self, client, seed_users):
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = upload_csv(client, b"\xff\xfe\x00\x01garbage\x00")
        assert resp.status_code == 400
        assert "UTF-8" in resp.json()["detail"]

    def test_rejects_html_content(self, client, seed_users):
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = upload_csv(client, b"<!DOCTYPE html><html><body>nope</body></html>", filename="fake.csv")
        assert resp.status_code == 400

    def test_rejects_oversized_file(self, client, seed_users):
        login(client, "admin@test.local", "admin-secret-pw-123")
        filler = "9" * 90 + ",A" + "a" * 90 + ",B" + "b" * 90 + ",C,09170000000,x@y.com\n"
        payload = (CANONICAL + filler * 120000).encode()  # ~11 MB
        assert len(payload) > 10 * 1024 * 1024
        resp = upload_csv(client, payload)
        assert resp.status_code == 400
        assert "10 MB" in resp.json()["detail"]

    def test_requires_csv_headers(self, client, seed_users):
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = upload_csv(client, "\n\n")
        assert resp.status_code == 400

    def test_unrecognized_headers_require_mapping(self, client, seed_users):
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = upload_csv(client, "Pangalan,Apelyido\nJuan,Dela Cruz\n")
        assert resp.status_code == 200
        data = resp.json()
        assert data["mapping_required"] is True
        assert "Pangalan" in data["headers"]


class TestValidationCounts:
    def _seed(self, client, db_session, seed_users, csv_text: str):
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = upload_csv(client, csv_text)
        assert resp.status_code == 200, resp.text
        batch_id = resp.json()["batch_id"]
        status = run_validation(client, db_session, batch_id)
        return batch_id, status

    def test_counts_and_duplicate_detection(self, client, db_session, seed_users):
        csv_text = (
            CANONICAL
            + "S1,Juan,Dela Cruz,M,09171112222,juan@example.com\n"  # valid
            + "S2,Ana,Santos,L,09173334444,ana@example.com\n"  # valid
            + "S2,Ana,Santos,L,09173334444,ana@example.com\n"  # duplicate student_number
            + "S3,,Lastname\n"  # missing first_name -> invalid
            + "S4,Bad,Email,,0917,bademail\n"  # invalid email
            + "S5,Juan,Dela Cruz,M,09171112222,juan@example.com\n"  # same identity as row 1 -> flagged
        )
        batch_id, status = self._seed(client, db_session, seed_users, csv_text)
        assert status["status"] == "validated"
        assert status["total_rows"] == 6
        assert status["processed_rows"] == 6
        assert status["valid_rows"] == 3  # S1, S2(first), S5(flagged but valid)
        assert status["invalid_rows"] == 2
        assert status["duplicate_count"] == 2  # number-dupe + identity flag
        preview = status["preview"]
        assert len(preview) == 6
        flagged = [r for r in preview if r["potential_duplicate"]]
        assert len(flagged) == 1
        assert flagged[0]["student_number"] == "S5"

    def test_preview_limited_to_20(self, client, db_session, seed_users):
        rows = "".join(f"S{i},First{i},Last{i}\n" for i in range(1, 31))
        batch_id, status = self._seed(client, db_session, seed_users, CANONICAL + rows)
        assert status["total_rows"] == 30
        assert len(status["preview"]) == 20

    def test_error_report_download(self, client, db_session, seed_users):
        csv_text = CANONICAL + "S1,Valid,Row\nS3,,Missing\nS2,Bad,Email,,,bademail\n"
        batch_id, status = self._seed(client, db_session, seed_users, csv_text)
        resp = client.get(f"/admin/masterlist/{batch_id}/errors.csv")
        assert resp.status_code == 200
        body = resp.content.decode("utf-8-sig")
        assert "first_name is required" in body
        assert "Row" in body.splitlines()[0]

    def test_error_report_sanitizes_formula_injection(self, client, db_session, seed_users):
        # Invalid email cell carrying a formula payload.
        csv_text = CANONICAL + 'S1,Cmd,Sum,,,=HYPERLINK("evil")\n'
        batch_id, status = self._seed(client, db_session, seed_users, csv_text)
        resp = client.get(f"/admin/masterlist/{batch_id}/errors.csv")
        body = resp.content.decode("utf-8-sig")
        assert "'=HYPERLINK" in body

    def test_mapping_flow(self, client, db_session, seed_users):
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = upload_csv(client, "ID Tag,Nama,Apel,MI\nS9,Juan,Dela,M\n")
        data = resp.json()
        assert data["mapping_required"] is True
        status = run_validation(
            client,
            db_session,
            data["batch_id"],
            mapping={
                "student_number": "ID Tag",
                "first_name": "Nama",
                "last_name": "Apel",
                "middle_initial": "MI",
            },
        )
        assert status["status"] == "validated"
        assert status["valid_rows"] == 1
        assert status["preview"][0]["student_number"] == "S9"

    def test_mapping_missing_required_field_rejected(self, client, db_session, seed_users):
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = upload_csv(client, "Nama,Apel\nJuan,Cruz\n")
        batch_id = resp.json()["batch_id"]
        resp = client.post(
            f"/admin/masterlist/{batch_id}/validate",
            data={"mapping": json.dumps({"first_name": "Given Name"}), "_csrf": csrf_from(client, "/admin/masterlist")},
        )
        assert resp.status_code == 200
        assert resp.json()["errors"]


class TestReplace:
    def _validated_batch(self, client, db_session, seed_users, csv_text=CANONICAL + "S1,Juan,Dela Cruz\nS2,Ana,Santos\n"):
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = upload_csv(client, csv_text)
        batch_id = resp.json()["batch_id"]
        run_validation(client, db_session, batch_id)
        return batch_id

    def _replace(self, client, batch_id, confirm="REPLACE"):
        return client.post(
            f"/admin/masterlist/{batch_id}/replace",
            data={"confirm": confirm, "_csrf": csrf_from(client, "/admin/masterlist")},
        )

    def test_replace_requires_explicit_confirmation(self, client, db_session, seed_users):
        batch_id = self._validated_batch(client, db_session, seed_users)
        resp = self._replace(client, batch_id, confirm="yes")
        assert resp.status_code == 400

    def test_replace_wipes_and_inserts_atomically(self, client, db_session, seed_users):
        # First import.
        batch_id = self._validated_batch(client, db_session, seed_users)
        assert self._replace(client, batch_id).status_code == 200
        assert db_session.query(StudentMasterlist).count() == 2
        # Second import replaces entirely.
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = upload_csv(client, CANONICAL + "S9,New,Batch\n")
        batch_id2 = resp.json()["batch_id"]
        run_validation(client, db_session, batch_id2)
        assert self._replace(client, batch_id2).status_code == 200
        rows = db_session.query(StudentMasterlist).all()
        assert len(rows) == 1
        assert rows[0].student_number == "S9"
        # Batch history recorded.
        from app.models.masterlist import ImportBatch

        history = db_session.query(ImportBatch).order_by(ImportBatch.id.desc()).all()
        assert len(history) == 2
        assert history[0].file_name == "students.csv"
        assert history[0].valid_rows == 1
        # Staging rows removed after import.
        assert db_session.query(MasterlistStagingRow).count() == 0

    def test_failed_replace_preserves_previous_masterlist(self, client, db_session, seed_users, monkeypatch):
        batch_id = self._validated_batch(client, db_session, seed_users)
        assert self._replace(client, batch_id).status_code == 200
        assert db_session.query(StudentMasterlist).count() == 2

        # Second import fails mid-transaction.
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = upload_csv(client, CANONICAL + "S99,Crash,Incoming\n")
        batch_id2 = resp.json()["batch_id"]
        run_validation(client, db_session, batch_id2)

        def boom(*args, **kwargs):
            raise RuntimeError("simulated failure")

        # Fail when inserting replacement rows — after the DELETE has run in the
        # same transaction — to prove the rollback restores the old masterlist.
        monkeypatch.setattr(masterlist_service, "StudentMasterlist", boom)
        resp = self._replace(client, batch_id2)
        assert resp.status_code == 200  # job accepted; failure handled in background job
        # Original masterlist preserved; failed batch marked.
        db_session.expire_all()
        rows = db_session.query(StudentMasterlist).all()
        assert len(rows) == 2
        assert {r.student_number for r in rows} == {"S1", "S2"}
        batch2 = db_session.get(MasterlistStagingBatch, batch_id2)
        assert batch2.status == "failed"

    def test_concurrent_import_rejected(self, client, db_session, seed_users):
        batch_id = self._validated_batch(client, db_session, seed_users)
        # Simulate another import in flight.
        other = MasterlistStagingBatch(
            file_name="other.csv", uploaded_by=seed_users["admin"].id, status="importing", total_rows=1
        )
        db_session.add(other)
        db_session.commit()
        resp = self._replace(client, batch_id)
        assert resp.status_code == 409
        assert "in progress" in resp.json()["detail"]
        # No rows were replaced.
        assert db_session.query(StudentMasterlist).count() == 0

    def test_replace_requires_validated_status(self, client, db_session, seed_users):
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = upload_csv(client, CANONICAL + "S1,Juan,Dela Cruz\n")
        batch_id = resp.json()["batch_id"]
        resp = self._replace(client, batch_id)  # still mapping_required/uploaded
        assert resp.status_code == 409


class TestFacultyLookup:
    def _seed_masterlist(self, db_session, seed_users):
        admin = seed_users["admin"]
        login_batch = MasterlistStagingBatch(
            file_name="seed.csv", uploaded_by=admin.id, status="validated", total_rows=3
        )
        db_session.add(login_batch)
        db_session.flush()
        from app.models.masterlist import ImportBatch

        history = ImportBatch(file_name="seed.csv", imported_by=admin.id, total_rows=3, valid_rows=3)
        db_session.add(history)
        db_session.flush()
        entries = [
            ("S100", "Juan", "Dela Cruz", "M", "09171112222", "juan@example.com"),
            ("S101", "Ana", "Santos", "L", "09173334444", "ana@example.com"),
            ("S102", "Jose", "Rizal", None, None, None),
        ]
        from app.models.masterlist import StudentMasterlist as SM

        for number, first, last, mi, tel, email in entries:
            db_session.add(
                SM(
                    student_number=number,
                    first_name=first,
                    last_name=last,
                    middle_initial=mi,
                    telephone=tel,
                    email=email,
                    import_batch_id=history.id,
                )
            )
        db_session.commit()

    def test_lookup_partial_case_insensitive(self, client, db_session, seed_users):
        self._seed_masterlist(db_session, seed_users)
        login(client, "facultya@test.local", "faculty-secret-pw-1")
        resp = client.get("/students/lookup?q=cruz")
        data = resp.json()
        assert data["total"] == 1
        assert data["results"][0]["first_name"] == "Juan"
        resp = client.get("/students/lookup?q=ANA")
        assert resp.json()["total"] == 1
        resp = client.get("/students/lookup?q=S10")
        assert resp.json()["total"] == 3

    def test_lookup_limit_and_offset(self, client, db_session, seed_users):
        self._seed_masterlist(db_session, seed_users)
        login(client, "facultya@test.local", "faculty-secret-pw-1")
        resp = client.get("/students/lookup?q=e")  # matches multiple
        data = resp.json()
        assert len(data["results"]) <= data["limit"]

    def test_selected_student_creates_reservation_not_masterlist(self, client, db_session, seed_users):
        self._seed_masterlist(db_session, seed_users)
        section = make_section(db_session, name="LK", year_level=1, created_by=seed_users["admin"].id)
        entry = db_session.query(StudentMasterlist).filter_by(student_number="S100").one()
        login(client, "facultya@test.local", "faculty-secret-pw-1")
        token = csrf_from(client, "/students/new")
        resp = client.post(
            "/students/new",
            data={
                "first_name": "Juan",
                "last_name": "Dela Cruz",
                "middle_initial": "M",
                "telephone": "09171112222",
                "email": "juan@example.com",
                "section_id": str(section.id),
                "masterlist_student_number": "S100",
                "masterlist_entry_id": str(entry.id),
                "_csrf": token,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303
        from app.models.student import Student

        student = db_session.query(Student).filter_by(masterlist_student_number="S100").one()
        assert student.created_by == seed_users["faculty_a"].id
        assert student.masterlist_entry_id == entry.id
        # Masterlist untouched.
        assert db_session.query(StudentMasterlist).count() == 3

    def test_duplicate_active_reservation_rejected(self, client, db_session, seed_users):
        self._seed_masterlist(db_session, seed_users)
        section = make_section(db_session, name="LK2", year_level=1, created_by=seed_users["admin"].id)
        login(client, "facultya@test.local", "faculty-secret-pw-1")
        token = csrf_from(client, "/students/new")
        data = {
            "first_name": "Juan",
            "last_name": "Dela Cruz",
            "section_id": str(section.id),
            "masterlist_student_number": "S100",
            "_csrf": token,
        }
        assert client.post("/students/new", data=data, follow_redirects=False).status_code == 303
        token = csrf_from(client, "/students/new")
        data["_csrf"] = token
        resp = client.post("/students/new", data=data)
        assert resp.status_code == 400
        assert "already exists for this student number" in resp.text
        # After soft-delete the number frees up.
        from app.models.student import Student

        student = db_session.query(Student).filter_by(masterlist_student_number="S100").one()
        token = csrf_from(client, "/students")
        client.post(f"/students/{student.id}/delete", data={"_csrf": token}, follow_redirects=False)
        token = csrf_from(client, "/students/new")
        data["_csrf"] = token
        assert client.post("/students/new", data=data, follow_redirects=False).status_code == 303

    def test_manual_entry_without_lookup_still_works(self, client, db_session, seed_users):
        self._seed_masterlist(db_session, seed_users)
        section = make_section(db_session, name="MANUAL", year_level=1, created_by=seed_users["admin"].id)
        login(client, "facultya@test.local", "faculty-secret-pw-1")
        token = csrf_from(client, "/students/new")
        resp = client.post(
            "/students/new",
            data={
                "first_name": "Manual",
                "last_name": "Entry",
                "section_id": str(section.id),
                "_csrf": token,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303
        from app.models.student import Student

        student = db_session.query(Student).filter_by(last_name="Entry").one()
        assert student.masterlist_student_number is None

    def test_reservation_survives_masterlist_replacement(self, client, db_session, seed_users):
        self._seed_masterlist(db_session, seed_users)
        section = make_section(db_session, name="KEEP", year_level=1, created_by=seed_users["admin"].id)
        login(client, "facultya@test.local", "faculty-secret-pw-1")
        token = csrf_from(client, "/students/new")
        client.post(
            "/students/new",
            data={
                "first_name": "Juan",
                "last_name": "Dela Cruz",
                "section_id": str(section.id),
                "masterlist_student_number": "S100",
                "_csrf": token,
            },
            follow_redirects=False,
        )
        # Replace masterlist with a completely different batch.
        client.cookies.jar.clear()
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = upload_csv(client, CANONICAL + "S999,New,World\n")
        batch_id = resp.json()["batch_id"]
        run_validation(client, db_session, batch_id)
        client.post(
            f"/admin/masterlist/{batch_id}/replace",
            data={"confirm": "REPLACE", "_csrf": csrf_from(client, "/admin/masterlist")},
        )
        db_session.expire_all()
        from app.models.student import Student

        student = db_session.query(Student).filter_by(masterlist_student_number="S100").one()
        assert student.deleted_at is None
        assert db_session.query(StudentMasterlist).count() == 1
