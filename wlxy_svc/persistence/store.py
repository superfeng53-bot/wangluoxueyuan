"""SQLite WAL 持久层（B 型：无申请队列 / AI 缓存）。"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Optional

from wlxy_svc.config import DEFAULT_CONCURRENCY, MAX_CONCURRENCY, MIN_CONCURRENCY
from wlxy_svc.states import assert_account_transition, is_force_target

_SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS accounts (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    display_name      TEXT    NOT NULL DEFAULT '',
    username          TEXT    NOT NULL UNIQUE,
    password          TEXT    NOT NULL,
    requirements_json TEXT    NOT NULL DEFAULT '[]',
    target_years_json TEXT    NOT NULL DEFAULT '[]',
    extra_json        TEXT    NOT NULL DEFAULT '{}',
    status            TEXT    NOT NULL DEFAULT 'queued',
    status_msg        TEXT    NOT NULL DEFAULT '',
    retry_count       INTEGER NOT NULL DEFAULT 0,
    queued_at         REAL    NOT NULL DEFAULT 0,
    created_at        REAL    NOT NULL DEFAULT 0,
    updated_at        REAL    NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id  INTEGER NOT NULL,
    started_at  REAL    NOT NULL,
    ended_at    REAL    NOT NULL,
    result      TEXT    NOT NULL,
    summary     TEXT    NOT NULL DEFAULT '',
    logs_json   TEXT    NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_runs_account ON runs(account_id, id DESC);

CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class Store:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def startup_recovery(self) -> None:
        now = time.time()
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, status FROM accounts WHERE status IN ('running','retrying')",
            ).fetchall()
            for row in rows:
                assert_account_transition(row["status"], "queued", force=True)
            conn.execute(
                "UPDATE accounts SET status='queued', "
                "status_msg=CASE WHEN status='running' THEN 'startup recovery' ELSE status_msg END, "
                "updated_at=? WHERE status IN ('running','retrying')",
                (now,),
            )

    def create_account(
        self,
        display_name: str,
        username: str,
        password: str,
        requirements_json: str = "[]",
        target_years_json: str = "[]",
        extra_json: str = "{}",
    ) -> int:
        now = time.time()
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO accounts "
                "(display_name,username,password,requirements_json,target_years_json,"
                "extra_json,status,queued_at,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,'queued',?,?,?)",
                (
                    display_name,
                    username,
                    password,
                    requirements_json,
                    target_years_json,
                    extra_json,
                    now,
                    now,
                    now,
                ),
            )
            return cur.lastrowid

    def get_account(self, account_id: int) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
            return dict(row) if row else None

    def get_account_by_username(self, username: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM accounts WHERE username=?", (username,)).fetchone()
            return dict(row) if row else None

    @staticmethod
    def _accounts_filter_sql(
        status: str = "",
        search: str = "",
        date_from: float = 0,
        date_to: float = 0,
    ) -> tuple[str, list]:
        sql = ""
        params: list = []
        if status:
            sql += " AND status=?"
            params.append(status)
        if search:
            sql += " AND (display_name LIKE ? OR username LIKE ? OR status_msg LIKE ?)"
            params.extend([f"%{search}%"] * 3)
        if date_from > 0:
            sql += " AND created_at >= ?"
            params.append(date_from)
        if date_to > 0:
            sql += " AND created_at <= ?"
            params.append(date_to)
        return sql, params

    def count_accounts(
        self,
        status: str = "",
        search: str = "",
        date_from: float = 0,
        date_to: float = 0,
    ) -> int:
        where, params = self._accounts_filter_sql(status, search, date_from, date_to)
        with self._conn() as conn:
            row = conn.execute(
                f"SELECT COUNT(*) AS n FROM accounts WHERE 1=1{where}",
                params,
            ).fetchone()
            return int(row["n"] if row else 0)

    def list_accounts(
        self,
        status: str = "",
        search: str = "",
        limit: int = 50,
        offset: int = 0,
        date_from: float = 0,
        date_to: float = 0,
    ) -> list[dict]:
        where, params = self._accounts_filter_sql(status, search, date_from, date_to)
        sql = f"SELECT * FROM accounts WHERE 1=1{where} ORDER BY id ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with self._conn() as conn:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def count_by_status(self) -> dict[str, int]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) as n FROM accounts GROUP BY status",
            ).fetchall()
            counts = {r["status"]: r["n"] for r in rows}
            total = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
            counts["total"] = total
            return counts

    def update_account(self, account_id: int, **fields) -> None:
        if not fields:
            return
        fields["updated_at"] = time.time()
        set_clause = ", ".join(f"{k}=?" for k in fields)
        with self._conn() as conn:
            conn.execute(
                f"UPDATE accounts SET {set_clause} WHERE id=?",
                (*fields.values(), account_id),
            )

    def update_account_status(
        self,
        account_id: int,
        status: str,
        status_msg: str = "",
        retry_delta: int = 0,
        *,
        force: bool = False,
    ) -> None:
        account = self.get_account(account_id)
        if account:
            frm = account.get("status") or ""
            if frm != status and not (force or is_force_target(status)):
                assert_account_transition(frm, status)
        now = time.time()
        with self._conn() as conn:
            if retry_delta:
                conn.execute(
                    "UPDATE accounts SET status=?,status_msg=?,retry_count=retry_count+?,"
                    "updated_at=? WHERE id=?",
                    (status, status_msg, retry_delta, now, account_id),
                )
            else:
                conn.execute(
                    "UPDATE accounts SET status=?,status_msg=?,updated_at=? WHERE id=?",
                    (status, status_msg, now, account_id),
                )

    def update_extra(self, account_id: int, extra: dict) -> None:
        self.update_account(account_id, extra_json=json.dumps(extra, ensure_ascii=False))

    def delete_account(self, account_id: int) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM accounts WHERE id=?", (account_id,))
            conn.execute("DELETE FROM runs WHERE account_id=?", (account_id,))

    def claim_next_queued(self, now: float) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM accounts WHERE status='queued' "
                "AND queued_at <= ? ORDER BY queued_at ASC LIMIT 1",
                (now,),
            ).fetchone()
            if not row:
                return None
            cur = conn.execute(
                "UPDATE accounts SET status='running', updated_at=? "
                "WHERE id=? AND status='queued'",
                (now, row["id"]),
            )
            if cur.rowcount == 0:
                return None
            updated = conn.execute("SELECT * FROM accounts WHERE id=?", (row["id"],)).fetchone()
            return dict(updated) if updated else dict(row)

    def requeue_account(self, account_id: int, preserve_extra_keys: list[str] | None = None) -> None:
        now = time.time()
        account = self.get_account(account_id)
        if not account:
            return
        extra = json.loads(account.get("extra_json") or "{}")

        keep_keys = {"cookies", "user_profile", "card_no", "region", "report_mode"}
        if preserve_extra_keys:
            keep_keys.update(preserve_extra_keys)
        runtime_prefixes = ("_results", "phase", "failed_phase", "error_log", "year_status")
        new_extra = {
            k: v
            for k, v in extra.items()
            if k in keep_keys or not any(k.endswith(p) or k == p for p in runtime_prefixes)
        }
        for key in ("phase", "failed_phase", "error_log_text", "year_status", "current_year"):
            new_extra.pop(key, None)

        frm = account.get("status") or ""
        if frm != "queued":
            assert_account_transition(frm, "queued", force=True)

        with self._conn() as conn:
            conn.execute(
                "UPDATE accounts SET status='queued', status_msg='', retry_count=0, "
                "queued_at=?, updated_at=?, extra_json=? WHERE id=?",
                (now, now, json.dumps(new_extra, ensure_ascii=False), account_id),
            )
            conn.execute("DELETE FROM runs WHERE account_id=?", (account_id,))

    def top_account(self, account_id: int) -> None:
        now = time.time()
        self.update_account(account_id, queued_at=now, status="queued")

    def add_run(
        self,
        account_id: int,
        started_at: float,
        ended_at: float,
        result: str,
        summary: str = "",
        logs: list | None = None,
    ) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO runs (account_id,started_at,ended_at,result,summary,logs_json) "
                "VALUES (?,?,?,?,?,?)",
                (
                    account_id,
                    started_at,
                    ended_at,
                    result,
                    summary,
                    json.dumps(logs or [], ensure_ascii=False),
                ),
            )
            return cur.lastrowid

    def get_runs(self, account_id: int, limit: int = 20) -> list[dict]:
        with self._conn() as conn:
            return [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM runs WHERE account_id=? ORDER BY id DESC LIMIT ?",
                    (account_id, limit),
                ).fetchall()
            ]

    def kv_get(self, key: str, default: str = "") -> str:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
            return row["value"] if row else default

    def kv_set(self, key: str, value: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def is_paused(self) -> bool:
        return self.kv_get("scheduler.paused", "0") == "1"

    def set_paused(self, paused: bool) -> None:
        self.kv_set("scheduler.paused", "1" if paused else "0")

    def ensure_scheduler_defaults(self) -> None:
        if not self.kv_get("scheduler.concurrency_limit", ""):
            self.set_concurrency_limit(DEFAULT_CONCURRENCY)

    def get_concurrency_limit(self) -> int:
        raw = self.kv_get("scheduler.concurrency_limit", "")
        if not raw:
            return DEFAULT_CONCURRENCY
        return int(raw)

    def set_concurrency_limit(self, limit: int) -> None:
        clamped = max(MIN_CONCURRENCY, min(MAX_CONCURRENCY, int(limit)))
        self.kv_set("scheduler.concurrency_limit", str(clamped))
