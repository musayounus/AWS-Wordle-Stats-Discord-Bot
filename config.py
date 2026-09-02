import os
from dotenv import load_dotenv
import discord

# Load from .env
load_dotenv()

# ── Discord / Bot settings ────────────────────────────────────────────────────
TOKEN                = os.getenv("DISCORD_BOT_TOKEN")
_test_guild_env      = os.getenv("TEST_GUILD_ID")
TEST_GUILD_ID        = int(_test_guild_env) if _test_guild_env else None

# When True: only server admins can invoke slash commands, all command
# responses default to ephemeral (only the invoker sees them), and passive
# bot-initiated channel messages (personal-best praise, summary leaderboard
# auto-post) are suppressed. Flip off for production.
TESTING_MODE         = os.getenv("TESTING_MODE", "false").lower() in ("true", "1", "yes")

# Discord user ID of the official Wordle app. Only summary messages from
# this account are accepted by parse_summary_message; anyone else typing
# "Here are yesterday's results:" is ignored.
OFFICIAL_WORDLE_BOT_ID = int(os.getenv("OFFICIAL_WORDLE_BOT_ID", "1211781489931452447"))

# Timezone used to interpret "yesterday's results:" summary messages. The Wordle
# Discord app posts shortly after midnight local; using UTC caused summaries
# posted late-night-local to land on the wrong calendar day.
WORDLE_TZ = os.getenv("WORDLE_TZ", "Asia/Riyadh")

# Era cutover: scores with wordle_number >= this value are "current era",
# below it are "legacy". Default leaderboard/stats commands show current only;
# legacy reachable via era=legacy param. Env-overridable for future cutovers.
CURRENT_ERA_START_WORDLE = int(os.getenv("CURRENT_ERA_START_WORDLE", 1777))

# Minimum games played in a calendar month to qualify for the monthly crown.
# Applies both to the winner query and the monthly recap leaderboard, so the
# crowned user is always the top row of the board posted beside it.
MONTHLY_MIN_GAMES = int(os.getenv("MONTHLY_MIN_GAMES", 23))

# ── Quarterly awards ──────────────────────────────────────────────────────────
# Minimum games in a quarter to qualify for the average and champion awards.
# 3x the monthly floor, i.e. roughly 75% attendance over a ~92-day quarter.
QUARTERLY_MIN_GAMES = int(os.getenv("QUARTERLY_MIN_GAMES", 69))

# "Solve of the quarter" compares a score against everyone else who played that
# day. Days with fewer than this many *other* players are ignored, so a thin day
# can't produce a huge delta from noise.
SOLVE_MIN_OTHERS = int(os.getenv("SOLVE_MIN_OTHERS", 3))

# Champion of the quarter: each component is min-max normalised to 0-100 across
# the qualifying field, then weighted by these. Must sum to 100.
CHAMPION_WEIGHTS = {
    "avg": int(os.getenv("CHAMPION_WEIGHT_AVG", 40)),
    "crowns": int(os.getenv("CHAMPION_WEIGHT_CROWNS", 25)),
    "uncons": int(os.getenv("CHAMPION_WEIGHT_UNCONS", 15)),
    "solve": int(os.getenv("CHAMPION_WEIGHT_SOLVE", 10)),
    "games": int(os.getenv("CHAMPION_WEIGHT_GAMES", 10)),
}

# ── AWS / RDS settings ────────────────────────────────────────────────────────
AWS_REGION       = os.getenv("AWS_REGION", "eu-central-1")
RDS_SECRET_ARN   = os.getenv("RDS_SECRET_ARN")
RDS_HOST         = os.getenv("RDS_HOST")
RDS_DBNAME       = os.getenv("RDS_DBNAME", "postgres")
RDS_PORT         = int(os.getenv("RDS_PORT", 5432))

# ── Bot Intents ───────────────────────────────────────────────────────────────
INTENTS = discord.Intents.default()
INTENTS.messages        = True
INTENTS.message_content = True
INTENTS.guilds          = True
INTENTS.members         = True