from datetime import datetime, timezone

from tests.conftest import csrf_from, login, make_section, make_student


class TestDashboard:
    def test_dashboard_counts(self, client, db_session, seed_users):
        admin = seed_users["admin"]
        make_section(db_session, name="D1", year_level=1, created_by=admin.id, active=True)
        make_section(db_session, name="D2", year_level=2, created_by=admin.id, active=True)
        make_section(db_session, name="D3", year_level=3, created_by=admin.id, active=False)
        s1 = make_section(db_session, name="D4", year_level=4, created_by=admin.id, active=True)
        make_student(db_session, section_id=s1.id, created_by=admin.id)
        make_student(db_session, first_name="Del", last_name="Eted", section_id=s1.id, created_by=admin.id,
                     deleted_at=datetime.now(timezone.utc))
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Active students" in resp.text
        # 1 active student (today), 3 active sections, 1 encoded today
        assert ">3</div>" in resp.text  # active sections card renders 3
        assert ">1</div>" in resp.text  # active students / encoded today render 1


class TestReports:
    def test_date_filter_respects_manila_timezone(self, client, db_session, seed_users):
        admin = seed_users["admin"]
        section = make_section(db_session, name="R1", year_level=1, created_by=admin.id)
        # 2026-01-15 17:30 UTC == 2026-01-16 01:30 Asia/Manila
        make_student(
            db_session,
            first_name="Manila",
            last_name="Boundary",
            section_id=section.id,
            created_by=admin.id,
            created_at=datetime(2026, 1, 15, 17, 30, tzinfo=timezone.utc),
        )
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = client.get("/reports/result?date_from=2026-01-16&date_to=2026-01-16")
        assert resp.status_code == 200
        assert "Boundary" in resp.text
        resp = client.get("/reports/result?date_from=2026-01-14&date_to=2026-01-15")
        assert resp.status_code == 200
        assert "Boundary" not in resp.text

    def test_year_level_and_section_filters(self, client, db_session, seed_users):
        admin = seed_users["admin"]
        s1 = make_section(db_session, name="RY1", year_level=1, created_by=admin.id)
        s2 = make_section(db_session, name="RY2", year_level=2, created_by=admin.id)
        make_student(db_session, first_name="One", last_name="LevelOne", section_id=s1.id, created_by=admin.id)
        make_student(db_session, first_name="Two", last_name="LevelTwo", section_id=s2.id, created_by=admin.id)
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = client.get("/reports/result?year_level=1")
        assert "LevelOne" in resp.text
        assert "LevelTwo" not in resp.text
        resp = client.get(f"/reports/result?section_id={s2.id}")
        assert "LevelTwo" in resp.text
        assert "LevelOne" not in resp.text

    def test_csv_export(self, client, db_session, seed_users):
        admin = seed_users["admin"]
        section = make_section(db_session, name="RC", year_level=1, created_by=admin.id)
        make_student(db_session, first_name="Csv", last_name="Exported", section_id=section.id, created_by=admin.id)
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = client.get("/reports/export.csv")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert "attachment" in resp.headers["content-disposition"]
        body = resp.content.decode("utf-8-sig")
        assert "Last Name" in body
        assert "Exported" in body

    def test_csv_excludes_soft_deleted(self, client, db_session, seed_users):
        admin = seed_users["admin"]
        section = make_section(db_session, name="RCD", year_level=1, created_by=admin.id)
        make_student(
            db_session,
            first_name="Gone",
            last_name="Deletedson",
            section_id=section.id,
            created_by=admin.id,
            deleted_at=datetime.now(timezone.utc),
        )
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = client.get("/reports/export.csv")
        assert "Deletedson" not in resp.content.decode("utf-8-sig")

    def test_csv_injection_sanitized(self, client, db_session, seed_users):
        admin = seed_users["admin"]
        section = make_section(db_session, name="RCI", year_level=1, created_by=admin.id)
        make_student(
            db_session,
            first_name="=cmd",
            last_name="=SUM(A1:A9)",
            section_id=section.id,
            created_by=admin.id,
        )
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = client.get("/reports/export.csv")
        body = resp.content.decode("utf-8-sig")
        assert "'=SUM" in body
        assert "'=cmd" in body

    def test_invalid_date_rejected(self, client, seed_users):
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = client.get("/reports/result?date_from=not-a-date")
        assert resp.status_code == 400

    def test_invalid_section_rejected(self, client, seed_users):
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = client.get("/reports/result?section_id=99999")
        assert resp.status_code == 400

    def test_printable_view(self, client, db_session, seed_users):
        admin = seed_users["admin"]
        section = make_section(db_session, name="RP", year_level=1, created_by=admin.id)
        make_student(db_session, first_name="Print", last_name="Me", section_id=section.id, created_by=admin.id)
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = client.get("/reports/print")
        assert resp.status_code == 200
        assert "Student Encoding Report" in resp.text
