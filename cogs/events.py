import re
import datetime
import discord
from discord.ext import commands
from utils.parsing import parse_wordle_message, parse_summary_message

class EventsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Avoid loops and invalid messages
        if message.author == self.bot.user or not message.content:
            return

        content = message.content.strip()

        # --- 1) Official Wordle summary messages ---
        if "Here are yesterday's results:" in content:
            await parse_summary_message(self.bot, message)
            return

        # --- 2) Official `/share` embed from Wordle Bot ---
        if message.author.bot and message.embeds:
            embed = message.embeds[0]
            if embed.title and re.search(r"Wordle\s+\d+\s+\d|X/6", embed.title, re.IGNORECASE):
                await parse_wordle_message(self.bot, message)
            return

        # --- 3) Manual text-based Wordle submissions ---
        # Only allow admins to submit manual Wordle scores
        if (re.search(r"Wordle\s+\d+\s+\d|X/6", content, re.IGNORECASE) and 
            message.author.guild_permissions.administrator):
            await parse_wordle_message(self.bot, message)
            return

        # --- 4) Handle potential Wordle-related messages that might need processing ---
        # (Add any additional message patterns you want to handle here)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        # Re-process edited messages that might contain Wordle results
        if before.content != after.content:
            await self.on_message(after)

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return  # Ignore unknown commands
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send("⛔ You don't have permission to use this command.")
        else:
            print(f"Error in command {ctx.command}: {error}")
            await ctx.send("⚠️ An error occurred while processing that command.")

async def setup(bot):
    await bot.add_cog(EventsCog(bot))