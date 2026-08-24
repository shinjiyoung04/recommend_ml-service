import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .schemas import ChatMessage, Preference, RecommendationEvent, RecommendationEventCreate


class _ClosingSQLiteConnection(sqlite3.Connection):
    """Commit/rollback like sqlite3's context manager, then release the file."""

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


class MeetupDatabase:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self):
        connection = sqlite3.connect(
            self.path,
            factory=_ClosingSQLiteConnection,
        )
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self):
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS chat_rooms (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    state_version INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    reply_to_message_id INTEGER NULL,
                    mentioned_user_ids TEXT NOT NULL DEFAULT '[]',
                    idempotency_key TEXT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(room_id) REFERENCES chat_rooms(id)
                );
                CREATE INDEX IF NOT EXISTS idx_chat_messages_room ON chat_messages(room_id, id);
                CREATE TABLE IF NOT EXISTS preference_snapshots (
                    room_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    preference_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(room_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS chat_analysis_progress (
                    room_id TEXT PRIMARY KEY,
                    last_message_id INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS recommendation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room_id TEXT NOT NULL,
                    round_id TEXT NOT NULL,
                    movie_id TEXT NOT NULL,
                    movie_title TEXT NOT NULL,
                    rank_no INTEGER NOT NULL,
                    group_score REAL NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_recommendation_room ON recommendation_history(room_id, id);
                CREATE TABLE IF NOT EXISTS recommendation_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    room_id TEXT NOT NULL,
                    round_id TEXT NOT NULL,
                    user_id TEXT NULL,
                    movie_id TEXT NULL,
                    rank_no INTEGER NULL,
                    event_type TEXT NOT NULL,
                    model_version TEXT NULL,
                    payload TEXT NOT NULL DEFAULT '{}',
                    occurred_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_recommendation_events_round ON recommendation_events(round_id, occurred_at);
                CREATE INDEX IF NOT EXISTS idx_recommendation_events_training ON recommendation_events(event_type, model_version, occurred_at);
            """)

            room_columns = {row["name"] for row in db.execute("PRAGMA table_info(chat_rooms)").fetchall()}
            if "state_version" not in room_columns:
                db.execute("ALTER TABLE chat_rooms ADD COLUMN state_version INTEGER NOT NULL DEFAULT 0")
            message_columns = {row["name"] for row in db.execute("PRAGMA table_info(chat_messages)").fetchall()}
            if "idempotency_key" not in message_columns:
                db.execute("ALTER TABLE chat_messages ADD COLUMN idempotency_key TEXT NULL")
            db.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_message_idempotency
                ON chat_messages(room_id, idempotency_key) WHERE idempotency_key IS NOT NULL""")

    def add_message(self, room_id: str, user_id: str, text: str, reply_to_message_id: int | None = None,
                    idempotency_key: str | None = None) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO chat_rooms(id, created_at, updated_at, state_version) VALUES(?,?,?,0)", (room_id, now, now))
            if idempotency_key:
                existing = db.execute(
                    "SELECT id FROM chat_messages WHERE room_id=? AND idempotency_key=?",
                    (room_id, idempotency_key),
                ).fetchone()
                if existing:
                    version = db.execute("SELECT state_version FROM chat_rooms WHERE id=?", (room_id,)).fetchone()[0]
                    return {"message_id": existing["id"], "created": False, "state_version": version}
            cursor = db.execute("""INSERT INTO chat_messages
                (room_id,user_id,text,reply_to_message_id,idempotency_key,created_at) VALUES(?,?,?,?,?,?)""",
                (room_id, user_id, text, reply_to_message_id, idempotency_key, now))
            db.execute("UPDATE chat_rooms SET updated_at=?, state_version=state_version+1 WHERE id=?", (now, room_id))
            version = db.execute("SELECT state_version FROM chat_rooms WHERE id=?", (room_id,)).fetchone()[0]
            return {"message_id": cursor.lastrowid, "created": True, "state_version": version}

    def state_version(self, room_id: str) -> int:
        with self.connect() as db:
            row = db.execute("SELECT state_version FROM chat_rooms WHERE id=?", (room_id,)).fetchone()
        return int(row[0]) if row else 0

    def preferences(self, room_id: str) -> list[Preference]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT preference_json FROM preference_snapshots WHERE room_id=? ORDER BY user_id", (room_id,)
            ).fetchall()
        return [Preference.model_validate_json(row["preference_json"]) for row in rows]

    def messages(self, room_id: str) -> list[ChatMessage]:
        with self.connect() as db:
            rows = db.execute("SELECT id,user_id,text,reply_to_message_id FROM chat_messages WHERE room_id=? ORDER BY id", (room_id,)).fetchall()
        return [ChatMessage(message_id=row["id"], user_id=row["user_id"], text=row["text"], reply_to_message_id=row["reply_to_message_id"]) for row in rows]

    def messages_after(self, room_id: str, message_id: int) -> list[ChatMessage]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT id,user_id,text,reply_to_message_id FROM chat_messages WHERE room_id=? AND id>? ORDER BY id",
                (room_id, message_id),
            ).fetchall()
        return [ChatMessage(message_id=row["id"], user_id=row["user_id"], text=row["text"], reply_to_message_id=row["reply_to_message_id"]) for row in rows]

    def context_messages(self, room_id: str, before_or_at: int, limit: int = 12) -> list[ChatMessage]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT id,user_id,text,reply_to_message_id FROM chat_messages WHERE room_id=? AND id<=? ORDER BY id DESC LIMIT ?",
                (room_id, before_or_at, limit),
            ).fetchall()
        return [ChatMessage(message_id=row["id"], user_id=row["user_id"], text=row["text"], reply_to_message_id=row["reply_to_message_id"]) for row in reversed(rows)]

    def analysis_checkpoint(self, room_id: str) -> int:
        with self.connect() as db:
            row = db.execute("SELECT last_message_id FROM chat_analysis_progress WHERE room_id=?", (room_id,)).fetchone()
        return int(row["last_message_id"]) if row else 0

    def save_analysis_checkpoint(self, room_id: str, message_id: int):
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as db:
            db.execute("""INSERT INTO chat_analysis_progress(room_id,last_message_id,updated_at) VALUES(?,?,?)
                ON CONFLICT(room_id) DO UPDATE SET last_message_id=excluded.last_message_id, updated_at=excluded.updated_at""",
                (room_id, message_id, now))

    def save_preferences(self, room_id: str, members: list[Preference]):
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as db:
            for member in members:
                db.execute("""INSERT INTO preference_snapshots(room_id,user_id,preference_json,updated_at) VALUES(?,?,?,?)
                    ON CONFLICT(room_id,user_id) DO UPDATE SET preference_json=excluded.preference_json, updated_at=excluded.updated_at""",
                    (room_id, member.user_id, member.model_dump_json(), now))

    def save_recommendations(self, room_id: str, round_id: str, recommendations):
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO chat_rooms(id, created_at, updated_at) VALUES(?,?,?)", (room_id, now, now))
            for rank, item in enumerate(recommendations, 1):
                db.execute("INSERT INTO recommendation_history(room_id,round_id,movie_id,movie_title,rank_no,group_score,created_at) VALUES(?,?,?,?,?,?,?)",
                           (room_id, round_id, item.movie.internal_id, item.movie.title, rank, item.group_score, now))

    def recommended_movie_ids(self, room_id: str) -> list[str]:
        with self.connect() as db:
            rows = db.execute("SELECT movie_id FROM recommendation_history WHERE room_id=? ORDER BY id", (room_id,)).fetchall()
        return list(dict.fromkeys(row["movie_id"] for row in rows))

    def recommendation_history_rows(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("""SELECT room_id,round_id,movie_id,movie_title,rank_no,group_score,created_at
                FROM recommendation_history ORDER BY id""").fetchall()
        return [dict(row) for row in rows]

    def save_recommendation_event(self, event: RecommendationEventCreate) -> RecommendationEvent:
        created_at = datetime.now(timezone.utc)
        with self.connect() as db:
            db.execute("""INSERT OR IGNORE INTO recommendation_events
                (event_id,room_id,round_id,user_id,movie_id,rank_no,event_type,model_version,payload,occurred_at,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (event.event_id, event.room_id, event.round_id, event.user_id, event.movie_id, event.rank_no,
                 event.event_type, event.model_version, json.dumps(event.payload, ensure_ascii=False),
                 event.occurred_at.isoformat(), created_at.isoformat()))
            row = db.execute("SELECT * FROM recommendation_events WHERE event_id=?", (event.event_id,)).fetchone()
        return RecommendationEvent(id=row["id"], event_id=row["event_id"], room_id=row["room_id"], round_id=row["round_id"],
            user_id=row["user_id"], movie_id=row["movie_id"], rank_no=row["rank_no"], event_type=row["event_type"],
            model_version=row["model_version"], payload=json.loads(row["payload"]), occurred_at=row["occurred_at"], created_at=row["created_at"])

    def recommendation_events(self, round_id: str | None = None) -> list[RecommendationEvent]:
        query = "SELECT * FROM recommendation_events" + (" WHERE round_id=?" if round_id else "") + " ORDER BY id"
        with self.connect() as db:
            rows = db.execute(query, (round_id,) if round_id else ()).fetchall()
        return [RecommendationEvent(id=row["id"], event_id=row["event_id"], room_id=row["room_id"], round_id=row["round_id"],
            user_id=row["user_id"], movie_id=row["movie_id"], rank_no=row["rank_no"], event_type=row["event_type"],
            model_version=row["model_version"], payload=json.loads(row["payload"]), occurred_at=row["occurred_at"], created_at=row["created_at"]) for row in rows]

    def reset_room(self, room_id: str):
        with self.connect() as db:
            db.execute("DELETE FROM recommendation_history WHERE room_id=?", (room_id,))
            db.execute("DELETE FROM recommendation_events WHERE room_id=?", (room_id,))
            db.execute("DELETE FROM preference_snapshots WHERE room_id=?", (room_id,))
            db.execute("DELETE FROM chat_messages WHERE room_id=?", (room_id,))
            db.execute("DELETE FROM chat_rooms WHERE id=?", (room_id,))


class MySQLMeetupDatabase:
    def __init__(self, host: str, port: int, database: str, user: str, password: str):
        import pymysql
        self.pymysql = pymysql
        self.options = {"host": host, "port": port, "database": database, "user": user, "password": password,
                        "charset": "utf8mb4", "cursorclass": pymysql.cursors.DictCursor, "autocommit": True}

    def connect(self):
        return self.pymysql.connect(**self.options)

    def add_message(self, room_id: str, user_id: str, text: str, reply_to_message_id: int | None = None,
                    idempotency_key: str | None = None) -> dict:
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute("""INSERT INTO chat_rooms(id,created_at,updated_at,state_version)
                VALUES(%s,NOW(),NOW(),0) ON DUPLICATE KEY UPDATE updated_at=updated_at""", (room_id,))
            if idempotency_key:
                cursor.execute("SELECT id FROM chat_messages WHERE room_id=%s AND idempotency_key=%s", (room_id, idempotency_key))
                existing = cursor.fetchone()
                if existing:
                    cursor.execute("SELECT state_version FROM chat_rooms WHERE id=%s", (room_id,))
                    return {"message_id": existing["id"], "created": False, "state_version": cursor.fetchone()["state_version"]}
            cursor.execute("""INSERT INTO chat_messages
                (room_id,user_id,text,reply_to_message_id,idempotency_key,created_at) VALUES(%s,%s,%s,%s,%s,NOW())""",
                (room_id, user_id, text, reply_to_message_id, idempotency_key))
            message_id = cursor.lastrowid
            cursor.execute("UPDATE chat_rooms SET updated_at=NOW(), state_version=state_version+1 WHERE id=%s", (room_id,))
            cursor.execute("SELECT state_version FROM chat_rooms WHERE id=%s", (room_id,))
            return {"message_id": message_id, "created": True, "state_version": cursor.fetchone()["state_version"]}

    def state_version(self, room_id: str) -> int:
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute("SELECT state_version FROM chat_rooms WHERE id=%s", (room_id,))
            row = cursor.fetchone()
        return int(row["state_version"]) if row else 0

    def preferences(self, room_id: str) -> list[Preference]:
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute("SELECT preference_json FROM preference_snapshots WHERE room_id=%s ORDER BY user_id", (room_id,))
            rows = cursor.fetchall()
        return [Preference.model_validate_json(row["preference_json"]) for row in rows]

    def messages(self, room_id: str) -> list[ChatMessage]:
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute("SELECT id,user_id,text,reply_to_message_id FROM chat_messages WHERE room_id=%s ORDER BY id", (room_id,))
            rows = cursor.fetchall()
        return [ChatMessage(message_id=row["id"], user_id=row["user_id"], text=row["text"], reply_to_message_id=row["reply_to_message_id"]) for row in rows]

    def messages_after(self, room_id: str, message_id: int) -> list[ChatMessage]:
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute("SELECT id,user_id,text,reply_to_message_id FROM chat_messages WHERE room_id=%s AND id>%s ORDER BY id", (room_id, message_id))
            rows = cursor.fetchall()
        return [ChatMessage(message_id=row["id"], user_id=row["user_id"], text=row["text"], reply_to_message_id=row["reply_to_message_id"]) for row in rows]

    def context_messages(self, room_id: str, before_or_at: int, limit: int = 12) -> list[ChatMessage]:
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute("SELECT id,user_id,text,reply_to_message_id FROM chat_messages WHERE room_id=%s AND id<=%s ORDER BY id DESC LIMIT %s", (room_id, before_or_at, limit))
            rows = list(reversed(cursor.fetchall()))
        return [ChatMessage(message_id=row["id"], user_id=row["user_id"], text=row["text"], reply_to_message_id=row["reply_to_message_id"]) for row in rows]

    def analysis_checkpoint(self, room_id: str) -> int:
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute("SELECT last_message_id FROM chat_analysis_progress WHERE room_id=%s", (room_id,))
            row = cursor.fetchone()
        return int(row["last_message_id"]) if row else 0

    def save_analysis_checkpoint(self, room_id: str, message_id: int):
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute("""INSERT INTO chat_analysis_progress(room_id,last_message_id,updated_at) VALUES(%s,%s,NOW())
                ON DUPLICATE KEY UPDATE last_message_id=VALUES(last_message_id), updated_at=NOW()""", (room_id, message_id))

    def save_preferences(self, room_id: str, members: list[Preference]):
        with self.connect() as db, db.cursor() as cursor:
            for member in members:
                cursor.execute("""INSERT INTO preference_snapshots(room_id,user_id,preference_json,updated_at) VALUES(%s,%s,%s,NOW())
                    ON DUPLICATE KEY UPDATE preference_json=VALUES(preference_json), updated_at=NOW()""",
                    (room_id, member.user_id, member.model_dump_json()))

    def save_recommendations(self, room_id: str, round_id: str, recommendations):
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute("INSERT INTO chat_rooms(id,created_at,updated_at) VALUES(%s,NOW(),NOW()) ON DUPLICATE KEY UPDATE updated_at=NOW()", (room_id,))
            for rank, item in enumerate(recommendations, 1):
                cursor.execute("INSERT INTO recommendation_history(room_id,round_id,movie_id,movie_title,rank_no,group_score,created_at) VALUES(%s,%s,%s,%s,%s,%s,NOW())",
                               (room_id, round_id, item.movie.internal_id, item.movie.title, rank, item.group_score))

    def recommended_movie_ids(self, room_id: str) -> list[str]:
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute("SELECT movie_id FROM recommendation_history WHERE room_id=%s ORDER BY id", (room_id,))
            rows = cursor.fetchall()
        return list(dict.fromkeys(row["movie_id"] for row in rows))

    def recommendation_history_rows(self) -> list[dict]:
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute("""SELECT room_id,round_id,movie_id,movie_title,rank_no,group_score,created_at
                FROM recommendation_history ORDER BY id""")
            return cursor.fetchall()

    def save_recommendation_event(self, event: RecommendationEventCreate) -> RecommendationEvent:
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute("""INSERT INTO recommendation_events
                (event_id,room_id,round_id,user_id,movie_id,rank_no,event_type,model_version,payload,occurred_at,created_at)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW()) ON DUPLICATE KEY UPDATE event_id=VALUES(event_id)""",
                (event.event_id, event.room_id, event.round_id, event.user_id, event.movie_id, event.rank_no,
                 event.event_type, event.model_version, json.dumps(event.payload, ensure_ascii=False), event.occurred_at))
            cursor.execute("SELECT * FROM recommendation_events WHERE event_id=%s", (event.event_id,)); row = cursor.fetchone()
        return RecommendationEvent(id=row["id"], event_id=row["event_id"], room_id=row["room_id"], round_id=row["round_id"],
            user_id=row["user_id"], movie_id=row["movie_id"], rank_no=row["rank_no"], event_type=row["event_type"],
            model_version=row["model_version"], payload=json.loads(row["payload"] or "{}"), occurred_at=row["occurred_at"], created_at=row["created_at"])

    def recommendation_events(self, round_id: str | None = None) -> list[RecommendationEvent]:
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute("SELECT * FROM recommendation_events" + (" WHERE round_id=%s" if round_id else "") + " ORDER BY id", (round_id,) if round_id else ())
            rows = cursor.fetchall()
        return [RecommendationEvent(id=row["id"], event_id=row["event_id"], room_id=row["room_id"], round_id=row["round_id"],
            user_id=row["user_id"], movie_id=row["movie_id"], rank_no=row["rank_no"], event_type=row["event_type"],
            model_version=row["model_version"], payload=json.loads(row["payload"] or "{}"), occurred_at=row["occurred_at"], created_at=row["created_at"]) for row in rows]

    def reset_room(self, room_id: str):
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute("DELETE FROM recommendation_history WHERE room_id=%s", (room_id,))
            cursor.execute("DELETE FROM recommendation_events WHERE room_id=%s", (room_id,))
            cursor.execute("DELETE FROM preference_snapshots WHERE room_id=%s", (room_id,))
            cursor.execute("DELETE FROM chat_messages WHERE room_id=%s", (room_id,))
            cursor.execute("DELETE FROM chat_rooms WHERE id=%s", (room_id,))
