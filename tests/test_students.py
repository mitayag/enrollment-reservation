from tests.conftest import csrf_from, login, make_section, make_student


class TestStudentCRUD:
    def test_create_student_derives_program_and_year_from_section(
        self, client, db_session, seed_users, programs
    ):
        admin = seed_users["admin"]
        section = make_section(
            db_session,
            name="S-YL3",
            year_level=3,
            created_by=admin.id,
            program_id=programs["BSIT-WD"].id,
        )
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
                "program_id": str(programs["BSIT-WD"].id),
                "year_level": "3",
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
        assert student.section.program_id == programs["BSIT-WD"].id
        assert student.created_by == admin.id
        resp = client.get("/students?year_level=3")
        assert "Santos" in resp.text
        resp = client.get("/students?year_level=1")
        assert "Santos" not in resp.text
        resp = client.get(f"/students?program_id={programs['BSIT-WD'].id}")
        assert "Santos" in resp.text

    def test_create_student_requires_section(self, client, seed_users, programs):
        login(client, "admin@test.local", "admin-secret-pw-123")
        token = csrf_from(client, "/students/new")
        resp = client.post(
            "/students/new",
            data={
                "first_name": "No",
                "last_name": "Section",
                "section_id": "99999",
                "program_id": str(programs["BSIT-WD"].id),
                "year_level": "1",
                "_csrf": token,
            },
        )
        assert resp.status_code == 400
        assert "does not exist" in resp.text

    def test_mismatched_program_and_section_rejected(self, client, db_session, seed_users, programs):
        admin = seed_users["admin"]
        section = make_section(
            db_session,
            name="MM-SEC",
            year_level=1,
            created_by=admin.id,
            program_id=programs["BSCS"].id,
        )
        login(client, "admin@test.local", "admin-secret-pw-123")
        token = csrf_from(client, "/students/new")
        resp = client.post(
            "/students/new",
            data={
                "first_name": "Bad",
                "last_name": "Match",
                "section_id": str(section.id),
                "program_id": str(programs["BSIT-WD"].id),  # wrong program
                "year_level": "1",
                "_csrf": token,
            },
        )
        assert resp.status_code == 400
        assert "does not belong to the selected program" in resp.text

    def test_mismatched_year_and_section_rejected(self, client, db_session, seed_users, programs):
        admin = seed_users["admin"]
        section = make_section(
            db_session,
            name="MM-SEC2",
            year_level=2,
            created_by=admin.id,
            program_id=programs["BSCS"].id,
        )
        login(client, "admin@test.local", "admin-secret-pw-123")
        token = csrf_from(client, "/students/new")
        resp = client.post(
            "/students/new",
            data={
                "first_name": "Bad",
                "last_name": "Year",
                "section_id": str(section.id),
                "program_id": str(programs["BSCS"].id),
                "year_level": "1",  # wrong year
                "_csrf": token,
            },
        )
        assert resp.status_code == 400
        assert "does not belong to the selected year level" in resp.text

    def test_cannot_assign_legacy_section_to_new_student(self, client, db_session, seed_users, programs):
        admin = seed_users["admin"]
        legacy = make_section(
            db_session, name="LEGACY-STU", year_level=1, created_by=admin.id, program_id=None
        )
        login(client, "admin@test.local", "admin-secret-pw-123")
        token = csrf_from(client, "/students/new")
        resp = client.post(
            "/students/new",
            data={
                "first_name": "Legacy",
                "last_name": "Student",
                "section_id": str(legacy.id),
                "program_id": str(programs["BSCS"].id),
                "year_level": "1",
                "_csrf": token,
            },
        )
        assert resp.status_code == 400
        assert "does not belong to the selected program" in resp.text

    def test_create_student_with_inactive_section_rejected(self, client, db_session, seed_users, programs):
        section = make_section(
            db_session,
            name="INACT",
            year_level=1,
            created_by=seed_users["admin"].id,
            active=False,
            program_id=programs["BSCS"].id,
        )
        login(client, "admin@test.local", "admin-secret-pw-123")
        token = csrf_from(client, "/students/new")
        resp = client.post(
            "/students/new",
            data={
                "first_name": "X",
                "last_name": "Y",
                "section_id": str(section.id),
                "program_id": str(programs["BSCS"].id),
                "year_level": "1",
                "_csrf": token,
            },
        )
        assert resp.status_code == 400
        assert "not active" in resp.text

    def test_faculty_creates_student_records_creator(self, client, db_session, seed_users, programs):
        faculty = seed_users["faculty_a"]
        section = make_section(
            db_session,
            name="FAC-SEC",
            year_level=1,
            created_by=seed_users["admin"].id,
            program_id=programs["BSCS"].id,
        )
        login(client, "facultya@test.local", "faculty-secret-pw-1")
        token = csrf_from(client, "/students/new")
        resp = client.post(
            "/students/new",
            data={
                "first_name": "Ana",
                "last_name": "Reyes",
                "section_id": str(section.id),
                "program_id": str(programs["BSCS"].id),
                "year_level": "1",
                "_csrf": token,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303
        from app.models.student import Student

        student = db_session.query(Student).filter_by(last_name="Reyes").one()
        assert student.created_by == faculty.id

    def test_faculty_can_edit_own_student(self, client, db_session, seed_users, programs):
        faculty = seed_users["faculty_a"]
        section = make_section(
            db_session,
            name="OWN",
            year_level=1,
            created_by=seed_users["admin"].id,
            program_id=programs["BSCS"].id,
        )
        student = make_student(db_session, section_id=section.id, created_by=faculty.id)
        login(client, "facultya@test.local", "faculty-secret-pw-1")
        token = csrf_from(client, f"/students/{student.id}/edit")
        resp = client.post(
            f"/students/{student.id}/edit",
            data={
                "first_name": "Updated",
                "last_name": "Name",
                "section_id": str(section.id),
                "program_id": str(programs["BSCS"].id),
                "year_level": "1",
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

    def test_admin_can_edit_any_student(self, client, db_session, seed_users, programs):
        section = make_section(
            db_session,
            name="ANY",
            year_level=1,
            created_by=seed_users["admin"].id,
            program_id=programs["BSCS"].id,
        )
        student = make_student(db_session, section_id=section.id, created_by=seed_users["faculty_b"].id)
        login(client, "admin@test.local", "admin-secret-pw-123")
        token = csrf_from(client, f"/students/{student.id}/edit")
        resp = client.post(
            f"/students/{student.id}/edit",
            data={
                "first_name": "AdminEdit",
                "last_name": "Done",
                "section_id": str(section.id),
                "program_id": str(programs["BSCS"].id),
                "year_level": "1",
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

    def test_faculty_cannot_keep_inactive_section_on_change(self, client, db_session, seed_users, programs):
        active = make_section(
            db_session,
            name="ACT",
            year_level=1,
            created_by=seed_users["admin"].id,
            program_id=programs["BSCS"].id,
        )
        inactive = make_section(
            db_session,
            name="INACT2",
            year_level=2,
            created_by=seed_users["admin"].id,
            active=False,
            program_id=programs["BSCS"].id,
        )
        student = make_student(db_session, section_id=active.id, created_by=seed_users["admin"].id)
        login(client, "admin@test.local", "admin-secret-pw-123")
        token = csrf_from(client, f"/students/{student.id}/edit")
        resp = client.post(
            f"/students/{student.id}/edit",
            data={
                "first_name": "Juan",
                "last_name": "Dela Cruz",
                "section_id": str(inactive.id),
                "program_id": str(programs["BSCS"].id),
                "year_level": "2",
                "_csrf": token,
            },
        )
        assert resp.status_code == 400
        assert "not active" in resp.text


class TestStudentListFilters:
    """Empty/omitted filter params must mean "All" — never a 422."""

    def test_empty_filter_params_are_treated_as_all(self, client, db_session, seed_users):
        section = make_section(db_session, name="FL-E", year_level=1, created_by=seed_users["admin"].id)
        make_student(db_session, first_name="Empty", last_name="Params", section_id=section.id, created_by=seed_users["admin"].id)
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = client.get("/students?q=&section_id=&year_level=")
        assert resp.status_code == 200
        assert "Params" in resp.text

    def test_missing_filter_params_are_treated_as_all(self, client, db_session, seed_users):
        section = make_section(db_session, name="FL-M", year_level=1, created_by=seed_users["admin"].id)
        make_student(db_session, first_name="Missing", last_name="Params", section_id=section.id, created_by=seed_users["admin"].id)
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = client.get("/students")
        assert resp.status_code == 200
        assert "Params" in resp.text

    def test_whitespace_filter_params_are_treated_as_all(self, client, db_session, seed_users):
        section = make_section(db_session, name="FL-W", year_level=1, created_by=seed_users["admin"].id)
        make_student(db_session, first_name="White", last_name="Space", section_id=section.id, created_by=seed_users["admin"].id)
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = client.get("/students?q=%20&section_id=%20%20&year_level=%20")
        assert resp.status_code == 200
        assert "Space" in resp.text

    def test_name_only_filter(self, client, db_session, seed_users):
        section = make_section(db_session, name="FL-N", year_level=1, created_by=seed_users["admin"].id)
        make_student(db_session, first_name="Findme", last_name="Only", section_id=section.id, created_by=seed_users["admin"].id)
        make_student(db_session, first_name="Other", last_name="Person", section_id=section.id, created_by=seed_users["admin"].id)
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = client.get("/students?q=Findme")
        assert resp.status_code == 200
        assert "Findme" in resp.text
        assert "Person" not in resp.text

    def test_year_level_only_filter(self, client, db_session, seed_users):
        admin = seed_users["admin"]
        s1 = make_section(db_session, name="FL-Y1", year_level=1, created_by=admin.id)
        s2 = make_section(db_session, name="FL-Y2", year_level=2, created_by=admin.id)
        make_student(db_session, first_name="Year", last_name="Two", section_id=s2.id, created_by=admin.id)
        make_student(db_session, first_name="Year", last_name="One", section_id=s1.id, created_by=admin.id)
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = client.get("/students?year_level=2")
        assert resp.status_code == 200
        assert "Two" in resp.text
        assert "One" not in resp.text

    def test_section_only_filter(self, client, db_session, seed_users):
        admin = seed_users["admin"]
        s1 = make_section(db_session, name="FL-S1", year_level=1, created_by=admin.id)
        s2 = make_section(db_session, name="FL-S2", year_level=2, created_by=admin.id)
        make_student(db_session, first_name="Sec", last_name="One", section_id=s1.id, created_by=admin.id)
        make_student(db_session, first_name="Sec", last_name="Two", section_id=s2.id, created_by=admin.id)
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = client.get(f"/students?section_id={s1.id}")
        assert resp.status_code == 200
        assert "One, Sec" in resp.text
        assert "Two, Sec" not in resp.text

    def test_name_year_level_and_section_combined(self, client, db_session, seed_users):
        admin = seed_users["admin"]
        s1 = make_section(db_session, name="FL-C1", year_level=1, created_by=admin.id)
        s2 = make_section(db_session, name="FL-C2", year_level=2, created_by=admin.id)
        s3 = make_section(db_session, name="FL-C3", year_level=3, created_by=admin.id)
        make_student(db_session, first_name="Combo", last_name="Match", section_id=s2.id, created_by=admin.id)
        make_student(db_session, first_name="Combo", last_name="Wrongsec", section_id=s1.id, created_by=admin.id)
        make_student(db_session, first_name="Combo", last_name="Wroong", section_id=s3.id, created_by=admin.id)
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = client.get(f"/students?q=Combo&year_level=2&section_id={s2.id}")
        assert resp.status_code == 200
        assert "Match, Combo" in resp.text
        assert "Wrongsec" not in resp.text
        assert "Wroong" not in resp.text

    def test_all_year_levels_and_all_sections(self, client, db_session, seed_users):
        admin = seed_users["admin"]
        s1 = make_section(db_session, name="FL-A1", year_level=1, created_by=admin.id)
        s2 = make_section(db_session, name="FL-A2", year_level=3, created_by=admin.id)
        make_student(db_session, first_name="Any", last_name="First", section_id=s1.id, created_by=admin.id)
        make_student(db_session, first_name="Any", last_name="Second", section_id=s2.id, created_by=admin.id)
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = client.get("/students?q=Any&section_id=&year_level=")
        assert resp.status_code == 200
        assert "First, Any" in resp.text
        assert "Second, Any" in resp.text

    def test_invalid_section_id_returns_controlled_400(self, client, seed_users):
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = client.get("/students?section_id=abc")
        assert resp.status_code == 400
        assert "must be a positive integer" in resp.text

    def test_invalid_year_level_returns_controlled_400(self, client, seed_users):
        login(client, "admin@test.local", "admin-secret-pw-123")
        # %2B decodes to a literal "+"; a bare "+" would decode to a space.
        for bad in ("-1", "0", "1.5", "%2B2"):
            resp = client.get(f"/students?year_level={bad}")
            assert resp.status_code == 400, bad
            assert "must be a positive integer" in resp.text

    def test_form_omits_blank_filters_via_script(self, client, seed_users):
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = client.get("/students")
        assert resp.status_code == 200
        assert "omitBlankFilters" in resp.text

    def test_pagination_preserves_active_filters(self, client, db_session, seed_users):
        from app.services import student_service

        admin = seed_users["admin"]
        section = make_section(db_session, name="FL-PG", year_level=2, created_by=admin.id)
        other = make_section(db_session, name="FL-PG-OTHER", year_level=1, created_by=admin.id)
        for i in range(student_service.PAGE_SIZE + 1):
            make_student(
                db_session,
                first_name="Paginated",
                last_name=f"Zed{i:02d}",
                section_id=section.id,
                created_by=admin.id,
            )
        make_student(db_session, first_name="Paginated", last_name="Elsewhere", section_id=other.id, created_by=admin.id)
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = client.get(
            f"/students?page=2&q=Paginated&year_level=2&section_id={section.id}&show_deleted=true"
        )
        assert resp.status_code == 200
        assert "Zed25" in resp.text  # the 26th row lands on page 2
        assert "Elsewhere" not in resp.text
        page_two_href = (
            f"/students?page=2&q=Paginated&section_id={section.id}&year_level=2&show_deleted=true"
        )
        assert page_two_href in resp.text
