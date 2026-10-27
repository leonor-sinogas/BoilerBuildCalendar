from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

import jwt
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from pwdlib import PasswordHash

app = FastAPI(title="Club Time Finder", version="0.1.0", docs_url=None if os.getenv("ENV") == "production" else "/docs")
# Flutter's Chrome debug server chooses a dynamic loopback port. Restrict CORS to
# loopback origins rather than allowing arbitrary websites to call this API.
app.add_middleware(CORSMiddleware, allow_origins=[], allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):[0-9]+$", allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"])

password_hash = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)
SECRET = os.getenv("CLUB_TIME_JWT_SECRET", "local-development-secret-change-before-production")
EMAIL = os.getenv("CLUB_TIME_ADMIN_EMAIL", "admin@example.local")
PASSWORD = os.getenv("CLUB_TIME_ADMIN_PASSWORD", "change-me-now")
PASSWORD_HASH = password_hash.hash(PASSWORD)
USERS_DB_PATH = Path(os.getenv("CLUB_TIME_USERS_DB_PATH", "../data/users.sqlite3"))
DATA_PATH = Path(os.getenv("CLUB_TIME_DATASET_PATH", "../../../students_classes.json"))
if not DATA_PATH.is_absolute():
    DATA_PATH = (Path(__file__).parent / DATA_PATH).resolve()
if not USERS_DB_PATH.is_absolute():
    USERS_DB_PATH = (Path(__file__).parent / USERS_DB_PATH).resolve()

def users_db() -> sqlite3.Connection:
    USERS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(USERS_DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection

def initialize_users() -> None:
    with users_db() as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS users (email TEXT PRIMARY KEY, password_hash TEXT NOT NULL, created_at TEXT NOT NULL)")
        connection.execute("INSERT OR IGNORE INTO users (email, password_hash, created_at) VALUES (?, ?, ?)", (EMAIL.lower(), PASSWORD_HASH, datetime.now(timezone.utc).isoformat()))

initialize_users()

# Canonical labels shown in the app. Aliases keep the proof-of-concept JSON
# compatible with the concise names stakeholders want to filter by.
COLLEGE_MAJORS = {
    "Science": ["CS", "DS", "AI", "Math"],
    "Polytechnic": ["MET", "Interior Architecture Design", "CIT", "Cybersecurity", "Computer Graphics Tech", "Construction Management Tech"],
    "Engineering": ["CompE", "EE", "ME", "MotorsportsE", "BME", "IndustrialE"],
    "College of Health and Human Sciences": ["Hospitality Tourism"],
    "Mitchell Business": ["IBE"],
}
MAJOR_ALIASES = {
    "Computer Science": "CS", "Data Science": "DS", "Mathematics": "Math",
    "Electrical Engineering": "EE", "Mechanical Engineering": "ME",
}
YEAR_ORDER = ["Freshman", "Sophomore", "Junior", "Senior"]
WEEK_ORDER = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
TIME_PREFERENCES = {
    "business_hours": (9 * 60, 17 * 60),
    "after_hours": (16 * 60, 21 * 60),
}

class Filters(BaseModel):
    majors: list[str] = Field(default_factory=list)
    colleges: list[str] = Field(default_factory=list)
    academic_years: list[str] = Field(default_factory=list)
    duration_minutes: int = Field(default=60, ge=30, le=240, multiple_of=30)
    days: list[str] = Field(default_factory=list)
    time_preferences: list[str] = Field(default_factory=list)
    start_hour: int = Field(default=8, ge=0, le=23)
    end_hour: int = Field(default=20, ge=1, le=24)

class CreateAccount(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128)

def dataset() -> dict:
    try:
        return json.loads(DATA_PATH.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(500, "Schedule dataset is unavailable") from exc

def require_user(creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> str:
    if not creds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    try:
        claims = jwt.decode(creds.credentials, SECRET, algorithms=["HS256"], audience="club-time-finder")
        return claims["sub"]
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired access token") from exc

def minutes(value: str) -> int:
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute

def canonical_major(student_major: str) -> str:
    return MAJOR_ALIASES.get(student_major, student_major)

def college_for_major(major: str) -> str | None:
    return next((college for college, majors in COLLEGE_MAJORS.items() if major in majors), None)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/auth/token")
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()]):
    # Argon2 work is performed even for unknown identities, limiting account-enumeration timing leaks.
    with users_db() as connection:
        user = connection.execute("SELECT email, password_hash FROM users WHERE email = ?", (form.username.strip().lower(),)).fetchone()
    password_ok = password_hash.verify(form.password, user["password_hash"] if user else PASSWORD_HASH)
    valid = user is not None and password_ok
    if not valid:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    token = jwt.encode({"sub": user["email"], "aud": "club-time-finder", "exp": datetime.now(timezone.utc) + timedelta(minutes=30)}, SECRET, algorithm="HS256")
    return {"access_token": token, "token_type": "bearer"}

@app.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register(account: CreateAccount):
    email = account.email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(422, "Enter a valid email address")
    with users_db() as connection:
        try:
            connection.execute("INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)", (email, password_hash.hash(account.password), datetime.now(timezone.utc).isoformat()))
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, "An account already exists for that email") from exc
    return {"email": email}

