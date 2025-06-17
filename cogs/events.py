import datetime
import re
import discord
from discord.ext import commands
from utils.parsing import parse_wordle_message, parse_summary_message

class EventsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Avoid loops
        if message.author == self.bot.user:
            return

        # --- 1) Official Wordle summary messages ---
        # These come from the Wordle Bot (message.author.bot) but contain plaintext:
        #    "Here are yesterday's results:" 
        if "Here are yesterday's results:" in (message.content or ""):
            await parse_summary_message(self.bot, message)
            return

        # --- 2) Official `/share` embed from Wordle Bot ---
        # Look for embeds with titles like "Wordle 1441 3/6"
        if message.author.bot and message.embeds:
            embed = message.embeds[0]
            if embed.title and re.search(r"Wordle\s+\d+\s+\d|X/6", embed.title, re.IGNORECASE):
                # Let your parsing utility handle associating it to the correct user
                await parse_wordle_message(self.bot, message)
            return

        # --- 3) Manual text-based Wordle submissions ---
        # Only allow real admins to submit `Wordle #### X/6` in chat
        if "Wordle" in message.content:
            if not message.author.guild_permissions.administrator:
                # non-admin manual submissions are ignored
                return
            await parse_wordle_message(self.bot, message)
            return

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        # Re-run logic on edits
        await self.on_message(after)


async def setup(bot):
    await bot.add_cog(EventsCog(bot))