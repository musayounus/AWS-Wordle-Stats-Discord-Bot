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
        # Avoid loops
        if message.author == self.bot.user:
            return

        content = (message.content or "").strip()

        # --- 1) Official Wordle summary messages ---
        if "Here are yesterday's results:" in content:
            await parse_summary_message(self.bot, message)
            return

        # --- 2) Wordle APP /share (bot-authored slash-command result) ---
        if message.author.bot:
            meta = getattr(message, "interaction_metadata", None) or getattr(message, "interaction", None)
            if meta is None or getattr(meta, "user", None) is None:
                return
            candidate = content or (message.embeds[0].title if message.embeds else "") or ""
            if re.search(r"Wordle\s+\d+\s+(\d|X)/6", candidate, re.IGNORECASE):
                await parse_wordle_message(self.bot, message)
                from utils.leaderboard import generate_leaderboard_embed
                embed = await generate_leaderboard_embed(self.bot)
                await message.channel.send(embed=embed)
            return

        # --- 3) Manual text-based Wordle submissions ---
        # Only allow admins to submit manual Wordle scores
        if (re.search(r"Wordle\s+\d+\s+(\d|X)/6", content, re.IGNORECASE) and
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