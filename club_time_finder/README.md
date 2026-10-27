# Club Time Finder

Local-first tool for clubs to identify event windows where their selected audience is least likely to be in class.

## Run locally

```bash
cd backend
cp .env.example .env # change secrets before use
docker compose up -d db
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

In a second terminal:

```bash
cd frontend
flutter pub get
flutter run -d chrome --dart-define=API_BASE_URL=http://localhost:8000
```

The seeded local account is `admin@example.local` / `change-me-now`. Change it in `.env` before exposing the backend anywhere.

You can also use **Create an account** on the sign-in screen. Passwords must be at least 12 characters and are stored only as Argon2 hashes in the local user database.

## How recommendations work

For each 30-minute candidate window, the API first selects students matching the requested majors and/or academic years. It marks a student busy if **any** of their assigned course meetings overlaps the full event interval. The score is the percentage of selected unique students who remain free. Results are sorted by highest free percentage, then largest free count, then earliest time. The UI also shows every candidate time in a day-by-day heatmap.

This makes the metric an availability estimate, not an attendance guarantee: jobs, travel time, clubs, and personal preferences are not in this dataset.

## Security and operations

- Authentication uses short-lived signed JWT access tokens and Argon2 password hashes. Local accounts persist in a SQLite file; migrate that table to PostgreSQL before a shared deployment.
- The API is designed to be private behind Caddy; local development exposes only the API port. PostgreSQL is not published to the host.
- `docker-compose.yml` uses a named PostgreSQL volume; `infra/backup-postgres.sh` creates a compressed logical backup.
- Production configuration belongs in a private EC2 subnet/security group, with Systems Manager Session Manager instead of SSH, Caddy terminating HTTPS, EBS-backed volumes, and scheduled encrypted backups. See `infra/production-notes.md`.

The root-level `students_classes.json` is the local schedule source used by the API. Its student records provide `major` and `academic_year`; add an explicit `department` field when UniTime/registration data makes that reliable, rather than guessing it from a major. A future import endpoint should validate, version, and persist approved uploads in PostgreSQL/object storage before analysis. Academic deadlines and university events should be a separately managed conflict feed that removes or penalizes affected windows.
