# Architectural Patterns

## 1. Cog-per-Feature Organization

Each feature is a discord.py `Cog` in its own file under `cogs/`. Every cog follows the same structure:

- Class inherits `commands.Cog`, takes `bot` in `__init__` and stores it as `self.bot`
- Slash commands use `@app_commands.command()` decorators
- Admin commands are gated with `@app_commands.checks.has_permissions(administrator=True)`
- Module-level `async def setup(bot)` calls `bot.add_cog()`

Reference: any file in `cogs/` — e.g., `cogs/crowns.py:5-10`, `cogs/admin.py:8-10`

## 2. Database Access via bot.pg_pool

The bot stores an `asyncpg` connection pool on `bot.pg_pool` (created in `bot.py:41`). All database access follows this pattern:

```python
async with self.bot.pg_pool.acquire() as conn:
    await conn.execute(...)  # or conn.fetch(), conn.fetchrow(), conn.fetchval()
```

- Pool is created once in `setup_hook` (`bot.py:39-42`)
- Every cog and utility accesses it via `bot.pg_pool` or receives a `conn` parameter
- SSL is required for all connections (`db/pool.py:14`)
- Pool is sized 1-5 connections (`db/pool.py:15-16`)

## 3. Upsert with ON CONFLICT

All score/crown/fail inserts use PostgreSQL `ON CONFLICT` clauses to handle duplicates:

- `ON CONFLICT DO NOTHING` — for crowns and bans (idempotent inserts)
- `ON CONFLICT ... DO UPDATE` — for scores (allows correction of an existing score)

This pattern appears in: `utils/parsing.py:33-38`, `cogs/admin.py:39-43`, `cogs/fails.py:74-78`

## 4. Banned User Filtering

Banned users are excluded at two levels:

- **Write time:** Both `parse_wordle_message` and `parse_summary_message` check `banned_users` table before inserting (`utils/parsing.py:29`, `utils/parsing.py:100`)
- **Read time:** Leaderboard and stats queries include `WHERE user_id NOT IN (SELECT user_id FROM banned_users)` (`utils/leaderboard.py:4`, `cogs/streaks.py:17`, `cogs/fails.py:25`)

## 5. Dual-Table Score Recording

Fails (X/6) are recorded in two places:

- `scores` table with `attempts = NULL`
- `fails` table as a dedicated record

This duplication enables the `fails_leaderboard` without complex queries on the scores table while keeping fails counted in `games_played` on the main leaderboard.

Reference: `utils/parsing.py:41-46`, `cogs/fails.py:144-155`

## 6. Message Parsing Pipeline

Incoming messages flow through `cogs/events.py` `on_message` listener with priority routing:

1. Summary messages ("Here are yesterday's results:") → `parse_summary_message()`
2. Bot embeds (Wordle share) → `parse_wordle_message()`
3. Manual text submissions (admin only) → `parse_wordle_message()`

Both parsers live in `utils/parsing.py` and handle score insertion, fail tracking, crown assignment, and personal-best notifications.

## 7. Embed-Based Responses

All user-facing output uses `discord.Embed` objects rather than plain text. Each leaderboard/stats command builds an embed with `add_field()` calls for structured display.

Reference: `utils/leaderboard.py:75-105`, `cogs/crowns.py:23-29`, `cogs/streaks.py:46-48`

## 8. Deferred Interactions

Slash commands that hit the database use `interaction.response.defer(thinking=True)` followed by `interaction.followup.send()` to avoid Discord's 3-second response timeout.

Reference: `cogs/leaderboard.py:14`, `cogs/crowns.py:11`, `cogs/streaks.py:12`
