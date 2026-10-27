from tests.conftest import csrf_from, login, make_section, make_student


class TestCSRF:
    def test_post_without_token_rejected(self, client, seed_users):
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = client.post(
            "/sections/new",
            data={"name": "NO-TOKEN", "year_level": "1"},
            follow_redirects=False,
        )
        assert resp.status_code == 403

    def test_post_with_wrong_token_rejected(self, client, seed_users):
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = client.post(
            "/sections/new",
            data={"name": "BAD-TOKEN", "year_level": "1", "_csrf": "wrong-token-value"},
            follow_redirects=False,
        )
        assert resp.status_code == 403

    def test_post_with_valid_token_accepted(self, client, seed_users):
        login(client, "admin@test.local", "admin-secret-pw-123")
        token = csrf_from(client, "/sections/new")
        resp = client.post(
            "/sections/new",
            data={"name": "OK-TOKEN", "year_level": "1", "_csrf": token},
            follow_redirects=False,
        )
        assert resp.status_code == 303

    def test_login_requires_csrf(self, client, seed_users):
        resp = client.post(
            "/login",
            data={"email": "admin@test.local", "password": "admin-secret-pw-123"},
            follow_redirects=False,
        )
        assert resp.status_code == 403


class TestAdminUserManagement:
    def test_admin_creates_faculty(self, client, seed_users):
        login(client, "admin@test.local", "admin-secret-pw-123")
        token = csrf_from(client, "/admin/users/new")
        resp = client.post(
            "/admin/users/new",
            data={
                "email": "newfaculty@test.local",
                "full_name": "New Faculty",
                "password": "brand-new-faculty-pw",
                "role": "faculty",
                "_csrf": token,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303
        resp = client.get("/admin/users")
        assert "newfaculty@test.local" in resp.text

    def test_faculty_blocked_from_user_admin(self, client, seed_users):
        login(client, "facultya@test.local", "faculty-secret-pw-1")
        resp = client.get("/admin/users", follow_redirects=False)
        assert resp.status_code == 403
        token = csrf_from(client, "/")
        resp = client.post(
            "/admin/users/new",
            data={
                "email": "escalate@test.local",
                "full_name": "Escalate",
                "password": "escalation-attempt-pw",
                "role": "admin",
                "_csrf": token,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 403

    def test_weak_password_rejected(self, client, seed_users):
        login(client, "admin@test.local", "admin-secret-pw-123")
        token = csrf_from(client, "/admin/users/new")
        resp = client.post(
            "/admin/users/new",
            data={
                "email": "weak@test.local",
                "full_name": "Weak",
                "password": "short",
                "role": "faculty",
                "_csrf": token,
            },
        )
        assert resp.status_code == 400
        assert "12 characters" in resp.text

    def test_duplicate_email_rejected(self, client, seed_users):
        login(client, "admin@test.local", "admin-secret-pw-123")
        token = csrf_from(client, "/admin/users/new")
        resp = client.post(
            "/admin/users/new",
            data={
                "email": "admin@test.local",
                "full_name": "Dup",
                "password": "another-strong-pw!",
                "role": "faculty",
                "_csrf": token,
            },
        )
        assert resp.status_code == 400
        assert "already exists" in resp.text

    def test_admin_cannot_deactivate_self(self, client, seed_users):
        admin = seed_users["admin"]
        login(client, "admin@test.local", "admin-secret-pw-123")
        token = csrf_from(client, "/admin/users")
        resp = client.post(f"/admin/users/{admin.id}/toggle", data={"_csrf": token})
        assert resp.status_code == 400


class TestCreateAdminCLI:
    def test_create_admin_via_cli(self, db_session, monkeypatch):
        from tests.conftest import TestingSessionLocal

        monkeypatch.setattr("app.cli.SessionLocal", TestingSessionLocal)
        monkeypatch.setenv("ADMIN_EMAIL", "cliadmin@test.local")
        monkeypatch.setenv("ADMIN_FULL_NAME", "CLI Admin")
        monkeypatch.setenv("ADMIN_PASSWORD", "cli-admin-strong-pw")
        from app.cli import main

        assert main(["create-admin"]) == 0
        from app.models.user import Role, User

        user = db_session.query(User).filter_by(email="cliadmin@test.local").one()
        assert user.role is Role.admin
        # Second run must refuse duplicate.
        assert main(["create-admin"]) == 1

    def test_cli_rejects_weak_password(self, db_session, monkeypatch):
        from tests.conftest import TestingSessionLocal

        monkeypatch.setattr("app.cli.SessionLocal", TestingSessionLocal)
        monkeypatch.setenv("ADMIN_EMAIL", "weakcli@test.local")
        monkeypatch.setenv("ADMIN_FULL_NAME", "Weak CLI")
        monkeypatch.setenv("ADMIN_PASSWORD", "short")
        from app.cli import main

        assert main(["create-admin"]) == 1
