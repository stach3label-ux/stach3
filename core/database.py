"""Vektra Open - single shared Postgres database layer.

One DATABASE_URL serves every guild; guild_id columns keep servers apart.
The schema is created automatically at startup (ensure_schema) and also ships
as db/migrations/001_initial.sql for people who prefer a manual migration.

Every function opens its own short connection. On a managed Postgres
(Neon/Supabase) this is exactly what the pooler is for.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

from core.config import DATABASE_URL, DB_TIMEOUT_SECONDS, TICKET_CODE_ALPHABET

logger = logging.getLogger("vektra-open.database")

# ── schema ───────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
create table if not exists guild_config (
    guild_id          bigint primary key,
    staff_channel_id  bigint,
    ticket_channel_id bigint,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now()
);

create table if not exists submissions (
    id               bigint generated always as identity primary key,
    guild_id         bigint not null,
    ticket_code      text not null,
    artist_id        bigint,
    artist_name      text not null,
    artist_username  text,
    track_name       text not null,
    artists          text not null default '',
    demo_link        text not null,
    message          text not null default '',
    status           text not null default 'In Queue',
    reason           text,
    spam_flagged     boolean not null default false,
    staff_thread_id  bigint,
    created_at       timestamptz not null default now(),
    decided_at       timestamptz,
    unique (guild_id, ticket_code)
);

create table if not exists tickets (
    id          bigint generated always as identity primary key,
    guild_id    bigint not null,
    ticket_code text not null,
    user_id     bigint,
    username    text,
    subject     text not null,
    body        text not null default '',
    status      text not null default 'Open',
    thread_id   bigint,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    resolved_at timestamptz,
    unique (guild_id, ticket_code)
);

create index if not exists submissions_guild_status_idx on submissions (guild_id, status);
create index if not exists submissions_guild_artist_idx on submissions (guild_id, artist_id);
create index if not exists tickets_guild_status_idx on tickets (guild_id, status);
create index if not exists tickets_user_open_idx on tickets (user_id) where status <> 'Resolved';
"""


def _connect():
    return psycopg.connect(
        DATABASE_URL,
        connect_timeout=DB_TIMEOUT_SECONDS,
        row_factory=dict_row,
    )


def ensure_schema() -> None:
    """Create tables/indexes if missing. Safe to call on every startup."""
    if not DATABASE_URL:
        logger.warning("DATABASE_URL is not set - skipping schema setup.")
        return
    with _connect() as conn:
        conn.execute(SCHEMA_SQL)
    logger.info("Database schema is ready.")


def _new_code(guild_id: int, table: str) -> str:
    """Generate a unique human-friendly code for a guild (e.g. H7K2M9)."""
    with _connect() as conn:
        for _ in range(8):
            code = "".join(secrets.choice(TICKET_CODE_ALPHABET) for _ in range(6))
            row = conn.execute(
                f"select 1 from {table} where guild_id = %s and ticket_code = %s",
                (guild_id, code),
            ).fetchone()
            if not row:
                return code
    raise RuntimeError("Could not generate a unique ticket code.")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── guild config ─────────────────────────────────────────────────────────────

def get_guild_config(guild_id: int) -> dict:
    """Row for a guild (never None once ensure_schema ran, but guard anyway)."""
    if not guild_id:
        return {}
    with _connect() as conn:
        row = conn.execute(
            "select guild_id, staff_channel_id, ticket_channel_id from guild_config where guild_id = %s",
            (guild_id,),
        ).fetchone()
    return row or {}


def _upsert_guild(guild_id: int, **fields) -> None:
    now = _now()
    with _connect() as conn:
        conn.execute(
            """
            insert into guild_config (guild_id, created_at, updated_at)
            values (%s, %s, %s)
            on conflict (guild_id) do nothing
            """,
            (guild_id, now, now),
        )
        if fields:
            sets = ", ".join(f"{key} = %s" for key in fields)
            conn.execute(
                f"update guild_config set {sets}, updated_at = %s where guild_id = %s",
                (*fields.values(), now, guild_id),
            )


