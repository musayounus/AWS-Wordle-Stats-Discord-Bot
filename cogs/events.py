import discord
from discord.ext import commands
from utils.parsing import parse_wordle_message, parse_summary_message

class EventsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore bot's own messages
        if message.author.bot:
            return

        # Check for Wordle score message
        if "Wordle" in message.content:
            await parse_wordle_message(self.bot, message)

        # Check for summary message
        elif "Here are yesterday's results:" in message.content:
            await parse_summary_message(self.bot, message)

async def setup(bot):
    await bot.add_cog(EventsCog(bot))