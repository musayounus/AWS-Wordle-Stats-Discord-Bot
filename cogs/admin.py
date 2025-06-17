import discord
from discord import app_commands
from discord.ext import commands
import datetime
import re
import asyncio

class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="resetleaderboard", description="Reset the Wordle leaderboard")
    @app_commands.checks.has_permissions(administrator=True)
    async def resetleaderboard(self, interaction: discord.Interaction):
        await interaction.response.send_message("⚠️ Are you sure you want to reset the leaderboard? Type `yes` within 30s to confirm reset.")
        def check(m): return m.author.id == interaction.user.id and m.content.lower() == "yes"
        try:
            await self.bot.wait_for("message", timeout=30.0, check=check)
            async with self.bot.pg_pool.acquire() as conn:
                await conn.execute("DELETE FROM scores")
                await conn.execute("DELETE FROM crowns")
                await conn.execute("DELETE FROM uncontended_crowns")
            await interaction.followup.send("✅ Leaderboard reset.")
        except asyncio.TimeoutError:
            await interaction.followup.send("❌ Reset cancelled.")
        except Exception as e:
            await interaction.followup.send(f"❌ Reset failed: {e}")

    @app_commands.command(name="banuser", description="Ban a user from leaderboard and stats")
    @app_commands.describe(user="User to ban")
    @app_commands.checks.has_permissions(administrator=True)
    async def banuser(self, interaction: discord.Interaction, user: discord.User):
        async with self.bot.pg_pool.acquire() as conn:
            try:
                await conn.execute("""
                    INSERT INTO banned_users (user_id, username)
                    VALUES ($1, $2)
                    ON CONFLICT (user_id) DO NOTHING
                """, user.id, user.display_name)
                await interaction.response.send_message(f"🚫 {user.mention} has been banned.")
            except Exception as e:
                await interaction.response.send_message(f"❌ Failed to ban user: {e}", ephemeral=True)

    @app_commands.command(name="unbanuser", description="Unban a previously banned user")
    @app_commands.describe(user="User to unban")
    @app_commands.checks.has_permissions(administrator=True)
    async def unbanuser(self, interaction: discord.Interaction, user: discord.User):
        async with self.bot.pg_pool.acquire() as conn:
            try:
                await conn.execute("DELETE FROM banned_users WHERE user_id = $1", user.id)
                await interaction.response.send_message(f"✅ {user.mention} has been unbanned.")
            except Exception as e:
                await interaction.response.send_message(f"❌ Failed to unban user: {e}", ephemeral=True)

    @app_commands.command(name="removescores", description="Remove multiple Wordle scores from a user")
    @app_commands.describe(
        user="User to remove scores for",
        wordle_numbers="Comma-separated Wordle numbers (e.g. 123,124,125)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def removescores(self, interaction: discord.Interaction, user: discord.User, wordle_numbers: str):
        try:
            numbers = [int(num.strip()) for num in wordle_numbers.split(",") if num.strip().isdigit()]
            if not numbers:
                await interaction.response.send_message("⚠️ No valid Wordle numbers provided.", ephemeral=True)
                return

            async with self.bot.pg_pool.acquire() as conn:
                deleted_rows = await conn.fetch("""
                    DELETE FROM scores
                    WHERE user_id = $1 AND wordle_number = ANY($2)
                    RETURNING wordle_number
                """, user.id, numbers)

            deleted_count = len(deleted_rows)
            requested_count = len(numbers)
            if deleted_count == 0:
                await interaction.response.send_message(
                    f"ℹ️ No matching scores found for {user.mention}.", ephemeral=True)
            else:
                await interaction.response.send_message(
                    f"✅ Removed {deleted_count} out of {requested_count} requested scores for {user.mention}.",
                    ephemeral=True
                )
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to remove scores: {e}", ephemeral=True)

    @app_commands.command(name="import", description="Import Wordle scores from past messages in this channel")
    @app_commands.checks.has_permissions(administrator=True)
    async def import_scores(self, interaction: discord.Interaction):
        await interaction.response.send_message("⏳ Scanning channel messages for Wordle scores...")

        count = 0
        crown_count = 0
        channel = interaction.channel
        wordle_start = datetime.date(2021, 6, 19)
        import re

        async for message in channel.history(limit=None, oldest_first=True):
            content = message.content
            # Direct match: Wordle #### #/6
            match = re.search(r'Wordle\s+(\d+)\s+(\d|X)/6', content, re.IGNORECASE)
            if match:
                if message.author.bot or str(message.author.display_name).lower() in ["wordle bot", "wordle"]:
                    continue
                wordle_number = int(match.group(1))
                raw = match.group(2).upper()
                attempts = None if raw == "X" else int(raw)
                date = message.created_at.date()
                async with self.bot.pg_pool.acquire() as conn:
                    try:
                        await conn.execute("""
                            INSERT INTO scores (user_id, username, wordle_number, date, attempts)
                            VALUES ($1, $2, $3, $4, $5)
                            ON CONFLICT (username, wordle_number) DO NOTHING
                        """, message.author.id, message.author.display_name, wordle_number, date, attempts)
                        count += 1
                    except:
                        pass
                continue

            # Summary match
            if "Here are yesterday's results:" in content:
                date = message.created_at.date() - datetime.timedelta(days=1)
                wordle_number = (date - wordle_start).days
                summary_lines = content.strip().splitlines()
                pattern = re.compile(r"(\d|X)/6:\s+(.*)")

                summary_results = []

                for line in summary_lines:
                    match = pattern.search(line)
                    if match:
                        raw = match.group(1).upper()
                        attempts = None if raw == "X" else int(raw)
                        user_section = match.group(2)
                        if message.mentions:
                            for user in message.mentions:
                                if f"@{user.display_name}" in user_section or f"<@{user.id}>" in user_section:
                                    summary_results.append((user.id, user.display_name, attempts))

                # Insert scores
                async with self.bot.pg_pool.acquire() as conn:
                    for user_id, username, attempts in summary_results:
                        try:
                            await conn.execute("""
                                INSERT INTO scores (user_id, username, wordle_number, date, attempts)
                                VALUES ($1, $2, $3, $4, $5)
                                ON CONFLICT (username, wordle_number) DO NOTHING
                            """, user_id, username, wordle_number, date, attempts)
                            count += 1
                        except:
                            pass

                # Insert crown
                best_score = min([r[2] for r in summary_results if r[2] is not None], default=None)
                if best_score is not None:
                    top_users = [(uid, uname) for uid, uname, a in summary_results if a == best_score]
                    async with self.bot.pg_pool.acquire() as conn:
                        for user_id, username in top_users:
                            try:
                                await conn.execute("""
                                    INSERT INTO crowns (user_id, username, wordle_number, date)
                                    VALUES ($1, $2, $3, $4)
                                    ON CONFLICT DO NOTHING
                                """, user_id, username, wordle_number, date)
                                crown_count += 1
                            except:
                                pass

        await interaction.followup.send(f"✅ Import complete. {count} scores imported, {crown_count} crowns assigned.")

        # Cleanup: Remove imported scores from Wordle Bot or Wordle users
        async with self.bot.pg_pool.acquire() as conn:
            deleted = await conn.execute("""
                DELETE FROM scores
                WHERE LOWER(username) IN ('wordle bot', 'wordle')
            """)
            print(f"🧹 Cleanup complete: {deleted}")

async def setup(bot):
    await bot.add_cog(AdminCog(bot))