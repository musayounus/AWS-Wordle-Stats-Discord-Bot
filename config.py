import os
from dotenv import load_dotenv

load_dotenv()

# Bot command prefix
BOT_COMMAND_PREFIX = "!"

# AWS Secrets Manager
AWS_REGION_NAME = "eu-central-1"
SECRET_NAME = "wordle-bot/db-creds"

# Discord Channel IDs
PREDICTION_CHANNEL_ID = int(os.getenv("PREDICTION_CHANNEL_ID", 0))