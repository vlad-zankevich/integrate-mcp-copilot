# Mergington High School Activities API

A super simple FastAPI application that allows students to view and sign up for extracurricular activities.

## Features

- View all available extracurricular activities
- Teacher login for managing student registrations
- Public viewing of activities and participants

## Getting Started

1. Install the dependencies:

   ```
   pip install fastapi uvicorn
   ```

2. Run the application:

   ```
   cd src
   uvicorn app:app --reload
   ```

3. Open your browser and go to:
   - API documentation: http://localhost:8000/docs
   - Alternative documentation: http://localhost:8000/redoc

## Teacher Accounts

Teacher credentials are stored in `teachers.json`; each password must be a
PBKDF2-HMAC-SHA256 hash, never plaintext. Add assigned teacher accounts to the
`teachers` array with a username and password hash, for example:

```json
{
  "teachers": [
    {
      "username": "teacher-name",
      "password_hash": "pbkdf2_sha256$<salt>$<64-character-hex-digest>"
    }
  ]
}
```

Generate a salted hash with Python:

```python
import getpass
import hashlib
import secrets

password = getpass.getpass("Teacher password: ").encode()
salt = secrets.token_hex(16)
digest = hashlib.pbkdf2_hmac("sha256", password, salt.encode(), 310_000).hex()
print(f"pbkdf2_sha256${salt}${digest}")
```

Restart the app after editing `teachers.json`. The repository ships with an
empty teacher list, so no default account or password is enabled.

The app signs an eight-hour, HTTP-only, SameSite=Strict session cookie. For
deployments, set `TEACHER_SESSION_SECRET` to a persistent random secret and
serve the app over HTTPS with `TEACHER_SESSION_HTTPS_ONLY=true`. Without a
configured secret, a random process-local key is used and all sessions expire
when the server restarts.

## API Endpoints

| Method | Endpoint                                                          | Description                                                         |
| ------ | ----------------------------------------------------------------- | ------------------------------------------------------------------- |
| GET    | `/activities`                                                     | Get all activities with their details and current participant count |
| GET    | `/auth/status`                                                    | Check whether the current browser is signed in as a teacher          |
| POST   | `/auth/login`                                                      | Sign in with a teacher username and password                         |
| POST   | `/auth/logout`                                                     | Sign out the current teacher                                         |
| POST   | `/activities/{activity_name}/signup?email=student@mergington.edu` | Sign up a student (teacher login required)                           |
| DELETE | `/activities/{activity_name}/unregister?email=student@mergington.edu` | Remove a student (teacher login required)                        |

## Data Model

The application uses a simple data model with meaningful identifiers:

1. **Activities** - Uses activity name as identifier:

   - Description
   - Schedule
   - Maximum number of participants allowed
   - List of student emails who are signed up

2. **Students** - Uses email as identifier:
   - Name
   - Grade level

Activity registration data is stored in memory, which means changes will be
reset when the server restarts. Teacher account definitions are read from
`teachers.json` at startup.
