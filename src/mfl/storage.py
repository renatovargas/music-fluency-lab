"""Local, portable learner state. No account or network required.

Schema history (``PRAGMA user_version``):
  0 — v0.1–v0.4: a single ``attempts`` table (kept and still readable).
  1 — v0.5: skills (spaced-repetition state), results, sessions, settings.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import sqlite3

SCHEMA_VERSION = 1


def db_path() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "mfl" / "progress.sqlite3"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Progress:
    def __init__(self, path: Path | None = None):
        self.path = path or db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS attempts (id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, "
            "exercise TEXT NOT NULL, chord TEXT NOT NULL, success INTEGER NOT NULL, seconds REAL NOT NULL, "
            "voicing TEXT NOT NULL, distance INTEGER)"
        )
        self._migrate()
        self.db.commit()

    # ---- schema -------------------------------------------------------------------
    def _migrate(self):
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version < 1:
            self.db.executescript(
                """
                CREATE TABLE IF NOT EXISTS skills (
                    skill TEXT PRIMARY KEY, reps INTEGER NOT NULL DEFAULT 0, lapses INTEGER NOT NULL DEFAULT 0,
                    ease REAL NOT NULL DEFAULT 2.5, interval REAL NOT NULL DEFAULT 0, due TEXT,
                    last_review TEXT, last_grade INTEGER, introduced TEXT);
                CREATE TABLE IF NOT EXISTS results (
                    id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, day TEXT NOT NULL, session INTEGER,
                    skill TEXT NOT NULL, kind TEXT NOT NULL, grade INTEGER NOT NULL, score REAL,
                    seconds REAL, hints INTEGER, details TEXT);
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY, day TEXT NOT NULL, started TEXT NOT NULL, updated TEXT NOT NULL,
                    plan TEXT NOT NULL, position INTEGER NOT NULL DEFAULT 0, finished INTEGER NOT NULL DEFAULT 0,
                    seconds REAL NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS results_day ON results(day);
                """
            )
            self._seed_from_legacy()
            self.db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _seed_from_legacy(self):
        """Chords recalled from memory in v0.2–v0.4 count as introduced."""
        rows = self.db.execute(
            "SELECT chord, MIN(substr(timestamp, 1, 10)) FROM attempts "
            "WHERE exercise IN ('chord_recall', 'chord') AND success = 1 AND chord != '' GROUP BY chord"
        ).fetchall()
        today = date.today().isoformat()
        for chord, first in rows:
            self.db.execute(
                "INSERT OR IGNORE INTO skills (skill, reps, interval, due, last_review, last_grade, introduced) "
                "VALUES (?, 1, 1, ?, ?, 3, ?)",
                (f"chord/{chord}", today, first, first),
            )

    # ---- legacy attempts API (kept for v0.4 compatibility) ---------------------------
    def record(self, exercise: str, chord: str, success: bool, seconds: float, notes, distance: int | None):
        self.db.execute(
            "INSERT INTO attempts (timestamp,exercise,chord,success,seconds,voicing,distance) VALUES (?,?,?,?,?,?,?)",
            (_now(), exercise, chord, int(success), seconds, ",".join(map(str, sorted(notes))), distance),
        )
        self.db.commit()

    def completed_sessions(self) -> int:
        legacy = self.db.execute("SELECT COUNT(*) FROM attempts WHERE exercise='session_complete'").fetchone()[0]
        current = self.db.execute("SELECT COUNT(*) FROM sessions WHERE finished = 1").fetchone()[0]
        return int(legacy) + int(current)

    def mark_session_complete(self):
        self.record("session_complete", "", True, 0, set(), None)

    def last_attempts(self, limit=10, *, include_exercise=False):
        rows = self.db.execute(
            """SELECT chord, success, round(seconds, 1), distance, exercise
               FROM attempts
               WHERE exercise IN ('chord', 'chord_guided', 'chord_recall', 'chord_skip')
               ORDER BY id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        rows = [tuple(r) for r in rows]
        return rows if include_exercise else [row[:4] for row in rows]

    # ---- skills (spaced repetition state) ----------------------------------------------
    def skill(self, skill: str) -> dict | None:
        row = self.db.execute("SELECT * FROM skills WHERE skill = ?", (skill,)).fetchone()
        return dict(row) if row else None

    def skills(self) -> dict[str, dict]:
        return {row["skill"]: dict(row) for row in self.db.execute("SELECT * FROM skills")}

    def save_skill(self, state: dict):
        columns = ("skill", "reps", "lapses", "ease", "interval", "due", "last_review", "last_grade", "introduced")
        self.db.execute(
            f"INSERT OR REPLACE INTO skills ({','.join(columns)}) VALUES ({','.join('?' * len(columns))})",
            tuple(state.get(c) for c in columns),
        )
        self.db.commit()

    # ---- results -------------------------------------------------------------------------
    def add_result(self, *, skill: str, kind: str, grade: int, score: float | None, seconds: float,
                   hints: int, details: dict | None = None, session: int | None = None, day: str | None = None):
        self.db.execute(
            "INSERT INTO results (timestamp, day, session, skill, kind, grade, score, seconds, hints, details) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (_now(), day or date.today().isoformat(), session, skill, kind, grade, score, seconds, hints,
             json.dumps(details or {})),
        )
        self.db.commit()

    def recent_results(self, limit: int = 20) -> list[dict]:
        rows = self.db.execute("SELECT * FROM results ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def practice_days(self) -> list[str]:
        rows = self.db.execute(
            "SELECT DISTINCT day FROM results UNION SELECT DISTINCT substr(timestamp, 1, 10) FROM attempts "
            "ORDER BY 1"
        ).fetchall()
        return [r[0] for r in rows]

    def minutes_since(self, day: str) -> float:
        row = self.db.execute("SELECT COALESCE(SUM(seconds), 0) FROM sessions WHERE day >= ?", (day,)).fetchone()
        return float(row[0]) / 60

    # ---- sessions -------------------------------------------------------------------------
    def open_session(self, day: str) -> dict | None:
        row = self.db.execute(
            "SELECT * FROM sessions WHERE day = ? AND finished = 0 ORDER BY id DESC LIMIT 1", (day,)
        ).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["plan"] = json.loads(data["plan"])
        return data

    def sessions_on(self, day: str) -> int:
        return int(self.db.execute("SELECT COUNT(*) FROM sessions WHERE day = ?", (day,)).fetchone()[0])

    def create_session(self, day: str, plan: list[dict]) -> int:
        cursor = self.db.execute(
            "INSERT INTO sessions (day, started, updated, plan) VALUES (?,?,?,?)",
            (day, _now(), _now(), json.dumps(plan)),
        )
        self.db.commit()
        return int(cursor.lastrowid)

    def update_session(self, session: int, *, position: int | None = None, finished: bool | None = None,
                       add_seconds: float = 0.0, plan: list[dict] | None = None):
        parts, values = ["updated = ?", "seconds = seconds + ?"], [_now(), add_seconds]
        if position is not None:
            parts.append("position = ?")
            values.append(position)
        if finished is not None:
            parts.append("finished = ?")
            values.append(int(finished))
        if plan is not None:
            parts.append("plan = ?")
            values.append(json.dumps(plan))
        self.db.execute(f"UPDATE sessions SET {', '.join(parts)} WHERE id = ?", (*values, session))
        self.db.commit()

    # ---- settings -------------------------------------------------------------------------
    def setting(self, key: str, default=None):
        row = self.db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key: str, value):
        self.db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, json.dumps(value)))
        self.db.commit()

    def close(self):
        self.db.close()
