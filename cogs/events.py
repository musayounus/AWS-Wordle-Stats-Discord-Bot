import datetime
import re
from discord.ext import commands
from utils.parsing import parse_wordle_message, parse_summary_lines, parse_summary_result_line, parse_mentions
from db.queries import (
    insert_score, is_user_banned, get_previous_best, insert_crown
)
from config import PREDICTION_CHANNEL_ID

class EventsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"✅ Logged in as {self.bot.user} (ID: {self.bot.user.id})")

    @commands.Cog.listener()
    async def on_message(self, message):
        # Don’t react to itself
        if message.author == self.bot.user:
            return

        content = message.content

        # --- Individual Wordle result ---
        wordle_number, attempts = parse_wordle_message(content)
        if wordle_number is not None:
            # Score logic
            async with self.bot.pg_pool.acquire() as conn:
                is_banned = await is_user_banned(conn, message.author.id)
                if is_banned:
                    return
                previous_best = await get_previous_best(conn, message.author.id)
                await insert_score(conn, message.author.id, message.author.display_name, wordle_number, message.created_at.date(), attempts)
                # Celebrations
                if attempts == 1:
                    await message.channel.send(f"This rat {message.author.mention} got it in **1/6**... LOSAH CHEATED 100%!!")
                elif previous_best is None or (attempts is not None and attempts < previous_best):
                    await message.channel.send(f"Flippin {message.author.mention} just beat their personal best with **{attempts}/6**. Good Job Brev 👍")
            return

        # --- Embed from /share ---
        if message.author.bot and message.embeds:
            embed = message.embeds[0]
            match = re.search(r"Wordle\s+(\d+)\s+(\d|X)/6", embed.title if embed.title else "", re.IGNORECASE)
            if match:
                wordle_number = int(match.group(1))
                raw = match.group(2).upper()
                attempts = None if raw == "X" else int(raw)
                date = message.created_at.date()
                # Find the actual user from last /share message
                channel = message.channel
                async for m in channel.history(limit=20, before=message.created_at, oldest_first=False):
                    if not m.author.bot and "/share" in m.content.lower():
                        user = m.author
                        break
                else:
                    return
                async with self.bot.pg_pool.acquire() as conn:
                    is_banned = await is_user_banned(conn, user.id)
                    if is_banned:
                        return
                    previous_best = await get_previous_best(conn, user.id)
                    await insert_score(conn, user.id, user.display_name, wordle_number, date, attempts)
                    if attempts == 1:
                        await message.channel.send(f"This rat <@{user.id}> got it in **1/6**... LOSAH CHEATED 100%!!")
                    elif previous_best is None or (attempts is not None and attempts < previous_best):
                        await message.channel.send(f"Flippin <@{user.id}> just beat their personal best with **{attempts}/6**. Good Job Brev 👍")
            return

        # --- Summary Message ---
        if "Here are yesterday's results:" in content:
            summary_lines = parse_summary_lines(content)
            date = message.created_at.date() - datetime.timedelta(days=1)
            wordle_start = datetime.date(2021, 6, 19)
            wordle_number = (date - wordle_start).days
            # Parse results and crowns
            async with self.bot.pg_pool.acquire() as conn:
                for line in summary_lines:
                    attempts, user_section = parse_summary_result_line(line)
                    if attempts is not None and user_section:
                        for user_id, username in parse_mentions(user_section, message.mentions):
                            is_banned = await is_user_banned(conn, user_id)
                            if is_banned:
                                continue
                            previous_best = await get_previous_best(conn, user_id)
                            await insert_score(conn, user_id, username, wordle_number, date, attempts)
                            if attempts == 1:
                                await message.channel.send(f"This rat <@{user_id}> got it in **1/6**... LOSAH CHEATED 100%!!")
                            elif previous_best is None or (attempts is not None and attempts < previous_best):
                                await message.channel.send(f"Flippin <@{user_id}> just beat their personal best with **{attempts}/6**. Good Job Brev 👍")
                # 👑 Crowns
                for line in summary_lines:
                    if line.startswith("👑"):
                        for user_id, username in parse_mentions(line, message.mentions):
                            await insert_crown(conn, user_id, username, wordle_number, date)
            # TODO: Auto-post leaderboard after summary (import and call generate_leaderboard_embed from leaderboard cog, then send)
            return

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.content != after.content or before.embeds != after.embeds:
            await self.on_message(after)

async def setup(bot):
    await bot.add_cog(EventsCog(bot))