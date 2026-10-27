from tests.conftest import csrf_from, login


class TestSectionCRUD:
    def test_admin_creates_section(self, client, db_session, seed_users):
        login(client, "admin@test.local", "admin-secret-pw-123")
        token = csrf_from(client, "/sections/new")
        resp = client.post(
            "/sections/new",
            data={"name": "SECTION-1A", "year_level": "1", "_csrf": token},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        resp = client.get("/sections")
        assert "SECTION-1A" in resp.text

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

    def test_duplicate_active_name_rejected(self, client, db_session, seed_users):
        login(client, "admin@test.local", "admin-secret-pw-123")
        token = csrf_from(client, "/sections/new")
        for _ in range(2):
            resp = client.post(
                "/sections/new",
                data={"name": "DUP-NAME", "year_level": "2", "_csrf": token},
            )
        assert resp.status_code == 400
        assert "already exists" in resp.text

    def test_duplicate_name_allowed_after_deactivation(self, client, db_session, seed_users):
        from tests.conftest import make_section

        admin = seed_users["admin"]
        old = make_section(db_session, name="OLD-SECTION", year_level=3, created_by=admin.id, active=False)
        assert old.is_active is False
        login(client, "admin@test.local", "admin-secret-pw-123")
        token = csrf_from(client, "/sections/new")
        resp = client.post(
            "/sections/new",
            data={"name": "OLD-SECTION", "year_level": "3", "_csrf": token},
            follow_redirects=False,
        )
        assert resp.status_code == 303

    def test_edit_section(self, client, db_session, seed_users):
        from tests.conftest import make_section

        section = make_section(db_session, name="EDIT-ME", year_level=1, created_by=seed_users["admin"].id)
        login(client, "admin@test.local", "admin-secret-pw-123")
        token = csrf_from(client, f"/sections/{section.id}/edit")
        resp = client.post(
            f"/sections/{section.id}/edit",
            data={"name": "EDITED", "year_level": "4", "_csrf": token},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        db_session.refresh(section)
        assert section.name == "EDITED"
        assert section.year_level == 4

    def test_year_level_out_of_range_rejected(self, client, seed_users):
        login(client, "admin@test.local", "admin-secret-pw-123")
        token = csrf_from(client, "/sections/new")
        resp = client.post(
            "/sections/new",
            data={"name": "BAD-YL", "year_level": "5", "_csrf": token},
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

    def test_reactivation_with_duplicate_active_name_rejected(self, client, db_session, seed_users):
        from tests.conftest import make_section

        admin = seed_users["admin"]
        make_section(db_session, name="CLASH", year_level=1, created_by=admin.id, active=True)
        inactive = make_section(db_session, name="CLASH", year_level=2, created_by=admin.id, active=False)
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
