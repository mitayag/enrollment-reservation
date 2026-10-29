from tests.conftest import csrf_from, login


class TestSectionCRUD:
    def test_admin_creates_section(self, client, db_session, seed_users, programs):
        login(client, "admin@test.local", "admin-secret-pw-123")
        token = csrf_from(client, "/sections/new")
        resp = client.post(
            "/sections/new",
            data={
                "name": "SECTION-1A",
                "year_level": "1",
                "program_id": str(programs["BSIT-WD"].id),
                "_csrf": token,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303
        resp = client.get("/sections")
        assert "SECTION-1A" in resp.text
        assert "BSIT-WD" in resp.text

    def test_faculty_cannot_create_section(self, client, seed_users):
        login(client, "facultya@test.local", "faculty-secret-pw-1")
        token = csrf_from(client, "/sections")
        resp = client.post(
            "/sections/new",
            data={"name": "FORBIDDEN", "year_level": "1", "_csrf": token},
            follow_redirects=False,
        )
        assert resp.status_code == 403

    def test_faculty_cannot_access_new_section_form(self, client, seed_users):
        login(client, "facultya@test.local", "faculty-secret-pw-1")
        resp = client.get("/sections/new", follow_redirects=False)
        assert resp.status_code == 403

    def test_program_required_for_new_section(self, client, seed_users, programs):
        login(client, "admin@test.local", "admin-secret-pw-123")
        token = csrf_from(client, "/sections/new")
        resp = client.post(
            "/sections/new",
            data={"name": "NO-PROGRAM", "year_level": "1", "program_id": "", "_csrf": token},
        )
        assert resp.status_code == 400
        assert "Program is required." in resp.text

    def test_duplicate_active_name_rejected_within_program(
        self, client, db_session, seed_users, programs
    ):
        login(client, "admin@test.local", "admin-secret-pw-123")
        token = csrf_from(client, "/sections/new")
        for _ in range(2):
            resp = client.post(
                "/sections/new",
                data={
                    "name": "DUP-NAME",
                    "year_level": "2",
                    "program_id": str(programs["BSIT-WD"].id),
                    "_csrf": token,
                },
            )
        assert resp.status_code == 400
        assert "already exists" in resp.text

    def test_same_name_allowed_in_different_programs(
        self, client, db_session, seed_users, programs
    ):
        login(client, "admin@test.local", "admin-secret-pw-123")
        token = csrf_from(client, "/sections/new")
        for code in ("BSIT-WD", "BSCS"):
            resp = client.post(
                "/sections/new",
                data={
                    "name": "SHARED-NAME",
                    "year_level": "1",
                    "program_id": str(programs[code].id),
                    "_csrf": token,
                },
                follow_redirects=False,
            )
            assert resp.status_code == 303, code

    def test_duplicate_name_allowed_after_deactivation(
        self, client, db_session, seed_users, programs
    ):
        from tests.conftest import make_section

        admin = seed_users["admin"]
        old = make_section(
            db_session,
            name="OLD-SECTION",
            year_level=3,
            created_by=admin.id,
            active=False,
            program_id=programs["BSIT-WD"].id,
        )
        assert old.is_active is False
        login(client, "admin@test.local", "admin-secret-pw-123")
        token = csrf_from(client, "/sections/new")
        resp = client.post(
            "/sections/new",
            data={
                "name": "OLD-SECTION",
                "year_level": "3",
                "program_id": str(programs["BSIT-WD"].id),
                "_csrf": token,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303

    def test_edit_section(self, client, db_session, seed_users, programs):
        from tests.conftest import make_section

        section = make_section(
            db_session,
            name="EDIT-ME",
            year_level=1,
            created_by=seed_users["admin"].id,
            program_id=programs["BSCS"].id,
        )
        login(client, "admin@test.local", "admin-secret-pw-123")
        token = csrf_from(client, f"/sections/{section.id}/edit")
        resp = client.post(
            f"/sections/{section.id}/edit",
            data={
                "name": "EDITED",
                "year_level": "4",
                "program_id": str(programs["BSCS"].id),
                "_csrf": token,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303
        db_session.refresh(section)
        assert section.name == "EDITED"
        assert section.year_level == 4

    def test_year_level_out_of_range_rejected(self, client, seed_users, programs):
        login(client, "admin@test.local", "admin-secret-pw-123")
        token = csrf_from(client, "/sections/new")
        resp = client.post(
            "/sections/new",
            data={
                "name": "BAD-YL",
                "year_level": "5",
                "program_id": str(programs["BSIT-WD"].id),
                "_csrf": token,
            },
        )
        assert resp.status_code == 400
        assert "Year level" in resp.text

    def test_deactivate_preserves_student_links(self, client, db_session, seed_users):
        from tests.conftest import make_section, make_student

        admin = seed_users["admin"]
        section = make_section(db_session, name="WILL-DEACTIVATE", year_level=2, created_by=admin.id)
        student = make_student(db_session, section_id=section.id, created_by=admin.id)
        login(client, "admin@test.local", "admin-secret-pw-123")
        token = csrf_from(client, "/sections")
        resp = client.post(
            f"/sections/{section.id}/toggle",
            data={"_csrf": token},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        db_session.refresh(section)
        assert section.is_active is False
        db_session.refresh(student)
        assert student.section_id == section.id

    def test_reactivation_with_duplicate_active_name_rejected(
        self, client, db_session, seed_users, programs
    ):
        from tests.conftest import make_section

        admin = seed_users["admin"]
        make_section(
            db_session,
            name="CLASH",
            year_level=1,
            created_by=admin.id,
            active=True,
            program_id=programs["BSIT-NA"].id,
        )
        inactive = make_section(
            db_session,
            name="CLASH",
            year_level=2,
            created_by=admin.id,
            active=False,
            program_id=programs["BSIT-NA"].id,
        )
        login(client, "admin@test.local", "admin-secret-pw-123")
        token = csrf_from(client, "/sections")
        resp = client.post(
            f"/sections/{inactive.id}/toggle",
            data={"_csrf": token},
        )
        assert resp.status_code == 400

    def test_faculty_cannot_toggle_section(self, client, db_session, seed_users):
        from tests.conftest import make_section

        section = make_section(db_session, name="FAC-TOGGLE", year_level=1, created_by=seed_users["admin"].id)
        login(client, "facultya@test.local", "faculty-secret-pw-1")
        token = csrf_from(client, "/sections")
        resp = client.post(f"/sections/{section.id}/toggle", data={"_csrf": token})
        assert resp.status_code == 403


class TestSectionProgramAssignment:
    """Administrator workflow for migrating pre-existing sections."""

    def test_legacy_section_shows_unassigned_and_can_be_assigned(
        self, client, db_session, seed_users, programs
    ):
        from tests.conftest import make_section

        admin = seed_users["admin"]
        legacy = make_section(
            db_session, name="LEGACY-1A", year_level=1, created_by=admin.id, program_id=None
        )
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = client.get("/sections")
        assert "Unassigned" in resp.text
        token = csrf_from(client, f"/sections/{legacy.id}/edit")
        resp = client.post(
            f"/sections/{legacy.id}/edit",
            data={
                "name": legacy.name,
                "year_level": "1",
                "program_id": str(programs["BSCYB"].id),
                "_csrf": token,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303
        db_session.refresh(legacy)
        assert legacy.program_id == programs["BSCYB"].id
        resp = client.get("/sections")
        assert "Unassigned" not in resp.text
        assert "BSCYB" in resp.text

    def test_edit_form_requires_program_for_legacy_section(
        self, client, db_session, seed_users, programs
    ):
        from tests.conftest import make_section

        admin = seed_users["admin"]
        legacy = make_section(
            db_session, name="LEGACY-2A", year_level=2, created_by=admin.id, program_id=None
        )
        login(client, "admin@test.local", "admin-secret-pw-123")
        token = csrf_from(client, f"/sections/{legacy.id}/edit")
        resp = client.post(
            f"/sections/{legacy.id}/edit",
            data={"name": legacy.name, "year_level": "2", "program_id": "", "_csrf": token},
        )
        assert resp.status_code == 400
        assert "Program is required." in resp.text
        db_session.refresh(legacy)
        assert legacy.program_id is None
