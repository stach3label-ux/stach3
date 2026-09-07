<div align="center">

# 🎧 Vektra Open

**The free, self-hosted A&R demo-intake & support bot for Discord labels.**

Collect demos → review them with your team → decide — all inside Discord.
No dashboards, no subscriptions, no credit card.

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![discord.py](https://img.shields.io/badge/discord.py-2.3%2B-5865F2)](https://discordpy.readthedocs.io/)
[![Postgres](https://img.shields.io/badge/database-Postgres-336791)](https://www.postgresql.org/)
[![Hosting](https://img.shields.io/badge/free%20host-justrunmy.app-FF6F00)](https://justrunmy.app)

**Runs on a ~150 MB free VPS.** Connects to Neon, Supabase, or your own Postgres.
One bot token. One Python process. No other services to babysit.

</div>

---

## ✨ What it does

- **🎵 Demo intake** — artists hit `/submit` (or a "Submit a Demo" button), fill a small form, and their track lands as a **review card** in your private staff channel — with its own staff discussion thread.
- **⚖️ Team decisions** — `Approve`, `Reject` (with a reason), or `DM` right from the card. The artist is notified by Discord DM instantly.
- **🎟️ Support tickets** — members open a ticket from a button, staff get a card + thread, and *members can reply by just DMing the bot* — replies appear in the thread.
- **🧑‍🎤 Artist self-service** — `/my_submissions` and `/my_stats` so artists can check where they stand.
- **🧹 Staff tooling** — `/queue`, `/recent`, and `/submission` for a clean overview, all ephemeral (nobody else sees them).
- **🧠 Optional AI spam screening** — flag suspicious submissions with one AI key (Groq / OpenAI / SambaNova).
- **🎶 Optional music** — `/play` a track via your own Lavalink node.

```mermaid
flowchart LR
    A[Artist] -->|/submit| B[(Postgres)]
    B --> C[Staff review card + thread]
    C -->|Approve| D[✅ Artist DM]
    C -->|Reject| E[Reason + ❌ Artist DM]
    C -->|DM| F[💬 Artist DM]
    D & E & F --> G[Decision logged in thread]
    M[Member] -->|Ticket button| H[Staff ticket card + thread]
    H -->|Staff replies| I[Member DMs bot]
    I -.->|forwarded| H
```

> [!NOTE]
> Vektra Open is the **free, open-source edition** of [Vektra](https://github.com/Dap69420/labelutils) — a full product with hosted dashboards, Pro tiers, white-label identity, AI audio critique and more. This repo keeps the core that a label actually needs, small enough for a free VPS. MIT licensed — take it, run it, fork it.

---

## 🚀 Setup in 4 steps

### 1 · Create the Discord bot

1. Open the [Discord Developer Portal](https://discord.com/developers/applications) → **New Application**.
2. **Bot** tab → **Reset Token** → copy the token.
3. Under **Privileged Gateway Intents**, enable **MESSAGE CONTENT INTENT** (this powers the DM-reply bridge).
4. **OAuth2 → URL Generator** → scopes `bot` + `applications.commands` → permissions:

   `Send Messages` · `Embed Links` · `Create Public Threads` · `Send Messages in Threads` · `Manage Threads` · `Read Message History` · `Use Slash Commands`

5. Open the generated invite URL and add the bot to your server.

### 2 · Grab a free Postgres URL

Pick whichever you already use — all three work:

| Provider | Connection string pattern | Free tier? |
|---|---|---|
| **Neon** | `postgres://user:pass@ep-xxx.region.aws.neon.tech/dbname?sslmode=require` | ✅ |
| **Supabase** | `postgres://postgres.xxxx@aws-0-xx.pooler.supabase.com:6543/postgres?sslmode=require` | ✅ |
| **Self-hosted** | `postgres://user:pass@your-host:5432/dbname` | ✅ |

> Tables are created **automatically on first run** — no migration step needed (a `db/migrations/001_initial.sql` is included if you'd rather run it yourself).

### 3 · Deploy on a free host

Pick a home for the bot. The recommended, zero-config option:

<details>
<summary><b>☁️ justrunmy.app — recommended (free tier: 0.25 GB RAM, fits perfectly)</b></summary>

1. Sign up at [justrunmy.app](https://justrunmy.app) and create an **app** (Python).
2. Clone this repo and push it to the app via **Git** (or zip-upload the files).
3. Set these environment variables in the dashboard:

   ```env
   DISCORD_BOT_TOKEN=your_token
   DATABASE_URL=postgres://user:pass@host:5432/dbname?sslmode=require
   ```

4. Add a start command: `python bot.py` (or `sh -c "pip install -r requirements.txt && python bot.py"` if the platform doesn't auto-install).

The free tier (~0.15 vCPU / 0.25 GB RAM / auto-restart / logs) is more than enough — this bot idles around 60–90 MB.

</details>

**Other free options** (limits and terms change — always check the provider's current page):

| Host | Free allowance | Persistent 24/7? | Notes |
|---|---|---|---|
| **[justrunmy.app](https://justrunmy.app)** ⭐ | 0.25 GB RAM, 1 app | ✅ | Simplest for this bot; auto-restart + logs |
| **[Oracle Cloud — Always Free](https://www.oracle.com/cloud/free/)** | up to 4 vCPU / 24 GB RAM (ARM) | ✅ | The heavy hitter — a real free VPS; signup asks for a card |
| **[Google Cloud free tier](https://cloud.google.com/free)** | `e2-micro` (1 GB RAM) | ✅ | Always-free VM in 3 US regions; card required; ~10 min to set up a VM |
| **[AWS Free Tier](https://aws.amazon.com/free/)** | `t3.micro` (1 GB RAM) | ✅ (12 months) | Free for the first 12 months |
| **[Railway](https://railway.app/)** / **[Render](https://render.com/)** | small monthly trial / free 512 MB | ⚠️ sleeps on inactivity | Works, but free services sleep — bad for a Discord gateway. Use only as a temporary test |
| **Raspberry Pi / old PC at home** | whatever you own | ✅ | The original free host 🙂 |

> [!TIP]
> Whichever host you pick, the whole setup is identical: `python bot.py` + two environment variables. The bot has **no hard dependency on any platform**.

### 4 · First-run setup inside Discord

```text
/setup_staff #staff-reviews        ← private channel where submission cards appear
/setup_ticket_channel #tickets     ← private channel where support tickets appear
/status                            ← sanity check: channels + counts
```

Then **post the panels** where your community can see them:

```text
/post_submit_panel #submissions    ← artists click "Submit a Demo"
/ticket_panel #support             ← members click "Open a Ticket"
```

That's it — you're live. 🎉

---

## 🧭 Environment variables

```bash
# copy the template and fill it in — never commit this file
cp .env.example .env
```

| Variable | Required | Description |
|---|---|---|
| `DISCORD_BOT_TOKEN` | ✅ | From the Developer Portal |
| `DATABASE_URL` | ✅ | Any Postgres URI (Neon / Supabase / self-hosted) |
| `PORT` | – | HTTP port (default `7860`) |
| `HEALTH_HOST` | – | `0.0.0.0` = public, `127.0.0.1` = local only (default `0.0.0.0`) |
| `CHECKOUT_RECEIPT_SECRET` | – | Optional secret for the `/receipt` endpoint |
| `LAVALINK_HOST/PORT/PASSWORD/SSL` | – | Enable music (leave `LAVALINK_PASSWORD` empty to disable) |
| `SAMBANOVA_API_KEY` / `GROQ_API_KEY` / `OPENAI_API_KEY` | – | Enable AI spam screening (any one) |

---

## 🎮 Commands

| Artists | Staff | Admins |
|---|---|---|
| `/submit` — send a demo | `/queue` — newest queued demos | `/setup_staff` |
| `/my_submissions` — your tickets | `/recent` — latest activity | `/setup_ticket_channel` |
| `/my_stats` — acceptance rate | `/submission <code>` — full detail | `/post_submit_panel` |
| | `/tickets` — support ticket list | `/ticket_panel` |
| | `/ticket_set <code> <status>` | `/status` |

**Staff** = server owner or anyone with *Administrator* / *Manage Server*.
**Music** (optional): `/play` `/skip` `/stop` `/pause` `/music_queue` `/nowplaying` `/volume` `/leave`.

---

## 🧰 Under the hood

```
vektra-open/
├── bot.py                    entry point — bot + slash sync + HTTP server + auto schema
├── core/
│   ├── config.py             every env variable, in one place
│   ├── database.py           single-DB layer (guild_id separates servers) + CREATE TABLE IF NOT EXISTS
│   ├── ui.py                 review cards, decision buttons, modals, ticket views
│   └── moderation.py         optional AI spam screening
├── cogs/                     admin · submissions · tickets · music
├── utils/helpers.py          text formatting helpers
├── db/migrations/            optional manual migration
├── .env.example
└── requirements.txt
```

**Why it fits a 150 MB VPS**

- One Python process. No worker queues, no Redis, no bundled databases.
- Music talks to a **separate** Lavalink node — never install it on the bot's box.
- Every guild shares one Postgres; rows are separated by `guild_id`.
- AI screening only makes network calls when you configure a key.

**HTTP endpoints** (`PORT`, default 7860)

| Path | Purpose |
|---|---|
| `GET /health` | Plain-text heartbeat for uptime monitors |
| `GET /callback?token=…` | Completion-callback stub (log + acknowledge — extend to your own flow) |
| `GET /receipt?order_ref=…&secret=…` | Receipt endpoint stub for checkout sites (guarded by `CHECKOUT_RECEIPT_SECRET`) |

---

## ❓ FAQ

<details>
<summary><b>Will it really run on a 150 MB / 0.25 GB free tier?</b></summary>

Yes. Python + discord.py idles around **60–90 MB**. Just don't run Lavalink, Redis or Postgres on the same box — keep those elsewhere and this bot is comfortable.
</details>

<details>
<summary><b>Can multiple servers use the same bot + database?</b></summary>

Yes — data is separated by `guild_id`. Each server runs `/setup_staff` and `/setup_ticket_channel` for its own channels.
</details>

<details>
<summary><b>How do artists reply to staff?</b></summary>

**Tickets**: members DM the bot and replies are forwarded into the staff thread. **Submissions**: staff DM artists from the card; decisions notify artists automatically by DM.
</details>

<details>
<summary><b>My bot shows commands but nothing works — what did I miss?</b></summary>

Most common causes: the **Message Content Intent** is off, the bot lacks **Create Public Threads** in the staff channel, or `DATABASE_URL` is unreachable (check `/status` and the host logs).
</details>

<details>
<summary><b>Do I have to run the SQL migration?</b></summary>

No — `core/database.py` runs `CREATE TABLE IF NOT EXISTS` on startup. The `.sql` file exists for people who prefer explicit migrations.
</details>

---

## 🔒 Security notes

- `.env` is gitignored — **never commit your token or DB credentials**.
- Use `sslmode=require` with managed Postgres.
- Expose `PORT` only to what needs it; protect `/receipt` with `CHECKOUT_RECEIPT_SECRET` if it's public.
- If AI screening is on, submission text is sent to the provider you chose — make sure that's acceptable for your label.

---

<div align="center">

**Made for labels, collectives & A&R teams.**  
Questions? Open an [issue](../../issues) · Contributions welcome · MIT licensed

</div>
