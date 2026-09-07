-- Vektra Open - initial schema (single shared Postgres database)
--
-- You normally do NOT need to run this by hand: the bot runs the same
-- CREATE TABLE IF NOT EXISTS statements on startup. This file exists for
-- people who prefer a manual migration or want the schema visible up front.
--
--   psql "<DATABASE_URL>" -f db/migrations/001_initial.sql
--
-- Postgres 12+ works (Neon, Supabase, self-hosted).

begin;

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

commit;
