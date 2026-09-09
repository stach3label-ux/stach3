<div align="center">

# 🎧 Vektra Open

**The free, self-hosted A&R demo-intake & support bot for Discord labels.**

Collect demos → review them with your team → decide — all inside Discord.
Now with a **built-in AI assistant** that can run your label for you.
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

## 🆕 What's new in this update

- **🤖 Built-in AI MCP server** — set one password (`MCP_PASSWORD`) and connect Claude
  Desktop, claude.ai, Cursor or any MCP client straight to your bot. The AI can review
  demos, manage tickets, and **create custom slash commands that go live instantly** —
  no extra process, no dashboard, nothing to install. Connect via a simple password —
  no Discord login, no server picker.
- **🛠️ AI-authored custom commands** — ask your AI for a command ("make one that gives
  the Verified role") and it's live in seconds. Full power: moderation, roles,
  announcements, webhooks. The AI is the only reviewer and refuses only genuinely
  serious requests; every action still respects Discord's own permissions at runtime.
- **🎚️ `MUSIC_ENABLED` master switch** — `False` and music commands never exist and
  Lavalink is never touched. `True` without a Lavalink node? The bot runs fine and
  music commands simply say *"Lavalink is not configured"*.
- **🔒 Single-server lock** — the bot now permanently binds to the first server that
  invites it and leaves any other server. The open edition is for one label; running
  it commercially/multi-server requires a proper fork.

---

## ✨ What it does

- **🎵 Demo intake** — artists hit `/submit` (or a "Submit a Demo" button), fill a small form, and their track lands as a **review card** in your private staff channel — with its own staff discussion thread.
- **⚖️ Team decisions** — `Approve`, `Reject` (with a reason), or `DM` right from the card. The artist is notified by Discord DM instantly. **Your AI assistant can do the same through MCP.**
- **🎟️ Support tickets** — members open a ticket from a button, staff get a card + thread, and *members can reply by just DMing the bot* — replies appear in the thread.
- **🧑‍🎤 Artist self-service** — `/my_submissions` and `/my_stats` so artists can check where they stand.
- **🧹 Staff tooling** — `/queue`, `/recent`, and `/submission` for a clean overview, all ephemeral (nobody else sees them).
- **🧠 Optional AI spam screening** — flag suspicious submissions with one AI key (Groq / OpenAI / SambaNova).
- **🎶 Optional music** — `/play` a track via your own Lavalink node (master switch: `MUSIC_ENABLED`).
- **🤖 AI MCP server** — Claude/any MCP client connects with one password: review demos, manage tickets, **create live custom slash commands**.

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
    AI[🤖 AI assistant] -->|MCP: decide · tickets · make commands| B
```

> [!NOTE]
> Vektra Open is the **free, open-source edition** of [Vektra](https://vektra.games) — a full product with hosted dashboards, Pro tiers, white-label identity, AI audio critique and more. This repo keeps the core that a label actually needs, small enough for a free VPS. MIT licensed — take it, run it, fork it.

---

## 🚀 Setup in 4 steps

### 1 · Create the Discord bot

1. Open the [Discord Developer Portal](https://discord.com/developers/applications) → **New Application**.
2. **Bot** tab → **Reset Token** → copy the token.
3. Under **Privileged Gateway Intents**, enable **MESSAGE CONTENT INTENT** (this powers the DM-reply bridge).
4. **OAuth2 → URL Generator** → scopes `bot` + `applications.commands` → permissions:

   `Send Messages` · `Embed Links` · `Create Public Threads` · `Send Messages in Threads` · `Manage Threads` · `Read Message History` · `Use Slash Commands`

   > Using custom commands with **moderation** actions (kick/ban/timeout)? Also add
   > `Kick Members` · `Ban Members` · `Moderate Members` — the bot still refuses to act
   > on anyone the command caller couldn't act on themselves.

5. Open the generated invite URL and add the bot to your server. **This server becomes
   the bot's permanent home** (single-server lock — see below).

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
| `MUSIC_ENABLED` | – | Master music switch. `False`/`0` → music commands are **never registered** and Lavalink is never touched (default `True`) |
| `LAVALINK_HOST/PORT/PASSWORD/SSL` | – | Music with `MUSIC_ENABLED=True`. Password missing or node unreachable → commands reply *"Lavalink is not configured"* |
| `GUILD_ID` | – | Pin the single server this bot serves (otherwise the **first** server to invite it claims it) |
| `MCP_PASSWORD` | – | Enables the **AI MCP server** — the password AI assistants enter to connect. Empty = MCP disabled |
| `CHECKOUT_RECEIPT_SECRET` | – | Optional secret for the `/receipt` endpoint |
| `SAMBANOVA_API_KEY` / `GROQ_API_KEY` / `OPENAI_API_KEY` | – | Enable AI spam screening (any one) |

---

## 🤖 AI assistant (MCP) — connect Claude to your label

Set `MCP_PASSWORD=your-secret` and the bot serves a **Model Context Protocol** endpoint
from its own HTTP server. No extra process, no Node, nothing to install.

### Connect in 3 steps

1. In your AI client, **add a custom connector**:

   | Client | Where | URL |
   |---|---|---|
   | **Claude Desktop / claude.ai** | Settings → Connectors → *Add custom connector* | `http://<your-bot-host>:7860/mcp` |
   | **Cursor** | Settings → MCP → Add server | same URL |
   | **Any MCP client** | point it at the URL + OAuth discovery | same URL |

2. A Vektra Open page opens asking for the **MCP password** — that's the whole auth
   flow. No Discord login, no server selection (the bot is single-server anyway).
3. Done — the connector is authorized with a proper OAuth token (PKCE, auto-refresh,
   revocable). Tell the AI things like *"show me the queued demos"* or *"make a /verified
   command that gives people the Verified role"*.

> **https note:** some clients require https for non-localhost URLs. Put a tiny TLS
> proxy in front (see the [FAQ](#-faq)) — config only, no code change.

### What the AI can do

| Tool | Action |
|---|---|
| `list_submissions` / `get_submission` | Browse and read demo submissions |
| `decide_submission` | **Approve/reject** — the artist gets the same DM as a staff decision, the staff thread is updated |
| `list_tickets` / `set_ticket_status` | Read and update support tickets |
| `create_command` | **Create or update a custom slash command — live immediately** |
| `list_commands` / `get_command` | Inspect commands + usage stats |
| `set_command_enabled` / `delete_command` | Disable or remove commands |

### AI-made custom commands — how they work

Ask your assistant for any command and it drafts a **declarative manifest** (never code —
the interpreter is a strict sandbox). The command goes **live on your server within
seconds**. There is **no approval queue**: the AI itself is the reviewer and refuses only
genuinely serious requests (illegal activity, Discord-ToS breakers, credential/password
harvesting, phishing, prize-bait scams). Everything else — including powerful moderation,
role management, announcements and webhooks — is fair game.

Example manifest the AI might write for *"a /vibecheck command that picks one of three
answers"*:

```json
{
  "name": "vibecheck",
  "description": "Get your vibe checked",
  "parameters": [],
  "response": { "content": "🎧 {result.pick.pick}", "ephemeral": false },
  "actions": [
    { "type": "random_pick", "input": "Certified vibe ✅ | Mid 😐 | Unemployed behavior 💀", "store_as": "pick" }
  ],
  "rate_limit": { "max_uses_per_user_hour": 5 }
}
```

**Supported actions:** `text_reply` · `lookup_submission` · `my_submissions` ·
`random_pick` · `show_link` · `give_role` · `remove_role` · `kick_member` · `ban_member` ·
`timeout_member` · `announce` · `webhook_post`

**Safety model (no restrictions from us — Discord enforces the rest):**

- Commands are data, not code. The interpreter only knows the actions above; arbitrary
  code can never run.
- **Every role/moderation action is checked against the Discord permissions of whoever
  runs the command.** A `/kick` command made by the AI still requires the *caller* to have
  Kick Members — the bot never elevates anyone, and role hierarchy is respected.
- Placeholders like `{param.x}` and `{result.alias.field}` are the only templating;
  `store_as` lets actions feed each other.
- Per-user rate limits (1–30/hour) keep spam commands in check.
- Revoke an AI connection any time: delete its tokens (`mcp_oauth_tokens` table) or just
  change `MCP_PASSWORD` and restart.

---

## 🔒 Single-server lock

Vektra Open is the **free, open-source edition for one label**. The first server that
invites the bot becomes its **permanent home** (stored in the database); any other server
it gets invited to is left automatically with a log line. Set `GUILD_ID` to pin a
specific server instead.

> Want it multi-server or commercial? Fork and replace `core/single_server.py` — it's
> one small file on purpose.

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
**Music** (optional, `MUSIC_ENABLED=True`): `/play` `/skip` `/stop` `/pause` `/music_queue` `/nowplaying` `/volume` `/leave`.
**Custom commands** (via the AI MCP): your own slash commands — whatever you and the AI dream up.

---

## 🧰 Under the hood

```
vektra-open/
├── bot.py                    entry point — bot + slash sync + HTTP server + auto schema
├── core/
│   ├── config.py             every env variable, in one place
│   ├── database.py           DB layer + CREATE TABLE IF NOT EXISTS (commands, usage, MCP tokens)
│   ├── ui.py                 review cards, decision buttons, modals, ticket views
│   ├── single_server.py      one-server lock (fork to run multi-server)
│   └── moderation.py         optional AI spam screening
├── mcp/                      built-in AI MCP server
│   ├── common.py             token lifecycle, PKCE, OAuth pages
│   ├── http_api.py           routing: /mcp + /oauth/* + /.well-known
│   └── tools.py              the 10 AI tools + manifest validation
├── cogs/
│   ├── admin.py · submissions.py · tickets.py · music.py
│   └── custom_commands.py    interprets AI-made commands (sandboxed, permission-gated)
├── utils/helpers.py          text formatting helpers
├── db/migrations/            optional manual migration
├── .env.example
└── requirements.txt
```

**Why it fits a 150 MB VPS**

- One Python process. No worker queues, no Redis, no bundled databases. The MCP server
  lives inside the bot's existing HTTP server — zero extra processes.
- Music talks to a **separate** Lavalink node — never install it on the bot's box.
- One Postgres database. This edition is **single-server** (see the lock above).
- AI screening and the MCP server only make network calls when you configure them.

**HTTP endpoints** (`PORT`, default 7860)

| Path | Purpose |
|---|---|
| `GET /health` | Plain-text heartbeat for uptime monitors |
| `GET /callback?token=…` | Completion-callback stub (log + acknowledge — extend to your own flow) |
| `GET /receipt?order_ref=…&secret=…` | Receipt endpoint stub for checkout sites (guarded by `CHECKOUT_RECEIPT_SECRET`) |
| `POST /mcp` | **AI MCP JSON-RPC endpoint** (Bearer token required) |
| `GET/POST /oauth/authorize` | MCP connector authorize page (asks for `MCP_PASSWORD`) |
| `POST /oauth/token` · `/oauth/revoke` | MCP token issuance (PKCE + refresh rotation) / revocation |
| `GET /.well-known/oauth-authorization-server` | RFC 8414 metadata so MCP clients auto-discover the flow |

---

## ❓ FAQ

<details>
<summary><b>Will it really run on a 150 MB / 0.25 GB free tier?</b></summary>

Yes. Python + discord.py idles around **60–90 MB**. Just don't run Lavalink, Redis or Postgres on the same box — keep those elsewhere and this bot is comfortable.
</details>

<details>
<summary><b>Can multiple servers use the same bot?</b></summary>

No — this edition is **single-server on purpose**: the first server to invite the bot claims it forever, and any other server is left automatically (pin one with `GUILD_ID`). The open edition isn't meant for commercial/multi-tenant use; fork and replace <code>core/single_server.py</code> if you need that.
</details>

<details>
<summary><b>My AI client refuses the http:// connector URL. What do I do?</b></summary>

Some clients require https for remote connectors. Put a tiny Caddy reverse proxy in front:

```
mcp.yourdomain.com {
    reverse_proxy localhost:7860
}
```

Then use `https://mcp.yourdomain.com/mcp` as the connector URL. Config only — no code change.
</details>

<details>
<summary><b>How do artists reply to staff?</b></summary>

**Tickets**: members DM the bot and replies are forwarded into the staff thread. **Submissions**: staff DM artists from the card; decisions (staff or AI) notify artists automatically by DM.
</details>

<details>
<summary><b>Is it safe to let an AI create commands?</b></summary>

The AI can only assemble commands from a fixed set of building-block actions — it can never run code. Moderation and role actions are **always checked against the Discord permissions of the person invoking the command**, and role hierarchy applies, so an AI-made `/ban` is exactly as powerful as a staff-made `/ban`: nothing is elevated. If you ever feel uneasy, change `MCP_PASSWORD` (kills the tokens) and disable the command from Discord or the `custom_commands` table.
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

- `.env` is gitignored — **never commit your token, DB credentials, or `MCP_PASSWORD`**.
- Use `sslmode=require` with managed Postgres.
- `MCP_PASSWORD` is the key to your whole label through the AI — make it long and unique.
- MCP tokens are stored **hashed**, auto-expire (access 4 h, refresh 30 d, rotated on every refresh), and are revocable by changing the password.
- Expose `PORT` only to what needs it; protect `/receipt` with `CHECKOUT_RECEIPT_SECRET` if it's public. Prefer https via a reverse proxy for the MCP endpoint.
- If AI screening is on, submission text is sent to the provider you chose — make sure that's acceptable for your label.

---

<div align="center">

**Made for labels, collectives & A&R teams.**  
Questions? Open an [issue](../../issues) · Contributions welcome · MIT licensed

</div>