def set_staff_channel(guild_id: int, channel_id: int | None) -> None:
    _upsert_guild(guild_id, staff_channel_id=channel_id)


def set_ticket_channel(guild_id: int, channel_id: int | None) -> None:
    _upsert_guild(guild_id, ticket_channel_id=channel_id)


def get_staff_channel_id(guild_id: int) -> int | None:
    return get_guild_config(guild_id).get("staff_channel_id")


def get_ticket_channel_id(guild_id: int) -> int | None:
    return get_guild_config(guild_id).get("ticket_channel_id")


# ── submissions ──────────────────────────────────────────────────────────────

def create_submission(
    guild_id: int,
    *,
    artist_id: int | None,
    artist_name: str,
    artist_username: str,
    track_name: str,
    artists: str,
    demo_link: str,
    message: str,
    spam_flagged: bool = False,
) -> dict:
    last_error: Exception | None = None
    for _ in range(3):
        code = _new_code(guild_id, "submissions")
        try:
            with _connect() as conn:
                row = conn.execute(
                    """
                    insert into submissions (
                        guild_id, ticket_code, artist_id, artist_name, artist_username,
                        track_name, artists, demo_link, message, status, spam_flagged
                    )
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'In Queue', %s)
                    returning *
                    """,
                    (
                        guild_id, code, artist_id, artist_name, artist_username,
                        track_name, artists, demo_link, message, spam_flagged,
                    ),
                ).fetchone()
            return row
        except psycopg.errors.UniqueViolation:
            continue  # extremely unlikely code collision - just pick another
        except Exception as exc:
            last_error = exc
            break
    if last_error:
        raise last_error
    return {}


def fetch_submission(guild_id: int, code: str) -> dict | None:
    code = code.strip().upper()
    with _connect() as conn:
        return conn.execute(
            "select * from submissions where guild_id = %s and ticket_code = %s",
            (guild_id, code),
        ).fetchone()


def list_submissions(
    guild_id: int,
    *,
    status: str | None = None,
    artist_id: int | None = None,
    limit: int = 10,
    offset: int = 0,
) -> list[dict]:
    clauses = ["guild_id = %s"]
    params: list = [guild_id]
    if status:
        clauses.append("status = %s")
        params.append(status)
    if artist_id:
        clauses.append("artist_id = %s")
        params.append(artist_id)
    params.extend([limit, offset])
    with _connect() as conn:
        rows = conn.execute(
            f"""
            select * from submissions
            where {' and '.join(clauses)}
            order by created_at desc
            limit %s offset %s
            """,
            params,
        ).fetchall()
    return rows


def count_submissions(guild_id: int, *, status: str | None = None, artist_id: int | None = None) -> int:
    clauses = ["guild_id = %s"]
    params: list = [guild_id]
    if status:
        clauses.append("status = %s")
        params.append(status)
    if artist_id:
        clauses.append("artist_id = %s")
        params.append(artist_id)
    with _connect() as conn:
        row = conn.execute(
            f"select count(*) as n from submissions where {' and '.join(clauses)}",
            params,
        ).fetchone()
    return int(row["n"]) if row else 0


def artist_stats(guild_id: int, artist_id: int) -> dict:
    with _connect() as conn:
        rows = conn.execute(
            """
            select status, count(*) as n
            from submissions
            where guild_id = %s and artist_id = %s
            group by status
            """,
            (guild_id, artist_id),
        ).fetchall()
    counts = {row["status"]: int(row["n"]) for row in rows}
    total = sum(counts.values())
    return {
        "total": total,
        "approved": counts.get("Approved", 0),
        "rejected": counts.get("Rejected", 0),
        "in_queue": counts.get("In Queue", 0),
    }


