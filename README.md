# 🟩 Wordle Discord Leaderboard Bot

A production Discord bot that turns a server's daily Wordle habit into a living leaderboard — with streaks, crowns, stats, and admin tools — backed by PostgreSQL on AWS and monitored end‑to‑end.

![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python&logoColor=white)
![discord.py](https://img.shields.io/badge/discord.py-app__commands-5865F2?logo=discord&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-4169E1?logo=postgresql&logoColor=white)
![asyncpg](https://img.shields.io/badge/asyncpg-SSL%20pool-336791)
![AWS](https://img.shields.io/badge/AWS-EC2%20%7C%20RDS%20%7C%20Secrets%20%7C%20CloudWatch-FF9900?logo=amazonaws&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green.svg)

The bot silently watches a Discord channel and captures every Wordle result that lands there — whether it's a pasted `Wordle 1418 4/6` grid, an official Wordle app `/share` embed, or the daily group summary — then serves up real‑time slash commands for rankings, head‑to‑head stats, streaks, and crown counts. It runs 24/7 as a systemd service on EC2, pulls database credentials from AWS Secrets Manager at boot, and pages me through SNS when anything looks off.

---

## ✨ Engineering highlights

A few decisions that went beyond the happy path:

- **Three parser pipelines, one source of truth.** The bot ingests three wildly different message shapes — plain text, Discord **Components V2** embeds from the Wordle app (where `message.content` is empty and text is buried inside a nested `Container → Section → TextDisplay` tree), and the bot‑posted daily summary with multi‑user lines and crown markers — and normalizes them all into the same row in the `scores` table. See `utils/parsing.py`.
- **Defense in depth on ingest.** Every path that reads `wordle_number` from user‑submitted text (`parse_wordle_message` and the `/import` manual branch) runs it through `validate_wordle_number` before touching the DB — no more future‑dated garbage rows poisoning streaks.
- **Streak anchoring.** `calculate_streak` only counts a streak as *current* if the user solved today or yesterday, so a 30‑day‑old stale streak can't sit on the top‑10 leaderboard forever.
- **Fail‑aware averaging.** `X/6` fails are stored as `attempts = NULL` but counted as a `FAIL_PENALTY = 7` in every AVG query — so skipping days hurts your rank instead of hiding from it.
- **Uncontended‑crown auto‑sync.** When an admin adds or removes a crown for a Wordle, `sync_uncontended_for_wordle` reruns the "exactly one winner?" test for *just that Wordle* and rewrites the `uncontended_crowns` row in the same transaction. No background job, no drift.
- **Secrets never touch the repo or the environment.** The EC2 instance role grants `secretsmanager:GetSecretValue`; boto3 pulls the RDS password from Secrets Manager at startup. No secret lives in `.env` or Git history.
- **Single‑instance guard.** `psutil` scans the process table on boot and aborts if another `bot.py` is already running — cheap insurance against double‑ingest during a sloppy deploy.
- **External uptime signal.** A 5‑minute heartbeat line (`flush=True`) ships to CloudWatch Logs via the agent; a CloudWatch alarm fires on log silence and SNS emails me.

---

## 🎯 Features

**For players**
- 🏆 Real‑time leaderboard — all‑time, last 7 days, or this month
- 📊 Personal `/stats` — best, average, fails, games played, current streak
- 🔥 Streak tracking — individual and top‑10
- 👑 Crown leaderboard — first‑place finishes on the daily summary
- 🥇 Uncontended crown leaderboard — days you were the *only* first‑place finisher
- 💀 Fails leaderboard — because bragging rights cut both ways
- 🎉 Automatic "beat your personal best" and "1/6 — did you cheat?" announcements

**For admins**
- 🛠️ Fine‑grained score / fail / crown correction commands, each with cascading DB fixes
- 📥 `/import` — scan the whole channel's history and backfill every Wordle result it finds
- 🚫 Ban / unban users from appearing in stats and leaderboards
- ♻️ Full leaderboard reset (with a "type `yes` to confirm" guard)

---

## 💬 Slash commands

### Public

| Command | What it does |
|---|---|
| `/leaderboard [range]` | Top 10 by avg attempts; `range` is `week`, `month`, or empty for all‑time. Shows your own rank below the top 10 if you fell off. |
| `/stats [user]` | Best, avg, fails, games played, current streak, last played. Defaults to yourself. |
| `/streak` | Your current Wordle streak. |
| `/streaks` | Top 10 current streaks. |
| `/crowns` | Crown (👑) counts, all users. |
| `/uncontended` | Solo first‑place (🥇) counts, top 10. |
| `/fails_leaderboard` | Most `X/6` fails, top 10. |
| `/banned_users` | Anyone can see who's banned. |
| `/help` | In‑Discord command reference. |

### Admin (`administrator` permission required)

| Command | What it does |
|---|---|
| `/import` | Walks channel history, parses every Wordle score + summary + crown, reports a summary with any rejected out‑of‑range numbers. |
| `/reset_leaderboard` | Wipes `scores`, `fails`, `crowns`, `uncontended_crowns`. Requires typing `yes` within 30s. |
| `/add_scores user wordle_number attempts [crown]` | Set a user's score (1–6 or X). Optional `crown` flag also awards the crown and re‑syncs uncontended. |
| `/remove_scores user wordle_number` | Delete the score, the fail row, the crown — re‑syncs uncontended. |
| `/add_fails user wordle_number` | Mark as X/6 in both `scores` and `fails`. |
| `/remove_fails user wordle_number` | Unmark X/6. |
| `/add_crowns user wordle_number` | Award a 👑; re‑syncs uncontended for that Wordle. |
| `/remove_crowns user wordle_number` | Remove a 👑; re‑syncs uncontended for that Wordle. |
| `/ban_user user` | Hide a user from stats/leaderboard (writes still land but queries filter them out). |
| `/unban_user user` | Reverse a ban. |

---

## 📥 Accepted score formats

The parser routes incoming messages through three branches (see `cogs/events.py`):

1. **Daily group summary** (posted by the Wordle integration bot):
   ```
   Here are yesterday's results:
   👑 2/6: Alice
   4/6: Bob, Charlie
   X/6: Dave
   ```
2. **Wordle app `/share`** — a Components V2 embed authored by the Wordle bot; the invoking user is recovered from `interaction_metadata`.
3. **Manual text paste** — `Wordle 1418 3/6` — accepted from *admins only* (to prevent a bad actor from spam‑submitting scores for other people).

Edits are re‑processed via `on_message_edit`, so fixing a typo in a pasted grid updates the DB.

---

## 🏗️ Architecture

```mermaid
flowchart LR
    subgraph Discord
        U[Players] --> CH[Server channel]
    end
    subgraph AWS[AWS &mdash; eu-central-1]
        subgraph VPC[VPC]
            EC2[EC2<br/>wordle-bot.service<br/>Python 3.12] -->|SSL + VPC private subnet| RDS[(RDS PostgreSQL 17)]
        end
        EC2 -->|boto3, IAM role| SM[Secrets Manager]
        EC2 -->|CloudWatch agent| CWL[CloudWatch Logs]
        CWL --> AL[CloudWatch Alarms]
        AL --> SNS[SNS → email]
        RDSE[RDS Event Subscription] --> SNS
    end
    CH <-.discord.py gateway.-> EC2
```

### Flow on a new score

1. Player posts a Wordle grid in Discord.
2. Gateway event hits the bot's `on_message` listener.
3. `cogs/events.py` routes it to the right parser based on message shape.
4. `utils/parsing.py` extracts `wordle_number` + `attempts`, validates, checks the ban list, upserts into `scores` (and `fails` if X/6), and clears stale fail rows on a successful re‑submit.
5. If the attempt beats the user's previous best, the bot posts a celebratory message.
6. After a daily summary, the bot auto‑posts a fresh leaderboard embed.

---

## ☁️ AWS infrastructure

Everything runs in **eu‑central‑1** (Frankfurt), with billing alerts in **us‑east‑1**.

### Compute — EC2
- Amazon Linux, single instance running `bot.py` under `wordle-bot.service` (systemd)
- Auto‑restart on failure, journald → file (`/var/log/wordle-bot/bot.log`) → CloudWatch Logs via the CloudWatch agent
- `psutil` PID scan at boot aborts duplicate runs

### Database — RDS PostgreSQL 17
- `PubliclyAccessible: false` — private IP only
- Security group allows inbound `5432` from exactly two sources: the bot's EC2 security group and the Secrets Manager rotation Lambda's security group. No `0.0.0.0/0`.
- Automatic daily backups; connection pool held on `bot.pg_pool` (1–5 connections, `ssl="require"`, `db/pool.py`)

### Secrets — Secrets Manager
- RDS username/password stored as a JSON secret
- EC2 instance role has `secretsmanager:GetSecretValue` for that ARN only
- `aws/secrets.py` fetches them at bot boot — never cached to disk, never read from `.env`
- VPC interface endpoint for Secrets Manager so the call stays inside AWS's backbone

### IAM
- Least‑privilege EC2 instance role: Secrets Manager read, CloudWatch logs/metrics write
- No long‑lived IAM user, no static access keys

### Networking — VPC
- Both EC2 and RDS live inside the VPC
- RDS in a private subnet with no internet route
- EC2's security group allows only SSH (from a locked CIDR) and Discord gateway egress

### Observability — CloudWatch + SNS

| Alarm | Triggers on |
|---|---|
| `wordle-ec2-status-check-failed` | EC2 system/instance health check failure |
| `wordle-ec2-high-cpu` | EC2 CPU > 80% for 5 min |
| `wordle-ec2-auto-recover` | System status failure → auto‑recover action |
| `wordle-rds-high-cpu` | RDS CPU > 80% |
| `wordle-rds-low-storage` | RDS free storage < 2 GB |
| `wordle-rds-high-connections` | RDS connections > 20 |
| `wordle-bot-no-logs` | No log line for 10 min (heartbeat gap = the bot is down) |
| `wordle-billing-exceeds-10` (us‑east‑1) | Monthly estimated charges > $10 |

All alarms publish to the `wordle-bot-alerts` SNS topic; the RDS event subscription (`wordle-rds-events`) also publishes to it for availability / maintenance / failure events. Email subscription → me.

### Cost
- Runs within AWS free tier bounds; cost‑optimized pass in April 2026 brought ongoing spend to ~$8/mo by releasing an unused Elastic IP and trimming a multi‑AZ Secrets Manager VPC endpoint to one AZ.

---

## 🗄️ Database schema

```sql
-- One row per (user, wordle). attempts IS NULL ⇒ the user failed that day (X/6).
CREATE TABLE scores (
  id             SERIAL PRIMARY KEY,
  user_id        BIGINT,
  username       TEXT    NOT NULL,
  wordle_number  INTEGER NOT NULL,
  date           DATE    NOT NULL,
  attempts       INTEGER,
  UNIQUE (username, wordle_number)
);

-- Dedicated fail ledger. Redundant with scores.attempts IS NULL but makes
-- /fails_leaderboard a trivial count and keeps fails addressable by user_id
-- when usernames change.
CREATE TABLE fails (
  id             SERIAL PRIMARY KEY,
  user_id        BIGINT  NOT NULL,
  username       TEXT    NOT NULL,
  wordle_number  INTEGER NOT NULL,
  date           DATE    NOT NULL,
  UNIQUE (user_id, wordle_number)
);

-- Every time a user placed first on a given daily summary.
CREATE TABLE crowns (
  id             SERIAL PRIMARY KEY,
  user_id        BIGINT  NOT NULL,
  username       TEXT    NOT NULL,
  wordle_number  INTEGER NOT NULL,
  date           DATE    NOT NULL
);

-- Mirror of crowns, filtered to Wordles where exactly ONE user placed first.
-- Kept in sync by sync_uncontended_for_wordle() in utils/admin_helpers.py.
CREATE TABLE uncontended_crowns (
  id             SERIAL PRIMARY KEY,
  user_id        BIGINT  NOT NULL,
  username       TEXT    NOT NULL,
  wordle_number  INTEGER NOT NULL,
  date           DATE    NOT NULL,
  UNIQUE (user_id, wordle_number)
);

CREATE TABLE banned_users (
  user_id   BIGINT PRIMARY KEY,
  username  TEXT NOT NULL
);
```

Every INSERT uses `ON CONFLICT … DO NOTHING` or `DO UPDATE` so parsers are idempotent — reprocessing the same message (or an edit) never duplicates a row.

---

## 📁 Project layout

```
bot.py                    # Entry point: single-instance guard, pool init, cog loader, heartbeat
config.py                 # Env-driven config (Discord, AWS, RDS, intents)
requirements.txt

aws/
  secrets.py              # boto3 → Secrets Manager → (username, password)

db/
  pool.py                 # asyncpg.create_pool with SSL, 1–5 connections

utils/
  parsing.py              # parse_wordle_message, parse_summary_message, calculate_streak,
                          # Components V2 tree walker (extract_message_text)
  admin_helpers.py        # wordle_number ↔ date, validate_wordle_number, sync_uncontended
  leaderboard.py          # generate_leaderboard_embed + FAIL_PENALTY constant
  user_resolver.py        # @mention / plain-name → user_id resolution

cogs/
  events.py               # on_message / on_message_edit / on_command_error
  leaderboard.py          # /leaderboard, /stats
  streaks.py              # /streak, /streaks
  crowns.py               # /crowns
  uncontended_crowns.py   # /uncontended
  fails.py                # /fails_leaderboard, /add_fails, /remove_fails
  admin.py                # /reset_leaderboard, /ban_user, /unban_user,
                          # /add_scores, /remove_scores, /import,
                          # /add_crowns, /remove_crowns
  banned_users.py         # /banned_users
  help.py                 # /help
```

---

## 🛠️ Running it locally

Requires Python 3.12, a Discord bot token, and an AWS account (for Secrets Manager + RDS) or a local PostgreSQL if you prefer to bypass AWS for dev.

```bash
git clone https://github.com/<you>/wordle.git
cd wordle

python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

Create a `.env` file (already git‑ignored):

```env
DISCORD_BOT_TOKEN=...
TEST_GUILD_ID=123456789012345678       # for fast slash-command sync in dev
AWS_REGION=eu-central-1
RDS_SECRET_ARN=arn:aws:secretsmanager:...
RDS_HOST=your-db.xxxxxx.eu-central-1.rds.amazonaws.com
RDS_DBNAME=postgres
RDS_PORT=5432
```

```bash
python bot.py
```

You should see:

```
✅ Database pool initialized.
✅ Loaded cog: cogs.admin
...
✅ Slash commands synced.
✅ Logged in as YourBot (ID: ...)
💓 Heartbeat: bot is alive
```

---

## 🚀 Production deployment

Deployed as a systemd service on EC2. Standard flow:

```bash
# On the EC2 box
cd ~/wordle
git pull
sudo systemctl restart wordle-bot.service

# Tail logs
sudo journalctl -u wordle-bot.service -f

# Or from the CloudWatch side:
# Log group: /wordle-bot/application (30-day retention)
```

The systemd unit runs `python3.12 -u bot.py`, redirects stdout/stderr to `/var/log/wordle-bot/bot.log`, and the CloudWatch agent ships that file to the `/wordle-bot/application` log group.

---

## 📜 License

MIT — see [LICENSE](LICENSE).

---

## 🙏 Acknowledgments

[discord.py](https://github.com/Rapptz/discord.py) · [asyncpg](https://github.com/MagicStack/asyncpg) · [boto3](https://github.com/boto/boto3) · AWS · Wordle by The New York Times.
