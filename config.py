import os
from dotenv import load_dotenv
import discord

# Load from .env
load_dotenv()

# ── Discord / Bot settings ────────────────────────────────────────────────────
TOKEN                = os.getenv("DISCORD_BOT_TOKEN")
TEST_GUILD_ID        = int(os.getenv("TEST_GUILD_ID", "1364244767201955910"))

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