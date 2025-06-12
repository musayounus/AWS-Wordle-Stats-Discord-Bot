import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv

from config import BOT_COMMAND_PREFIX
from db.pool import create_pool
# from process_guard import guard_process

load_dotenv()
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

class WordleBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pg_pool = None

    async def setup_hook(self):
        # Create the database connection pool
        self.pg_pool = await create_pool()
        if self.pg_pool:
            print("✅ Successfully connected to PostgreSQL.")
        else:
            print("🔥 Failed to connect to PostgreSQL.")
            # Exit if the database connection fails
            await self.close()
            return

        # Load cogs
        cogs_dir = "cogs"
        for filename in os.listdir(cogs_dir):
            if filename.endswith(".py"):
                try:
                    await self.load_extension(f"{cogs_dir}.{filename[:-3]}")
                    print(f"✅ Loaded cog: {filename}")
                except Exception as e:
                    print(f"🔥 Failed to load cog {filename}: {e}")

    async def close(self):
        if self.pg_pool:
            await self.pg_pool.close()
            print("✅ PostgreSQL connection pool closed.")
        await super().close()

async def main():
    intents = discord.Intents.default()
    intents.messages = True
    intents.guilds = True
    intents.members = True
    intents.message_content = True # <-- This is the required fix

    bot = WordleBot(command_prefix=BOT_COMMAND_PREFIX, intents=intents)

    await bot.start(DISCORD_BOT_TOKEN)

if __name__ == "__main__":
    # guard_process()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🤖 Bot is shutting down.")