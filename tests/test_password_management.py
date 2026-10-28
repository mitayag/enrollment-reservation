import re

from tests.conftest import csrf_from, login


def _login_cookie(client) -> str:
    for cookie in client.cookies.jar:
        if cookie.name == "session":
            return cookie.value
    return ""


class TestChangeOwnPassword:
    def test_change_password_success(self, client, seed_users):
        login(client, "facultya@test.local", "faculty-secret-pw-1")
        token = csrf_from(client, "/account/password")
        old_cookie = _login_cookie(client)
        resp = client.post(
            "/account/password",
            data={
                "current_password": "faculty-secret-pw-1",
                "new_password": "brand-new-faculty-pw!",
                "confirm_password": "brand-new-faculty-pw!",
                "_csrf": token,
            },
        )
        assert resp.status_code == 200
        assert "Password changed successfully" in resp.text
        # Session regenerated: cookie value must differ from the old session.
        assert _login_cookie(client) != old_cookie
        # Old password no longer authenticates.
        client.cookies.jar.clear()
        token = csrf_from(client)
        resp = client.post(
            "/login",
            data={"email": "facultya@test.local", "password": "faculty-secret-pw-1", "_csrf": token},
        )
        assert resp.status_code == 401
        token = csrf_from(client)
        resp = client.post(
            "/login",
            data={
                "email": "facultya@test.local",
                "password": "brand-new-faculty-pw!",
                "_csrf": token,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303

    def test_wrong_current_password_rejected(self, client, seed_users):
        login(client, "facultya@test.local", "faculty-secret-pw-1")
        token = csrf_from(client, "/account/password")
        resp = client.post(
            "/account/password",
            data={
                "current_password": "not-the-password",
                "new_password": "brand-new-faculty-pw!",
                "confirm_password": "brand-new-faculty-pw!",
                "_csrf": token,
            },
        )
        assert resp.status_code == 400
        assert "Current password is incorrect" in resp.text

    def test_short_password_rejected(self, client, seed_users):
        login(client, "facultya@test.local", "faculty-secret-pw-1")
        token = csrf_from(client, "/account/password")
        resp = client.post(
            "/account/password",
            data={
                "current_password": "faculty-secret-pw-1",
                "new_password": "short",
                "confirm_password": "short",
                "_csrf": token,
            },
        )
        assert resp.status_code == 400
        assert "12 characters" in resp.text

    def test_mismatched_confirmation_rejected(self, client, seed_users):
        login(client, "facultya@test.local", "faculty-secret-pw-1")
        token = csrf_from(client, "/account/password")
        resp = client.post(
            "/account/password",
            data={
                "current_password": "faculty-secret-pw-1",
                "new_password": "brand-new-faculty-pw!",
                "confirm_password": "different-new-pw-1!",
                "_csrf": token,
            },
        )
        assert resp.status_code == 400
        assert "do not match" in resp.text

    def test_stale_csrf_rejected_after_password_change(self, client, seed_users):
        login(client, "facultya@test.local", "faculty-secret-pw-1")
        token = csrf_from(client, "/account/password")
        client.post(
            "/account/password",
            data={
                "current_password": "faculty-secret-pw-1",
                "new_password": "brand-new-faculty-pw!",
                "confirm_password": "brand-new-faculty-pw!",
                "_csrf": token,
            },
        )
        # The pre-change CSRF token must no longer be accepted.
        resp = client.post(
            "/account/password",
            data={
                "current_password": "brand-new-faculty-pw!",
                "new_password": "another-brand-new-pw!",
                "confirm_password": "another-brand-new-pw!",
                "_csrf": token,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 403


class TestAdminPasswordReset:
    def test_admin_reset_requires_policy_and_sets_flag(self, client, db_session, seed_users):
        login(client, "admin@test.local", "admin-secret-pw-123")
        faculty = seed_users["faculty_a"]
        token = csrf_from(client, f"/admin/users/{faculty.id}/reset-password")
        resp = client.post(
            f"/admin/users/{faculty.id}/reset-password",
            data={"new_password": "weak", "_csrf": token},
        )
        assert resp.status_code == 400
        token = csrf_from(client, f"/admin/users/{faculty.id}/reset-password")
        resp = client.post(
            f"/admin/users/{faculty.id}/reset-password",
            data={"new_password": "temporary-reset-pw-1", "_csrf": token},
        )
        assert resp.status_code == 200
        assert "must change it at next login" in resp.text
        db_session.refresh(faculty)
        assert faculty.must_change_password is True

    def test_faculty_cannot_reset_passwords(self, client, seed_users):
        target = seed_users["faculty_b"]
        login(client, "facultya@test.local", "faculty-secret-pw-1")
        resp = client.get(f"/admin/users/{target.id}/reset-password", follow_redirects=False)
        assert resp.status_code == 403
        token = csrf_from(client, "/")
        resp = client.post(
            f"/admin/users/{target.id}/reset-password",
            data={"new_password": "escalation-attempt-1", "_csrf": token},
        )
        assert resp.status_code == 403

    def test_admin_cannot_reset_own_password_via_admin_flow(self, client, seed_users):
        admin = seed_users["admin"]
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = client.get(f"/admin/users/{admin.id}/reset-password", follow_redirects=False)
        assert resp.status_code == 400

    def test_reset_does_not_log_password(self, client, seed_users, caplog):
        import logging

        target = seed_users["faculty_b"]
        login(client, "admin@test.local", "admin-secret-pw-123")
        token = csrf_from(client, f"/admin/users/{target.id}/reset-password")
        with caplog.at_level(logging.INFO):
            client.post(
                f"/admin/users/{target.id}/reset-password",
                data={"new_password": "temporary-reset-pw-1", "_csrf": token},
            )
        joined = " ".join(r.message for r in caplog.records)
        assert "temporary-reset-pw-1" not in joined
        assert "password reset" in joined


class TestMustChangePasswordFlow:
    def test_reset_user_forced_to_change_before_using_app(self, client, seed_users):
        admin = seed_users["admin"]
        faculty = seed_users["faculty_a"]
        login(client, "admin@test.local", "admin-secret-pw-123")
        token = csrf_from(client, f"/admin/users/{faculty.id}/reset-password")
        client.post(
            f"/admin/users/{faculty.id}/reset-password",
            data={"new_password": "temporary-reset-pw-1", "_csrf": token},
        )
        client.cookies.jar.clear()

        login(client, "facultya@test.local", "temporary-reset-pw-1")
        # Any page other than the password page redirects to the change form.
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/account/password"
        resp = client.get("/students", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/account/password"
        # The password page itself is reachable.
        assert client.get("/account/password").status_code == 200

        token = csrf_from(client, "/account/password")
        resp = client.post(
            "/account/password",
            data={
                "current_password": "temporary-reset-pw-1",
                "new_password": "permanently-mine-pw!",
                "confirm_password": "permanently-mine-pw!",
                "_csrf": token,
            },
        )
        assert resp.status_code == 200
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 200

    def test_password_not_reset_still_requires_change_after_logout(self, client, db_session, seed_users):
        faculty = seed_users["faculty_a"]
        faculty.must_change_password = True
        db_session.commit()
        login(client, "facultya@test.local", "faculty-secret-pw-1")
        token = csrf_from(client, "/account/password")
        client.post("/logout", data={"_csrf": token}, follow_redirects=False)
        login(client, "facultya@test.local", "faculty-secret-pw-1")
        resp = client.get("/", follow_redirects=False)
        assert resp.headers["location"] == "/account/password"
