# /cogs/events.py
# This cog handles all real-time message events.

from discord.ext import commands
from utils.parsing import (
    parse_wordle_message,
    parse_share_embed,
    parse_summary_message
)

class EventsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        # This on_ready is fine, but we'll remove the one in bot.py to avoid duplicate "Logged in" messages.
        # The one in setup_hook in bot.py is sufficient.
        pass

    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignore messages from the bot itself
        if message.author == self.bot.user:
            return

        # --- Message Routing ---
        # The bot will now attempt to parse messages in a specific order.
        # It returns after the first successful parse to avoid double-processing.

        content = message.content

        # 1. Check for a standard "Wordle #### X/6" message
        # This is a common format and should be checked first.
        if "Wordle" in content and "/" in content and "results" not in content:
            await parse_wordle_message(self.bot, message)
            return

        # 2. Check for an embed from a bot (likely a /share command)
        if message.author.bot and message.embeds:
            await parse_share_embed(self.bot, message)
            return

        # 3. Check for a daily summary message
        if "Here are yesterday's results:" in content:
            await parse_summary_message(self.bot, message)
            return

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        # If a message is edited, re-run the parsing logic on the new content.
        # This handles cases where a user corrects a typo in their score.
        if before.content != after.content or before.embeds != after.embeds:
            await self.on_message(after)

async def setup(bot):
    await bot.add_cog(EventsCog(bot))