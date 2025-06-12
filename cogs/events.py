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
    async def on_message(self, message):
        # Ignore messages from the bot itself
        if message.author.bot:
            return

        # --- Message Routing ---
        # The bot will attempt to parse messages in a specific order.
        # We use 'return' after a successful parse to avoid double-processing.
        content = message.content

        # 1. Check for a daily summary message
        if "Here are yesterday's results:" in content:
            await parse_summary_message(self.bot, message)
            return

        # 2. Check for an embed (likely a /share command)
        # This check is safer when you also check message.author.bot, but some setups might re-post embeds.
        # The logic in parse_share_embed correctly finds the non-bot user.
        if message.embeds:
            # We assume the first embed is the one to parse.
            await parse_share_embed(self.bot, message)
            return

        # 3. Check for a standard "Wordle #### X/6" message
        if "Wordle" in content and "/" in content:
            await parse_wordle_message(self.bot, message)
            return
            
        # --- CRUCIAL FIX ---
        # This line allows the bot to process other commands after our custom on_message listener runs.
        # Without this, all command processing STOPS here.
        await self.bot.process_commands(message)


    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        # If a message is edited, re-run the parsing logic on the new content.
        # This handles cases where a user corrects a typo in their score.
        if before.content != after.content or before.embeds != after.embeds:
            # We only need to re-run on_message, not process_commands again.
            await self.on_message(after)

async def setup(bot):
    await bot.add_cog(EventsCog(bot))