from tests.conftest import csrf_from, login


class TestAuthentication:
    def test_login_page_loads(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200
        assert "Faculty sign in" in resp.text

    def test_login_success_sets_session(self, client, seed_users):
        token = csrf_from(client)
        resp = client.post(
            "/login",
            data={"email": "admin@test.local", "password": "admin-secret-pw-123", "_csrf": token},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/"
        assert "session=" in resp.headers.get("set-cookie", "").lower()
        assert "httponly" in resp.headers.get("set-cookie", "").lower()

    def test_login_wrong_password_rejected(self, client, seed_users):
        token = csrf_from(client)
        resp = client.post(
            "/login",
            data={"email": "admin@test.local", "password": "wrong-password", "_csrf": token},
        )
        assert resp.status_code == 401
        assert "Invalid email or password" in resp.text

    def test_login_case_insensitive_email(self, client, seed_users):
        token = csrf_from(client)
        resp = client.post(
            "/login",
            data={"email": "ADMIN@test.local", "password": "admin-secret-pw-123", "_csrf": token},
            follow_redirects=False,
        )
        assert resp.status_code == 303

    def test_inactive_user_cannot_login(self, client, seed_users):
        token = csrf_from(client)
        resp = client.post(
            "/login",
            data={"email": "inactive@test.local", "password": "inactive-secret-pw", "_csrf": token},
        )
        assert resp.status_code == 401

    def test_unauthenticated_redirects_to_login(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"].startswith("/login")

    def test_logout_clears_session(self, client, seed_users):
        login(client, "admin@test.local", "admin-secret-pw-123")
        token = csrf_from(client, "/")
        resp = client.post("/logout", data={"_csrf": token}, follow_redirects=False)
        assert resp.status_code == 303
        resp = client.get("/", follow_redirects=False)
        assert resp.headers["location"].startswith("/login")


class TestPasswordHashing:
    def test_passwords_are_hashed_not_plaintext(self, seed_users):
        for user in seed_users.values():
            assert "secret" not in user.password_hash or user.password_hash.startswith("$2")
            assert user.password_hash != "admin-secret-pw-123"

    def test_session_of_deactivated_user_rejected(self, client, db_session, seed_users):
        login(client, "facultya@test.local", "faculty-secret-pw-1")
        faculty_a = seed_users["faculty_a"]
        faculty_a.is_active = False
        db_session.commit()
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"].startswith("/login")
