import os
from dotenv import load_dotenv
import discord

# Load from .env
load_dotenv()

# ── Discord / Bot settings ────────────────────────────────────────────────────
TOKEN                = os.getenv("DISCORD_BOT_TOKEN")
TEST_GUILD_ID        = int(os.getenv("TEST_GUILD_ID", "1364244767201955910"))
PREDICTION_CHANNEL_ID= int(os.getenv("PREDICTION_CHANNEL_ID", "1364244767201955911"))
PREDICTION_TIME_HOUR = int(os.getenv("PREDICTION_TIME_HOUR", "11"))

# ── AWS / RDS settings ────────────────────────────────────────────────────────
AWS_REGION       = os.getenv("AWS_REGION", "eu-central-1")
RDS_SECRET_ARN   = os.getenv("RDS_SECRET_ARN")        # e.g. arn:aws:secretsmanager:...
RDS_HOST         = os.getenv("RDS_HOST")              # e.g. wordle-db.cjywummmsd5i.eu-central-1.rds.amazonaws.com
RDS_DBNAME       = os.getenv("RDS_DBNAME", "postgres")
RDS_PORT         = int(os.getenv("RDS_PORT", 5432))

# ── Bot Intents ───────────────────────────────────────────────────────────────
INTENTS = discord.Intents.default()
INTENTS.messages        = True
INTENTS.message_content = True
INTENTS.guilds          = True
INTENTS.members         = True