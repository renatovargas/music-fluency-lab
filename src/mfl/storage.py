"""Local, portable learner state. No account or network required."""
import os
import sqlite3
from pathlib import Path
from datetime import datetime, timezone


def db_path() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "mfl" / "progress.sqlite3"

class Progress:
    def __init__(self, path: Path | None = None):
        self.path = path or db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.execute("CREATE TABLE IF NOT EXISTS attempts (id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, exercise TEXT NOT NULL, chord TEXT NOT NULL, success INTEGER NOT NULL, seconds REAL NOT NULL, voicing TEXT NOT NULL, distance INTEGER)")
        self.db.commit()

    def record(self, exercise: str, chord: str, success: bool, seconds: float, notes: set[int], distance: int | None):
        self.db.execute("INSERT INTO attempts (timestamp,exercise,chord,success,seconds,voicing,distance) VALUES (?,?,?,?,?,?,?)", (datetime.now(timezone.utc).isoformat(), exercise, chord, int(success), seconds, ",".join(map(str, sorted(notes))), distance))
        self.db.commit()

    def completed_sessions(self) -> int:
        row = self.db.execute("SELECT COUNT(*) FROM attempts WHERE exercise='session_complete'").fetchone()
        return int(row[0])

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
        return rows if include_exercise else [row[:4] for row in rows]

    def close(self):
        self.db.close()
