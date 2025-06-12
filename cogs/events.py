import discord
from discord.ext import commands
from utils.parsing import parse_wordle_message, parse_summary_message

class EventsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore messages sent by bots
        if message.author.bot:
            return

        # Ignore DMs (no guild info)
        if not message.guild:
            return

        # Check if author is an admin using permissions from the message
        if not message.author.guild_permissions.administrator:
            return  # Not an admin — ignore the message

        # Process Wordle score messages
        if "Wordle" in message.content:
            await parse_wordle_message(self.bot, message)

        # Process daily summary messages
        elif "Here are yesterday's results:" in message.content:
            await parse_summary_message(self.bot, message)

# Load the cog
async def setup(bot):
    await bot.add_cog(EventsCog(bot))