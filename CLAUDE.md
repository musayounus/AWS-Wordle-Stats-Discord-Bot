# Wordle Discord Leaderboard Bot

Discord bot that tracks Wordle scores, streaks, crowns, and leaderboards for a server. Scores are parsed from messages and stored in PostgreSQL on AWS RDS.

## Tech Stack

- **Language:** Python 3.9
- **Bot framework:** discord.py (commands + app_commands for slash commands)
- **Database:** PostgreSQL 17 on AWS RDS, accessed via `asyncpg` connection pool
- **Secrets:** AWS Secrets Manager via `boto3`
- **Hosting:** AWS EC2 (systemd service), single-instance guard via `psutil` PID check

## Project Structure

```
bot.py              — Entry point. Creates bot, initializes DB pool, loads cogs, syncs slash commands
config.py           — All env-based configuration (Discord tokens, AWS/RDS settings, intents)
aws/secrets.py      — Fetches RDS credentials from AWS Secrets Manager
db/pool.py          — Creates asyncpg connection pool with SSL
db/queries.py       — NOTE: currently a duplicate of utils/parsing.py (see Known Issues)
utils/parsing.py    — Core message parsing: parse_wordle_message(), parse_summary_message(), calculate_streak()
utils/leaderboard.py— Generates leaderboard Discord embeds with ranking queries
cogs/               — discord.py Cog extensions, one per feature domain
```

## Cogs Overview

| Cog | Slash Commands | Purpose |
|-----|---------------|---------|
| `events` | (none — listeners) | Routes on_message to parsers, handles edits and errors |
| `leaderboard` | `/leaderboard`, `/stats` | Leaderboard display and personal stats |
| `streaks` | `/streak`, `/streaks` | Individual and top-10 streak tracking |
| `crowns` | `/crowns` | Crown (first-place) leaderboard |
| `uncontended_crowns` | `/uncontended` | Solo first-place crown leaderboard |
| `fails` | `/fails_leaderboard`, `/set_fails` | X/6 fail tracking |
| `predictions` | (daily task) | Auto-posts daily score predictions |
| `admin` | `/reset_leaderboard`, `/ban_user`, `/unban_user`, `/remove_scores`, `/import`, `/set_uncontended_crowns`, `/adjust_crowns` | Admin-only data management |
| `banned_users` | `/banned_users` | Lists banned users |
| `help` | `/help` | Command reference embed |

## Database Tables

- `scores` — Main table. UNIQUE on (username, wordle_number). `attempts` is NULL for X/6 fails.
- `fails` — Dedicated fail tracking. UNIQUE on (user_id, wordle_number).
- `crowns` — Records when a user placed first on a given Wordle.
- `uncontended_crowns` — Counter table for solo first-place finishes. UNIQUE on user_id.
- `banned_users` — Banned user list. UNIQUE on user_id.

## Running

```bash
pip install -r requirements.txt
# Requires .env with: DISCORD_BOT_TOKEN, RDS_SECRET_ARN, RDS_HOST (+ optional overrides in config.py)
python bot.py
```

On EC2 production: managed by `wordle-bot.service` systemd unit.

## Workflow

- Commit work to Git regularly with clean, descriptive commit messages. Push to GitHub after each commit so progress is never lost.
- Do not batch up large amounts of changes — commit after completing each logical unit of work (a bug fix, a new feature, a refactor, etc.).
- Do not include "Co-Authored-By" lines in commit messages.

## Known Issues

- `db/queries.py` is a duplicate of `utils/parsing.py` — the `get_user_stats_for_predictions` function imported by `cogs/predictions.py:5` does not exist, so the predictions cog will fail at runtime.

## Additional Documentation

- [Architectural Patterns](.claude/docs/architectural_patterns.md) — Cog structure, DB access patterns, message parsing conventions