@app.get("/api/filters")
def filter_options(_: Annotated[str, Depends(require_user)]):
    data = dataset()
    return {"majors": [major for majors in COLLEGE_MAJORS.values() for major in majors], "colleges": list(COLLEGE_MAJORS), "academic_years": [year for year in YEAR_ORDER if any(s["academic_year"] == year for s in data["students"])], "days": WEEK_ORDER, "time_preferences": ["business_hours", "after_hours"], "slot_minutes": data["metadata"]["time_slot_minutes"]}

@app.post("/api/recommendations")
def recommendations(filters: Filters, _: Annotated[str, Depends(require_user)]):
    if filters.end_hour <= filters.start_hour:
        raise HTTPException(422, "End hour must be after start hour")
    data = dataset()
    selected = [s for s in data["students"] if (not filters.majors or canonical_major(s["major"]) in filters.majors) and (not filters.colleges or college_for_major(canonical_major(s["major"])) in filters.colleges) and (not filters.academic_years or s["academic_year"] in filters.academic_years)]
    if not selected:
        return {"target_students": 0, "recommendations": [], "message": "No students match these filters."}
    course_map = {c["course_id"]: c for c in data["courses"]}
    chosen_days = filters.days or WEEK_ORDER
    windows = [(filters.start_hour * 60, filters.end_hour * 60)]
    if filters.time_preferences:
        invalid = set(filters.time_preferences) - set(TIME_PREFERENCES)
        if invalid:
            raise HTTPException(422, "Unknown time preference")
        chosen_days = [day for day in chosen_days if day in WEEKDAYS]
        windows = [TIME_PREFERENCES[preference] for preference in filters.time_preferences]
    results_by_slot = {}
    for day in chosen_days:
        for window_start, window_end in windows:
            for start in range(window_start, window_end - filters.duration_minutes + 1, 30):
                end = start + filters.duration_minutes
                free = 0
                for student in selected:
                    busy = any(day in meeting["days"] and minutes(meeting["start_time"]) < end and minutes(meeting["end_time"]) > start for cid in student["course_ids"] for meeting in course_map[cid]["meetings"])
                    free += not busy
                results_by_slot[(day, start)] = {"day": day, "start_time": f"{start // 60:02}:{start % 60:02}", "end_time": f"{end // 60:02}:{end % 60:02}", "free_students": free, "busy_students": len(selected) - free, "availability_percent": round(free / len(selected) * 100, 1)}
    results = list(results_by_slot.values())
    ranked = sorted(results, key=lambda r: (-r["availability_percent"], -r["free_students"], r["day"], r["start_time"]))
    day_order = {day: index for index, day in enumerate(WEEK_ORDER)}
    heatmap = sorted(results, key=lambda r: (day_order.get(r["day"], 99), r["start_time"]))
    return {"target_students": len(selected), "recommendations": ranked[:12], "heatmap": heatmap}
