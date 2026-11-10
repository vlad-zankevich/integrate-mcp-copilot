"""
High School Management System API

A super simple FastAPI application that allows students to view and sign up
for extracurricular activities at Mergington High School.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

app = FastAPI(title="Mergington High School API",
              description="API for viewing and signing up for extracurricular activities")

# Mount the static files directory
current_dir = Path(__file__).parent
app.mount("/static", StaticFiles(directory=os.path.join(current_dir, "static")),
          name="static")

# Load the activity definitions separately so they can be edited without changing Python code.
with open(current_dir / "activities.json", encoding="utf-8") as activities_file:
    activities = json.load(activities_file)


def _is_supported_password_hash(password_hash: str) -> bool:
    try:
        algorithm, salt, digest = password_hash.split("$")
        bytes.fromhex(salt)
        bytes.fromhex(digest)
    except ValueError:
        return False
    return algorithm == "pbkdf2_sha256" and len(digest) == 64


with open(current_dir / "teachers.json", encoding="utf-8") as teachers_file:
    teacher_records = json.load(teachers_file)

if not isinstance(teacher_records, dict) or not isinstance(
        teacher_records.get("teachers"), list):
    raise ValueError("teachers.json must contain a 'teachers' list")

teachers = {}
for teacher in teacher_records["teachers"]:
    if not isinstance(teacher, dict):
        raise ValueError("Each teacher record must be an object")
    username = teacher.get("username")
    password_hash = teacher.get("password_hash")
    if not isinstance(username, str) or not username.strip():
        raise ValueError("Each teacher must have a non-empty username")
    if not isinstance(password_hash, str):
        raise ValueError(f"Teacher {username!r} must have a password_hash")
    if not _is_supported_password_hash(password_hash):
        raise ValueError(f"Teacher {username!r} has an invalid password_hash")
    if username in teachers:
        raise ValueError(f"Duplicate teacher username: {username}")
    teachers[username] = password_hash

SESSION_COOKIE_NAME = "teacher_session"
SESSION_MAX_AGE = 8 * 60 * 60
PASSWORD_HASH_ITERATIONS = 310_000
SESSION_SECRET = os.environ.get("TEACHER_SESSION_SECRET") or secrets.token_urlsafe(32)
SESSION_COOKIE_SECURE = os.environ.get("TEACHER_SESSION_HTTPS_ONLY", "").lower() in {
    "1", "true", "yes"
}
DUMMY_PASSWORD_SALT = secrets.token_hex(16)
DUMMY_PASSWORD_HASH = (
    "pbkdf2_sha256$"
    + DUMMY_PASSWORD_SALT
    + "$"
    + hashlib.pbkdf2_hmac(
        "sha256", secrets.token_bytes(32), DUMMY_PASSWORD_SALT.encode("utf-8"),
        PASSWORD_HASH_ITERATIONS
    ).hex()
)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


def _password_matches(password: str, stored_hash: str) -> bool:
    try:
        algorithm, salt, expected_hash = stored_hash.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        actual_hash = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"),
            PASSWORD_HASH_ITERATIONS
        ).hex()
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual_hash, expected_hash)


def _make_session_token(username: str) -> str:
    payload = json.dumps({
        "username": username,
        "expires": int(time.time()) + SESSION_MAX_AGE,
    }, separators=(",", ":")).encode("utf-8")
    encoded_payload = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    signature = hmac.new(
        SESSION_SECRET.encode("utf-8"), encoded_payload.encode("ascii"),
        hashlib.sha256
    ).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return f"{encoded_payload}.{encoded_signature}"


def _get_session_username(request: Request) -> str | None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None

    try:
        encoded_payload, encoded_signature = token.split(".", 1)
        expected_signature = hmac.new(
            SESSION_SECRET.encode("utf-8"), encoded_payload.encode("ascii"),
            hashlib.sha256
        ).digest()
        signature = base64.urlsafe_b64decode(
            encoded_signature + "=" * (-len(encoded_signature) % 4)
        )
        if not hmac.compare_digest(signature, expected_signature):
            return None
        payload = base64.urlsafe_b64decode(
            encoded_payload + "=" * (-len(encoded_payload) % 4)
        )
        session = json.loads(payload)
        username = session["username"]
        if (not isinstance(username, str) or username not in teachers
                or session["expires"] < time.time()):
            return None
        return username
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def require_teacher(request: Request) -> str:
    username = _get_session_username(request)
    if username is None:
        raise HTTPException(status_code=401, detail="Teacher login required")
    return username


@app.get("/")
def root():
    return RedirectResponse(url="/static/index.html")


@app.get("/auth/status")
def get_auth_status(request: Request):
    username = _get_session_username(request)
    return {"authenticated": username is not None, "username": username}


@app.post("/auth/login")
def login(credentials: LoginRequest):
    stored_hash = teachers.get(credentials.username, DUMMY_PASSWORD_HASH)
    password_matches = _password_matches(credentials.password, stored_hash)
    if credentials.username not in teachers or not password_matches:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    response = JSONResponse({"username": credentials.username})
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=_make_session_token(credentials.username),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=SESSION_COOKIE_SECURE,
        samesite="strict",
        path="/",
    )
    return response


@app.post("/auth/logout")
def logout():
    response = JSONResponse({"message": "Logged out"})
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        httponly=True,
        secure=SESSION_COOKIE_SECURE,
        samesite="strict",
        path="/",
    )
    return response


@app.get("/activities")
def get_activities():
    return activities


@app.post("/activities/{activity_name}/signup")
def signup_for_activity(activity_name: str, email: str,
                         _teacher: str = Depends(require_teacher)):
    """Sign up a student for an activity"""
    # Validate activity exists
    if activity_name not in activities:
        raise HTTPException(status_code=404, detail="Activity not found")

    # Get the specific activity
    activity = activities[activity_name]

    # Validate student is not already signed up
    if email in activity["participants"]:
        raise HTTPException(
            status_code=400,
            detail="Student is already signed up"
        )

    # Add student
    activity["participants"].append(email)
    return {"message": f"Signed up {email} for {activity_name}"}


@app.delete("/activities/{activity_name}/unregister")
def unregister_from_activity(activity_name: str, email: str,
                              _teacher: str = Depends(require_teacher)):
    """Unregister a student from an activity"""
    # Validate activity exists
    if activity_name not in activities:
        raise HTTPException(status_code=404, detail="Activity not found")

    # Get the specific activity
    activity = activities[activity_name]

    # Validate student is signed up
    if email not in activity["participants"]:
        raise HTTPException(
            status_code=400,
            detail="Student is not signed up for this activity"
        )

    # Remove student
    activity["participants"].remove(email)
    return {"message": f"Unregistered {email} from {activity_name}"}
