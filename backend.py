import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from functools import lru_cache

DEFAULT_DB_PATH = os.getenv("QUIZFORMS_DB_PATH", "quizforms.db")


def _hash_secret(value):
    if not value:
        return None

    iterations = 210_000
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        value.encode("utf-8"),
        bytes.fromhex(salt),
        iterations,
    ).hex()

    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def _verify_secret(value, encoded):
    if not value or not encoded:
        return False

    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)

        if algorithm != "pbkdf2_sha256":
            legacy = hashlib.sha256(value.encode("utf-8")).hexdigest()
            return hmac.compare_digest(legacy, encoded)

        digest = hashlib.pbkdf2_hmac(
            "sha256",
            value.encode("utf-8"),
            bytes.fromhex(salt),
            int(iterations),
        ).hex()

        return hmac.compare_digest(digest, expected)

    except ValueError:
        legacy = hashlib.sha256(value.encode("utf-8")).hexdigest()
        return hmac.compare_digest(legacy, encoded)


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _supabase_credentials():
    url = os.getenv("SUPABASE_URL")
    key = (
        os.getenv("SUPABASE_SECRET_KEY")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    )

    if url and key:
        return url, key

    try:
        import streamlit as st

        if "supabase" in st.secrets:
            section = st.secrets["supabase"]
            url = section.get("url")
            key = (
                section.get("secret_key")
                or section.get("service_role_key")
            )
            if url and key:
                return str(url), str(key)
    except Exception:
        pass

    return None, None


def storage_mode():
    url, key = _supabase_credentials()
    return "supabase" if url and key else "sqlite"


@lru_cache(maxsize=1)
def _supabase():
    url, key = _supabase_credentials()
    if not url or not key:
        return None

    from supabase import create_client
    return create_client(url, key)


def _sqlite_connect():
    return sqlite3.connect(DEFAULT_DB_PATH, check_same_thread=False)


def _sqlite_columns(cur, table):
    rows = cur.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def _init_sqlite():
    con = _sqlite_connect()
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS quizzes (
            code TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            questions_json TEXT NOT NULL,
            admin_pin_hash TEXT,
            access_password_hash TEXT,
            settings_json TEXT,
            created_at TEXT NOT NULL
        )
    """)

    columns = _sqlite_columns(cur, "quizzes")

    if "admin_pin_hash" not in columns:
        cur.execute(
            "ALTER TABLE quizzes ADD COLUMN admin_pin_hash TEXT"
        )
    if "access_password_hash" not in columns:
        cur.execute(
            "ALTER TABLE quizzes ADD COLUMN access_password_hash TEXT"
        )
    if "settings_json" not in columns:
        cur.execute(
            "ALTER TABLE quizzes ADD COLUMN settings_json TEXT"
        )

    cur.execute("""
        CREATE TABLE IF NOT EXISTS attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quiz_code TEXT NOT NULL,
            student_name TEXT NOT NULL,
            answers_json TEXT NOT NULL,
            details_json TEXT NOT NULL,
            correct INTEGER,
            total INTEGER,
            score REAL,
            created_at TEXT NOT NULL
        )
    """)

    con.commit()
    con.close()


def init_storage():
    if storage_mode() == "sqlite":
        _init_sqlite()


def create_quiz(
    code,
    title,
    questions,
    admin_pin,
    access_password=None,
    settings=None,
):
    payload = {
        "code": code,
        "title": title,
        "questions": questions,
        "admin_pin_hash": _hash_secret(admin_pin),
        "access_password_hash": (
            _hash_secret(access_password) if access_password else None
        ),
        "settings": settings or {},
        "created_at": _now_iso(),
    }

    if storage_mode() == "supabase":
        _supabase().table("quizzes").insert(payload).execute()
        return

    con = _sqlite_connect()
    cur = con.cursor()

    cur.execute("""
        INSERT INTO quizzes (
            code,
            title,
            questions_json,
            admin_pin_hash,
            access_password_hash,
            settings_json,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        payload["code"],
        payload["title"],
        json.dumps(payload["questions"], ensure_ascii=False),
        payload["admin_pin_hash"],
        payload["access_password_hash"],
        json.dumps(payload["settings"], ensure_ascii=False),
        payload["created_at"],
    ))

    con.commit()
    con.close()


def get_quiz(code):
    if storage_mode() == "supabase":
        response = (
            _supabase()
            .table("quizzes")
            .select("code,title,questions,settings,created_at")
            .eq("code", code)
            .limit(1)
            .execute()
        )

        if not response.data:
            return None

        row = response.data[0]
        questions = row.get("questions") or []

        for idx, q in enumerate(questions, start=1):
            q.setdefault("qid", str(idx))
            q.setdefault("points", 1)

        return {
            "code": row["code"],
            "title": row["title"],
            "questions": questions,
            "settings": row.get("settings") or {},
            "created_at": row.get("created_at"),
        }

    con = _sqlite_connect()
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    row = cur.execute(
        "SELECT * FROM quizzes WHERE code = ?",
        (code,),
    ).fetchone()
    con.close()

    if not row:
        return None

    questions = json.loads(row["questions_json"])

    for idx, q in enumerate(questions, start=1):
        q.setdefault("qid", str(idx))
        q.setdefault("points", 1)

    return {
        "code": row["code"],
        "title": row["title"],
        "questions": questions,
        "settings": (
            json.loads(row["settings_json"])
            if row["settings_json"]
            else {}
        ),
        "created_at": row["created_at"],
    }


