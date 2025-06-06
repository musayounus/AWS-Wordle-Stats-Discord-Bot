import os
from dotenv import load_dotenv
import discord

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
TEST_GUILD_ID = int(os.getenv("TEST_GUILD_ID", "1364244767201955910"))
PREDICTION_CHANNEL_ID = int(os.getenv("PREDICTION_CHANNEL_ID", "1364244767201955911"))
PREDICTION_TIME_HOUR = int(os.getenv("PREDICTION_TIME_HOUR", "11"))
AWS_REGION = os.getenv("AWS_REGION", "eu-central-1")
RDS_SECRET_ARN = os.getenv("RDS_SECRET_ARN", 'arn:aws:secretsmanager:eu-central-1:222634374532:secret:rds!db-5bb0c45b-baa5-40c4-9763-6fc3136ad726')

INTENTS = discord.Intents.default()
INTENTS.messages = True
INTENTS.message_content = True