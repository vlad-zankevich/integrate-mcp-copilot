import asyncio
import hashlib
import json
import secrets
import unittest
from copy import deepcopy
from http.cookies import SimpleCookie
from urllib.parse import urlencode

from src import app as app_module


class ASGIClient:
    def __init__(self, app):
        self.app = app
        self.cookies = {}
        self.response_headers = {}

    def request(self, method, path, *, params=None, json_body=None):
        query = urlencode(params or {}).encode("ascii")
        body = json.dumps(json_body).encode("utf-8") if json_body is not None else b""
        headers = [(b"host", b"testserver")]
        if json_body is not None:
            headers.append((b"content-type", b"application/json"))
        if self.cookies:
            cookie_header = "; ".join(
                f"{key}={value}" for key, value in self.cookies.items()
            )
            headers.append((b"cookie", cookie_header.encode("ascii")))

        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": query,
            "root_path": "",
            "headers": headers,
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "state": {},
        }
        messages = [{"type": "http.request", "body": body, "more_body": False}]
        response_messages = []

        async def receive():
            if messages:
                return messages.pop(0)
            return {"type": "http.disconnect"}

        async def send(message):
            response_messages.append(message)

        asyncio.run(self.app(scope, receive, send))
        response_start = next(
            message for message in response_messages
            if message["type"] == "http.response.start"
        )
        self.response_headers = dict(response_start["headers"])
        response_body = b"".join(
            message.get("body", b"") for message in response_messages
            if message["type"] == "http.response.body"
        )
        for key, value in response_start["headers"]:
            if key.lower() == b"set-cookie":
                cookie = SimpleCookie()
                cookie.load(value.decode("latin-1"))
                for name, morsel in cookie.items():
                    if morsel["max-age"] == "0":
                        self.cookies.pop(name, None)
                    else:
                        self.cookies[name] = morsel.value

        return response_start["status"], json.loads(response_body)


class TeacherAuthenticationTests(unittest.TestCase):
    def setUp(self):
        salt = secrets.token_hex(16)
        password_hash = hashlib.pbkdf2_hmac(
            "sha256", b"test-password", salt.encode(), 310_000
        ).hex()
        self.previous_teachers = app_module.teachers.copy()
        self.previous_activities = deepcopy(app_module.activities)
        app_module.teachers.clear()
        app_module.teachers["teacher"] = f"pbkdf2_sha256${salt}${password_hash}"
        self.client = ASGIClient(app_module.app)

    def tearDown(self):
        app_module.teachers.clear()
        app_module.teachers.update(self.previous_teachers)
        app_module.activities.clear()
        app_module.activities.update(self.previous_activities)

    def test_activity_mutations_require_teacher_login(self):
        signup_status, _ = self.client.request(
            "POST", "/activities/Chess Club/signup",
            params={"email": "new-student@mergington.edu"},
        )
        unregister_status, _ = self.client.request(
            "DELETE", "/activities/Chess Club/unregister",
            params={"email": "michael@mergington.edu"},
        )

        self.assertEqual(signup_status, 401)
        self.assertEqual(unregister_status, 401)
        activities_status, activities = self.client.request("GET", "/activities")
        self.assertEqual(activities_status, 200)
        self.assertIn("michael@mergington.edu",
                      activities["Chess Club"]["participants"])

    def test_teacher_login_allows_registration_and_logout_revokes_access(self):
        login_status, login_body = self.client.request(
            "POST", "/auth/login",
            json_body={"username": "teacher", "password": "test-password"},
        )
        self.assertEqual(login_status, 200)
        self.assertEqual(login_body["username"], "teacher")
        set_cookie = self.client.response_headers[b"set-cookie"].decode("latin-1")
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("SameSite=strict", set_cookie)
        _, status = self.client.request("GET", "/auth/status")
        self.assertTrue(status["authenticated"])

        signup_status, _ = self.client.request(
            "POST", "/activities/Chess Club/signup",
            params={"email": "new-student@mergington.edu"},
        )
        self.assertEqual(signup_status, 200)
        unregister_status, _ = self.client.request(
            "DELETE", "/activities/Chess Club/unregister",
            params={"email": "new-student@mergington.edu"},
        )
        self.assertEqual(unregister_status, 200)

        logout_status, _ = self.client.request("POST", "/auth/logout")
        self.assertEqual(logout_status, 200)
        _, status = self.client.request("GET", "/auth/status")
        self.assertFalse(status["authenticated"])
        self.assertEqual(
            self.client.request(
                "POST", "/activities/Chess Club/signup",
                params={"email": "another-student@mergington.edu"},
            )[0],
            401,
        )

    def test_invalid_password_is_rejected(self):
        status, _ = self.client.request(
            "POST", "/auth/login",
            json_body={"username": "teacher", "password": "wrong-password"},
        )
        self.assertEqual(status, 401)


if __name__ == "__main__":
    unittest.main()
