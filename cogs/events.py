import datetime
import re
from discord.ext import commands
from utils.parsing import parse_wordle_message, parse_summary_lines, parse_summary_result_line, parse_mentions
from db.queries import (
    insert_score, is_user_banned, get_previous_best, insert_crown
)
from config import PREDICTION_CHANNEL_ID
from utils.leaderboard import generate_leaderboard_embed

class EventsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"✅ Logged in as {self.bot.user} (ID: {self.bot.user.id})")

    @commands.Cog.listener()
    async def on_message(self, message):
        # Don't react to itself
        if message.author == self.bot.user:
            return

        content = message.content
        
        # DEBUG LOGGING
        print(f"\n---\nNew message from {message.author} ({message.author.id}):\n{content[:200]}")

        # --- Individual Wordle result ---
        wordle_number, attempts = parse_wordle_message(content)
        if wordle_number is not None:
            print(f"✅ Detected manual score: Wordle {wordle_number} {attempts}/6")
            async with self.bot.pg_pool.acquire() as conn:
                is_banned = await is_user_banned(conn, message.author.id)
                if is_banned:
                    print(f"🚫 User {message.author} is banned - skipping")
                    return
                
                previous_best = await get_previous_best(conn, message.author.id)
                await insert_score(
                    conn, 
                    message.author.id, 
                    message.author.display_name, 
                    wordle_number, 
                    message.created_at.date(), 
                    attempts
                )
                print(f"💾 Saved score: {message.author.display_name} - Wordle {wordle_number} {attempts}/6")

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
                print(f"✅ Detected /share embed: Wordle {wordle_number} {attempts}/6")
                
                # Find the actual user from last /share message
                channel = message.channel
                async for m in channel.history(limit=20, before=message.created_at, oldest_first=False):
                    if not m.author.bot and "/share" in m.content.lower():
                        user = m.author
                        break
                else:
                    print("⚠️ Couldn't find user for /share embed")
                    return
                
                async with self.bot.pg_pool.acquire() as conn:
                    is_banned = await is_user_banned(conn, user.id)
                    if is_banned:
                        print(f"🚫 User {user} is banned - skipping /share embed")
                        return
                    
                    previous_best = await get_previous_best(conn, user.id)
                    await insert_score(conn, user.id, user.display_name, wordle_number, date, attempts)
                    print(f"💾 Saved /share score: {user.display_name} - Wordle {wordle_number} {attempts}/6")

                    if attempts == 1:
                        await message.channel.send(f"This rat <@{user.id}> got it in **1/6**... LOSAH CHEATED 100%!!")
                    elif previous_best is None or (attempts is not None and attempts < previous_best):
                        await message.channel.send(f"Flippin <@{user.id}> just beat their personal best with **{attempts}/6**. Good Job Brev 👍")
            return

        # --- Summary Message ---
        summary_phrases = [
            "here are yesterday's results",
            "daily wordle results",
            "wordle summary"
        ]
        
        if any(phrase in content.lower() for phrase in summary_phrases):
            print("✅ Detected summary message")
            summary_lines = parse_summary_lines(content)
            date = message.created_at.date() - datetime.timedelta(days=1)
            wordle_start = datetime.date(2021, 6, 19)
            wordle_number = (date - wordle_start).days
            print(f"📅 Processing Wordle {wordle_number} for {date}")

            # Parse results and crowns
            async with self.bot.pg_pool.acquire() as conn:
                for line in summary_lines:
                    attempts, user_section = parse_summary_result_line(line)
                    if attempts is not None and user_section:
                        print(f"📝 Processing line: {line}")
                        for user_id, username in parse_mentions(user_section, message.mentions):
                            is_banned = await is_user_banned(conn, user_id)
                            if is_banned:
                                print(f"🚫 Banned user in summary: {username}")
                                continue
                            
                            previous_best = await get_previous_best(conn, user_id)
                            await insert_score(conn, user_id, username, wordle_number, date, attempts)
                            print(f"💾 Saved summary score: {username} - {attempts}/6")

                            if attempts == 1:
                                await message.channel.send(f"This rat <@{user_id}> got it in **1/6**... LOSAH CHEATED 100%!!")
                            elif previous_best is None or (attempts is not None and attempts < previous_best):
                                await message.channel.send(f"Flippin <@{user_id}> just beat their personal best with **{attempts}/6**. Good Job Brev 👍")

                # 👑 Crowns
                for line in summary_lines:
                    if line.startswith("👑"):
                        print(f"👑 Processing crown line: {line}")
                        for user_id, username in parse_mentions(line, message.mentions):
                            await insert_crown(conn, user_id, username, wordle_number, date)
                            print(f"👑 Crown assigned to {username}")

            # Auto-post leaderboard after summary
            try:
                print("🔄 Generating leaderboard...")
                embed = await generate_leaderboard_embed(self.bot)
                await message.channel.send(embed=embed)
                print("🏆 Leaderboard posted successfully")
            except Exception as e:
                print(f"❌ Error posting leaderboard: {str(e)}")
            return

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.content != after.content or before.embeds != after.embeds:
            print(f"✏️ Detected message edit from {after.author}")
            await self.on_message(after)

async def setup(bot):
    await bot.add_cog(EventsCog(bot))