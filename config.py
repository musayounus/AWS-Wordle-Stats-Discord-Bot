import os
from dotenv import load_dotenv
import discord

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
TEST_GUILD_ID = int(os.getenv("TEST_GUILD_ID", "1364244767201955910"))
PREDICTION_CHANNEL_ID = int(os.getenv("PREDICTION_CHANNEL_ID", "1364244767201955911"))
PREDICTION_TIME_HOUR = int(os.getenv("PREDICTION_TIME_HOUR", "11"))
RDS_SECRET_ARN = os.getenv('RDS_SECRET_ARN')
RDS_HOST = os.getenv('RDS_HOST')
RDS_DBNAME = os.getenv('RDS_DBNAME', 'postgres')
RDS_PORT = int(os.getenv('RDS_PORT', 5432))

INTENTS = discord.Intents.default()
INTENTS.messages = True
INTENTS.message_content = True