def update_quiz_settings(code, settings):
    if storage_mode() == "supabase":
        (
            _supabase()
            .table("quizzes")
            .update({"settings": settings})
            .eq("code", code)
            .execute()
        )
        return

    con = _sqlite_connect()
    cur = con.cursor()
    cur.execute(
        "UPDATE quizzes SET settings_json = ? WHERE code = ?",
        (json.dumps(settings, ensure_ascii=False), code),
    )
    con.commit()
    con.close()


def _get_quiz_secret_hash(code, column):
    if column not in {"admin_pin_hash", "access_password_hash"}:
        raise ValueError("Columna inválida.")

    if storage_mode() == "supabase":
        response = (
            _supabase()
            .table("quizzes")
            .select(column)
            .eq("code", code)
            .limit(1)
            .execute()
        )

        if not response.data:
            return None

        return response.data[0].get(column)

    con = _sqlite_connect()
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    row = cur.execute(
        f"SELECT {column} FROM quizzes WHERE code = ?",
        (code,),
    ).fetchone()
    con.close()

    return row[column] if row else None


def verify_admin_pin(code, pin):
    return _verify_secret(
        pin,
        _get_quiz_secret_hash(code, "admin_pin_hash"),
    )


def verify_access_password(code, password):
    encoded = _get_quiz_secret_hash(
        code,
        "access_password_hash",
    )
    if not encoded:
        return True

    return _verify_secret(password, encoded)


def save_attempt(
    quiz_code,
    student_name,
    answers,
    correct,
    total,
    score,
    details,
):
    payload = {
        "quiz_code": quiz_code,
        "student_name": student_name,
        "answers": answers,
        "details": details,
        "correct": correct,
        "total": total,
        "score": score,
        "created_at": _now_iso(),
    }

    if storage_mode() == "supabase":
        _supabase().table("attempts").insert(payload).execute()
        return

    con = _sqlite_connect()
    cur = con.cursor()

    cur.execute("""
        INSERT INTO attempts (
            quiz_code,
            student_name,
            answers_json,
            details_json,
            correct,
            total,
            score,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        quiz_code,
        student_name,
        json.dumps(answers, ensure_ascii=False),
        json.dumps(details, ensure_ascii=False),
        correct,
        total,
        score,
        payload["created_at"],
    ))

    con.commit()
    con.close()


def update_attempt_grading(
    attempt_id,
    details,
    correct,
    total,
    score,
):
    if storage_mode() == "supabase":
        (
            _supabase()
            .table("attempts")
            .update({
                "details": details,
                "correct": correct,
                "total": total,
                "score": score,
            })
            .eq("id", attempt_id)
            .execute()
        )
        return

    con = _sqlite_connect()
    cur = con.cursor()

    cur.execute("""
        UPDATE attempts
        SET details_json = ?,
            correct = ?,
            total = ?,
            score = ?
        WHERE id = ?
    """, (
        json.dumps(details, ensure_ascii=False),
        correct,
        total,
        score,
        attempt_id,
    ))

    con.commit()
    con.close()


def _upgrade_old_details(details):
    for detail in details:
        detail.setdefault("max_points", 1)

        if "awarded_points" not in detail:
            if detail.get("is_correct") is True:
                detail["awarded_points"] = float(
                    detail.get("max_points", 1)
                )
            elif detail.get("is_correct") is False:
                detail["awarded_points"] = 0.0
            else:
                detail["awarded_points"] = None

    return details


def get_attempts(quiz_code):
    if storage_mode() == "supabase":
        response = (
            _supabase()
            .table("attempts")
            .select("*")
            .eq("quiz_code", quiz_code)
            .order("id", desc=True)
            .execute()
        )

        rows = response.data or []

        for row in rows:
            row["details"] = _upgrade_old_details(
                row.get("details", [])
            )

        return rows

    con = _sqlite_connect()
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    rows = cur.execute("""
        SELECT *
        FROM attempts
        WHERE quiz_code = ?
        ORDER BY id DESC
    """, (quiz_code,)).fetchall()

    con.close()
    result = []

    for row in rows:
        result.append({
            "id": row["id"],
            "quiz_code": row["quiz_code"],
            "student_name": row["student_name"],
            "answers": json.loads(row["answers_json"]),
            "details": _upgrade_old_details(
                json.loads(row["details_json"])
            ),
            "correct": row["correct"],
            "total": row["total"],
            "score": row["score"],
            "created_at": row["created_at"],
        })

    return result


def attempt_exists(quiz_code, student_name):
    target = student_name.strip().casefold()

    for attempt in get_attempts(quiz_code):
        if (
            str(attempt.get("student_name", ""))
            .strip()
            .casefold()
            == target
        ):
            return True

    return False


def storage_healthcheck():
    """Comprueba la base configurada sin revelar credenciales."""
    try:
        if storage_mode() == "supabase":
            (
                _supabase()
                .table("quizzes")
                .select("code")
                .limit(1)
                .execute()
            )
            return True, "Supabase responde correctamente."

        con = _sqlite_connect()
        cur = con.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        con.close()
        return True, "SQLite local responde correctamente."
    except Exception as exc:
        return (
            False,
            f"No pude conectar con la base de datos: {type(exc).__name__}: {exc}",
        )
