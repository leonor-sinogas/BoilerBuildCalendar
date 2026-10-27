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
CLASS_YEARS_PATH = (Path(__file__).parent / "../../class_years.md").resolve()

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
# Planning baseline supplied for the Indianapolis campus.  These figures are
# deliberately kept separate from the small local schedule sample so the app
# can estimate an audience at campus scale.
YEAR_POPULATION = {
    "Freshman": 756,   # 30% of 2,520
    "Sophomore": 630,  # 25% of 2,520
    "Junior": 580,     # 23% of 2,520, rounded
    "Senior": 554,     # Remaining students; total is exactly 2,520
}
WEEK_ORDER = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
TIME_PREFERENCES = {
    "business_hours": (9 * 60, 17 * 60),
    "after_hours": (16 * 60, 21 * 60),
}

CLASS_MAJOR_ALIASES = {"CE": "CompE", "MSPE": "MotorsportsE", "IE": "IndustrialE"}

def course_catalog() -> dict[str, dict]:
    try:
        entries = CLASS_YEARS_PATH.read_text().splitlines()
    except OSError:
        return {}
    result: dict[str, dict] = {}
    for entry in entries:
        match = re.fullmatch(r"- ([A-Z]+ \d{5}) (\d(?:\.5)?)(?: (.*))?", entry.strip())
        if match:
            majors = {CLASS_MAJOR_ALIASES.get(major.strip(), major.strip()) for major in (match.group(3) or "").split(",") if major.strip()}
            result[match.group(1)] = {"year": float(match.group(2)), "majors": majors}
    return result

COURSE_CATALOG = course_catalog()
COURSE_YEARS = {code: info["year"] for code, info in COURSE_CATALOG.items()}

class Filters(BaseModel):
    source_mode: str = Field(default="student_data", pattern="^(student_data|class_schedule_data)$")
    majors: list[str] = Field(default_factory=list)
    colleges: list[str] = Field(default_factory=list)
    academic_years: list[str] = Field(default_factory=list)
    duration_minutes: int = Field(default=60, ge=30, le=240, multiple_of=30)
    days: list[str] = Field(default_factory=list)
    time_preferences: list[str] = Field(default_factory=list)
    semester: int = Field(default=1, ge=1, le=2)
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

def course_year(course: dict) -> float | None:
    match = re.match(r"([A-Z]+ \d{5})", course["course_code"])
    return COURSE_YEARS.get(match.group(1)) if match else None

def course_majors(course: dict) -> set[str]:
    match = re.match(r"([A-Z]+ \d{5})", course["course_code"])
    return COURSE_CATALOG.get(match.group(1), {}).get("majors", set()) if match else set()

def estimated_target_population(data: dict, filters: Filters) -> int:
    """Estimate the selected audience from the campus population baseline.

    Academic-year filters use the supplied campus totals directly.  When a
    major or college is also selected, the matching share of the local student
    sample is used to estimate that share within each academic year.
    """
    target_years = filters.academic_years or YEAR_ORDER
    estimate = 0.0
    for year in target_years:
        cohort = [student for student in data["students"] if student["academic_year"] == year]
        if not cohort:
            continue
        matching = [
            student for student in cohort
            if (not filters.majors or canonical_major(student["major"]) in filters.majors)
            and (not filters.colleges or college_for_major(canonical_major(student["major"])) in filters.colleges)
        ]
        share = len(matching) / len(cohort) if (filters.majors or filters.colleges) else 1.0
        estimate += YEAR_POPULATION[year] * share
    return round(estimate)

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
    course_map = {c["course_id"]: c for c in data["courses"]}
    selected = [s for s in data["students"] if (not filters.majors or canonical_major(s["major"]) in filters.majors) and (not filters.colleges or college_for_major(canonical_major(s["major"])) in filters.colleges) and (not filters.academic_years or s["academic_year"] in filters.academic_years)]
    selected_year_numbers = {YEAR_ORDER.index(year) + 1 for year in filters.academic_years if year in YEAR_ORDER}
    base_years = selected_year_numbers or set(range(1, 5))
    semester_offset = 0.0 if filters.semester == 1 else 0.5
    selected_course_years = {year + semester_offset for year in base_years}
    selected_courses = [course for course in data["courses"] if course_year(course) in selected_course_years and (not filters.majors or course_majors(course) & set(filters.majors)) and (not filters.colleges or any(college_for_major(major) in filters.colleges for major in course_majors(course)))]
    if filters.source_mode == "student_data" and not selected:
        return {"target_students": 0, "recommendations": [], "message": "No students match these filters.", "population_label": "target students"}
    if filters.source_mode == "class_schedule_data" and not selected_courses:
        term = "Fall" if filters.semester == 1 else "Spring"
        return {"target_students": 0, "recommendations": [], "message": f"No {term} class sections match these filters.", "population_label": "estimated target students"}
    total_population = estimated_target_population(data, filters)
    population_label = "estimated target students"
    chosen_days = filters.days or WEEK_ORDER
    windows = [(filters.start_hour * 60, filters.end_hour * 60)]
    time_preference_selected = bool(filters.time_preferences)
    if filters.time_preferences:
        invalid = set(filters.time_preferences) - set(TIME_PREFERENCES)
        if invalid:
            raise HTTPException(422, "Unknown time preference")
        chosen_days = [day for day in chosen_days if day in WEEKDAYS]
        windows = [TIME_PREFERENCES[preference] for preference in filters.time_preferences]
    results_by_slot = {}
    for day in chosen_days:
        for window_start, window_end in windows:
            # Preset time preferences describe valid *start* times.  For example,
            # Business Hours includes every weekday start from 9:00 AM through
            # 5:00 PM, even when the chosen event duration ends later.
            last_start = window_end if time_preference_selected else window_end - filters.duration_minutes
            for start in range(window_start, last_start + 1, 30):
                end = start + filters.duration_minutes
                if filters.source_mode == "student_data":
                    sample_free = sum(not any(day in meeting["days"] and minutes(meeting["start_time"]) < end and minutes(meeting["end_time"]) > start for cid in student["course_ids"] for meeting in course_map[cid]["meetings"]) for student in selected)
                    free = round(total_population * sample_free / len(selected))
                    busy = total_population - free
                else:
                    busy = sum(max(course["capacity"] - course["open_seats"], 0) for course in selected_courses if any(day in meeting["days"] and minutes(meeting["start_time"]) < end and minutes(meeting["end_time"]) > start for meeting in course["meetings"]))
                    free = max(total_population - busy, 0)
                results_by_slot[(day, start)] = {"day": day, "start_time": f"{start // 60:02}:{start % 60:02}", "end_time": f"{end // 60:02}:{end % 60:02}", "free_students": free, "busy_students": busy, "availability_percent": round(free / total_population * 100, 1) if total_population else 0}
    results = list(results_by_slot.values())
    ranked = sorted(results, key=lambda r: (-r["availability_percent"], -r["free_students"], r["day"], r["start_time"]))
    day_order = {day: index for index, day in enumerate(WEEK_ORDER)}
    heatmap = sorted(results, key=lambda r: (day_order.get(r["day"], 99), r["start_time"]))
    return {"target_students": total_population, "population_label": population_label, "population_assumption": "2,520 Indianapolis students: 30% freshman, 25% sophomore, 23% junior, 22% senior.", "semester": filters.semester, "source_mode": filters.source_mode, "recommendations": ranked[:12], "heatmap": heatmap}