def duplicate_demo(guild_id: int, demo_link: str) -> dict | None:
    """Return an earlier live submission for the same demo link, if any."""
    with _connect() as conn:
        return conn.execute(
            """
            select * from submissions
            where guild_id = %s and demo_link = %s and status <> 'Rejected'
            order by created_at asc
            limit 1
            """,
            (guild_id, demo_link),
        ).fetchone()


def set_submission_thread(guild_id: int, code: str, thread_id: int | None) -> None:
    with _connect() as conn:
        conn.execute(
            "update submissions set staff_thread_id = %s where guild_id = %s and ticket_code = %s",
            (thread_id, guild_id, code.strip().upper()),
        )


def decide_submission(
    guild_id: int,
    code: str,
    status: str,
    *,
    reason: str | None = None,
) -> bool:
    now = _now()
    with _connect() as conn:
        cur = conn.execute(
            """
            update submissions
            set status = %s, reason = %s, decided_at = %s
            where guild_id = %s and ticket_code = %s
            """,
            (status, reason, now, guild_id, code.strip().upper()),
        )
        return cur.rowcount > 0


def guild_totals(guild_id: int) -> dict:
    with _connect() as conn:
        rows = conn.execute(
            "select status, count(*) as n from submissions where guild_id = %s group by status",
            (guild_id,),
        ).fetchall()
    return {row["status"]: int(row["n"]) for row in rows}


# ── support tickets ──────────────────────────────────────────────────────────

def create_ticket(guild_id: int, *, user_id: int | None, username: str, subject: str, body: str) -> dict:
    last_error: Exception | None = None
    for _ in range(3):
        code = _new_code(guild_id, "tickets")
        try:
            with _connect() as conn:
                row = conn.execute(
                    """
                    insert into tickets (guild_id, ticket_code, user_id, username, subject, body, status)
                    values (%s, %s, %s, %s, %s, %s, 'Open')
                    returning *
                    """,
                    (guild_id, code, user_id, username, subject, body),
                ).fetchone()
            return row
        except psycopg.errors.UniqueViolation:
            continue
        except Exception as exc:
            last_error = exc
            break
    if last_error:
        raise last_error
    return {}


def fetch_ticket(guild_id: int, code: str) -> dict | None:
    code = code.strip().upper()
    with _connect() as conn:
        return conn.execute(
            "select * from tickets where guild_id = %s and ticket_code = %s",
            (guild_id, code),
        ).fetchone()


def list_tickets(guild_id: int, *, status: str | None = None, limit: int = 15) -> list[dict]:
    clauses = ["guild_id = %s"]
    params: list = [guild_id]
    if status:
        clauses.append("status = %s")
        params.append(status)
    params.append(limit)
    with _connect() as conn:
        rows = conn.execute(
            f"""
            select * from tickets
            where {' and '.join(clauses)}
            order by updated_at desc
            limit %s
            """,
            params,
        ).fetchall()
    return rows


def set_ticket_status(guild_id: int, code: str, status: str) -> bool:
    now = _now()
    resolved_at = now if status == "Resolved" else None
    with _connect() as conn:
        cur = conn.execute(
            """
            update tickets
            set status = %s, updated_at = %s, resolved_at = %s
            where guild_id = %s and ticket_code = %s
            """,
            (status, now, resolved_at, guild_id, code.strip().upper()),
        )
        return cur.rowcount > 0


def set_ticket_thread(guild_id: int, code: str, thread_id: int | None) -> None:
    with _connect() as conn:
        conn.execute(
            "update tickets set thread_id = %s where guild_id = %s and ticket_code = %s",
            (thread_id, guild_id, code.strip().upper()),
        )


def open_ticket_for_dm(user_id: int) -> dict | None:
    """Most recently updated unresolved ticket belonging to a user (DM bridge)."""
    with _connect() as conn:
        return conn.execute(
            """
            select * from tickets
            where user_id = %s and status <> 'Resolved'
            order by updated_at desc
            limit 1
            """,
            (user_id,),
        ).fetchone()
