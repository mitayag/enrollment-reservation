from tests.conftest import csrf_from, login, make_section, make_student


class TestStudentCRUD:
    def test_create_student_derives_year_level_from_section(self, client, db_session, seed_users):
        admin = seed_users["admin"]
        section = make_section(db_session, name="S-YL3", year_level=3, created_by=admin.id)
        login(client, "admin@test.local", "admin-secret-pw-123")
        token = csrf_from(client, "/students/new")
        resp = client.post(
            "/students/new",
            data={
                "first_name": "Maria",
                "last_name": "Santos",
                "middle_initial": "L",
                "telephone": "09171234567",
                "email": "maria@example.com",
                "section_id": str(section.id),
                "_csrf": token,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303
        from app.models.student import Student

        student = db_session.query(Student).filter_by(last_name="Santos").one()
        assert student is not None
        assert student.section_id == section.id
        assert student.section.year_level == 3
        assert student.created_by == admin.id
        resp = client.get("/students?year_level=3")
        assert "Santos" in resp.text
        resp = client.get("/students?year_level=1")
        assert "Santos" not in resp.text

    def test_create_student_requires_section(self, client, seed_users):
        login(client, "admin@test.local", "admin-secret-pw-123")
        token = csrf_from(client, "/students/new")
        resp = client.post(
            "/students/new",
            data={
                "first_name": "No",
                "last_name": "Section",
                "section_id": "99999",
                "_csrf": token,
            },
        )
        assert resp.status_code == 400
        assert "does not exist" in resp.text

    def test_create_student_with_inactive_section_rejected(self, client, db_session, seed_users):
        section = make_section(db_session, name="INACT", year_level=1, created_by=seed_users["admin"].id, active=False)
        login(client, "admin@test.local", "admin-secret-pw-123")
        token = csrf_from(client, "/students/new")
        resp = client.post(
            "/students/new",
            data={"first_name": "X", "last_name": "Y", "section_id": str(section.id), "_csrf": token},
        )
        assert resp.status_code == 400
        assert "not active" in resp.text

    def test_faculty_creates_student_records_creator(self, client, db_session, seed_users):
        faculty = seed_users["faculty_a"]
        section = make_section(db_session, name="FAC-SEC", year_level=1, created_by=seed_users["admin"].id)
        login(client, "facultya@test.local", "faculty-secret-pw-1")
        token = csrf_from(client, "/students/new")
        resp = client.post(
            "/students/new",
            data={"first_name": "Ana", "last_name": "Reyes", "section_id": str(section.id), "_csrf": token},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        from app.models.student import Student

        student = db_session.query(Student).filter_by(last_name="Reyes").one()
        assert student.created_by == faculty.id

    def test_faculty_can_edit_own_student(self, client, db_session, seed_users):
        faculty = seed_users["faculty_a"]
        section = make_section(db_session, name="OWN", year_level=1, created_by=seed_users["admin"].id)
        student = make_student(db_session, section_id=section.id, created_by=faculty.id)
        login(client, "facultya@test.local", "faculty-secret-pw-1")
        token = csrf_from(client, f"/students/{student.id}/edit")
        resp = client.post(
            f"/students/{student.id}/edit",
            data={
                "first_name": "Updated",
                "last_name": "Name",
                "section_id": str(section.id),
                "_csrf": token,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303
        db_session.refresh(student)
        assert student.first_name == "Updated"

    def test_faculty_cannot_edit_others_student(self, client, db_session, seed_users):
        section = make_section(db_session, name="OTHERS", year_level=1, created_by=seed_users["admin"].id)
        student = make_student(db_session, section_id=section.id, created_by=seed_users["faculty_b"].id)
        login(client, "facultya@test.local", "faculty-secret-pw-1")
        # Even the edit form page is forbidden for non-owners.
        assert client.get(f"/students/{student.id}/edit", follow_redirects=False).status_code == 403
        token = csrf_from(client, "/students")
        resp = client.post(
            f"/students/{student.id}/edit",
            data={
                "first_name": "Hack",
                "last_name": "Attempt",
                "section_id": str(section.id),
                "_csrf": token,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 403
        db_session.refresh(student)
        assert student.first_name != "Hack"

    def test_admin_can_edit_any_student(self, client, db_session, seed_users):
        section = make_section(db_session, name="ANY", year_level=1, created_by=seed_users["admin"].id)
        student = make_student(db_session, section_id=section.id, created_by=seed_users["faculty_b"].id)
        login(client, "admin@test.local", "admin-secret-pw-123")
        token = csrf_from(client, f"/students/{student.id}/edit")
        resp = client.post(
            f"/students/{student.id}/edit",
            data={
                "first_name": "AdminEdit",
                "last_name": "Done",
                "section_id": str(section.id),
                "_csrf": token,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303
        db_session.refresh(student)
        assert student.first_name == "AdminEdit"

    def test_soft_delete_hides_student(self, client, db_session, seed_users):
        section = make_section(db_session, name="DEL", year_level=1, created_by=seed_users["admin"].id)
        student = make_student(db_session, section_id=section.id, created_by=seed_users["admin"].id)
        login(client, "admin@test.local", "admin-secret-pw-123")
        token = csrf_from(client, "/students")
        resp = client.post(
            f"/students/{student.id}/delete",
            data={"_csrf": token},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        db_session.refresh(student)
        assert student.deleted_at is not None
        resp = client.get("/students")
        assert "Dela Cruz" not in resp.text

    def test_admin_can_view_deleted_students(self, client, db_session, seed_users):
        from datetime import datetime, timezone

        section = make_section(db_session, name="DELSHOWN", year_level=1, created_by=seed_users["admin"].id)
        student = make_student(
            db_session,
            section_id=section.id,
            created_by=seed_users["admin"].id,
            deleted_at=datetime.now(timezone.utc),
        )
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = client.get("/students?show_deleted=true")
        assert "Dela Cruz" in resp.text

    def test_faculty_cannot_soft_delete_others_student(self, client, db_session, seed_users):
        section = make_section(db_session, name="PROT", year_level=1, created_by=seed_users["admin"].id)
        student = make_student(db_session, section_id=section.id, created_by=seed_users["faculty_b"].id)
        login(client, "facultya@test.local", "faculty-secret-pw-1")
        token = csrf_from(client, "/students")
        resp = client.post(f"/students/{student.id}/delete", data={"_csrf": token})
        assert resp.status_code == 403
        db_session.refresh(student)
        assert student.deleted_at is None

    def test_search_by_name(self, client, db_session, seed_users):
        section = make_section(db_session, name="SRCH", year_level=1, created_by=seed_users["admin"].id)
        make_student(db_session, first_name="Unique", last_name="Zzyzx", section_id=section.id, created_by=seed_users["admin"].id)
        make_student(db_session, first_name="Other", last_name="Person", section_id=section.id, created_by=seed_users["admin"].id)
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = client.get("/students?q=Zzyzx")
        assert "Zzyzx" in resp.text
        assert "Person" not in resp.text

    def test_faculty_cannot_keep_inactive_section_on_change(self, client, db_session, seed_users):
        active = make_section(db_session, name="ACT", year_level=1, created_by=seed_users["admin"].id)
        inactive = make_section(db_session, name="INACT2", year_level=2, created_by=seed_users["admin"].id, active=False)
        student = make_student(db_session, section_id=active.id, created_by=seed_users["admin"].id)
        login(client, "admin@test.local", "admin-secret-pw-123")
        token = csrf_from(client, f"/students/{student.id}/edit")
        resp = client.post(
            f"/students/{student.id}/edit",
            data={
                "first_name": "Juan",
                "last_name": "Dela Cruz",
                "section_id": str(inactive.id),
                "_csrf": token,
            },
        )
        assert resp.status_code == 400
        assert "not active" in resp.text
