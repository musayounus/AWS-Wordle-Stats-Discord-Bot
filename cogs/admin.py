import discord
from discord import app_commands
from discord.ext import commands
import datetime
import re
import asyncio

class AdminCog(commands.Cog):
    """Admin-only commands for managing scores, bans, crowns, and imports."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="reset_leaderboard", description="Reset the Wordle leaderboard")
    @app_commands.checks.has_permissions(administrator=True)
    async def resetleaderboard(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "⚠️ Are you sure you want to reset the leaderboard? Type `yes` within 30s to confirm reset."
        )
        def check(m): 
            return m.author.id == interaction.user.id and m.content.lower() == "yes"
        try:
            await self.bot.wait_for("message", timeout=30.0, check=check)
            async with self.bot.pg_pool.acquire() as conn:
                await conn.execute("DELETE FROM scores")
                await conn.execute("DELETE FROM crowns")
                await conn.execute("DELETE FROM uncontended_crowns")
                await conn.execute("DELETE FROM fails")
            await interaction.followup.send("✅ Leaderboard reset.")
        except asyncio.TimeoutError:
            await interaction.followup.send("❌ Reset cancelled.")
        except Exception as e:
            await interaction.followup.send(f"❌ Reset failed: {e}")

    @app_commands.command(name="ban_user", description="Ban a user from leaderboard and stats")
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

    @app_commands.command(name="unban_user", description="Unban a previously banned user")
    @app_commands.describe(user="User to unban")
    @app_commands.checks.has_permissions(administrator=True)
    async def unbanuser(self, interaction: discord.Interaction, user: discord.User):
        async with self.bot.pg_pool.acquire() as conn:
            try:
                await conn.execute("DELETE FROM banned_users WHERE user_id = $1", user.id)
                await interaction.response.send_message(f"✅ {user.mention} has been unbanned.")
            except Exception as e:
                await interaction.response.send_message(f"❌ Failed to unban user: {e}", ephemeral=True)

    @app_commands.command(name="remove_scores", description="Remove multiple Wordle scores from a user")
    @app_commands.describe(
        user="User to remove scores for",
        wordle_numbers="Comma-separated Wordle numbers (e.g. 123,124,125)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def removescores(self, interaction: discord.Interaction, user: discord.User, wordle_numbers: str):
        try:
            numbers = [int(n.strip()) for n in wordle_numbers.split(",") if n.strip().isdigit()]
            if not numbers:
                await interaction.response.send_message("⚠️ No valid Wordle numbers provided.", ephemeral=True)
                return

            async with self.bot.pg_pool.acquire() as conn:
                deleted = await conn.fetch("""
                    DELETE FROM scores
                    WHERE user_id = $1 AND wordle_number = ANY($2)
                    RETURNING wordle_number
                """, user.id, numbers)

            dc = len(deleted)
            rc = len(numbers)
            if dc == 0:
                await interaction.response.send_message(
                    f"ℹ️ No matching scores found for {user.mention}.", ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"✅ Removed {dc} out of {rc} requested scores for {user.mention}.",
                    ephemeral=True
                )
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to remove scores: {e}", ephemeral=True)

    @app_commands.command(name="import", description="Import Wordle scores from past messages in this channel")
    @app_commands.checks.has_permissions(administrator=True)
    async def import_scores(self, interaction: discord.Interaction):
        await interaction.response.send_message("⏳ Scanning channel messages for Wordle scores...")
        count = 0
        fail_count = 0
        crown_count = 0
        uc_count = 0
        channel = interaction.channel
        wordle_start = datetime.date(2021, 6, 19)

        async for message in channel.history(limit=None, oldest_first=True):
            content = message.content

            # Direct manual submissions
            m = re.search(r'Wordle\s+(\d+)\s+(\d|X)/6', content, re.IGNORECASE)
            if m:
                if message.author.bot or message.author.display_name.lower() in ("wordle bot", "wordle"):
                    continue
                wn = int(m.group(1))
                raw = m.group(2).upper()
                attempts = None if raw == "X" else int(raw)
                date = message.created_at.date()
                async with self.bot.pg_pool.acquire() as conn:
                    try:
                        await conn.execute("""
                            INSERT INTO scores (user_id, username, wordle_number, date, attempts)
                            VALUES ($1, $2, $3, $4, $5)
                            ON CONFLICT (username, wordle_number) DO NOTHING
                        """, message.author.id, message.author.display_name, wn, date, attempts)
                        count += 1
                        if attempts is None:
                            await conn.execute("""
                                INSERT INTO fails (user_id, username, wordle_number, date)
                                VALUES ($1, $2, $3, $4)
                                ON CONFLICT (user_id, wordle_number) DO NOTHING
                            """, message.author.id, message.author.display_name, wn, date)
                            fail_count += 1
                    except:
                        pass
                continue

            # Summary messages
            if "Here are yesterday's results:" in content:
                date = message.created_at.date() - datetime.timedelta(days=1)
                wn = (date - wordle_start).days
                lines = content.strip().splitlines()
                pattern = re.compile(r"(\d|X)/6:\s+(.*)")

                results = []
                for line in lines:
                    mm = pattern.search(line)
                    if mm:
                        raw = mm.group(1).upper()
                        attempts = None if raw == "X" else int(raw)
                        section = mm.group(2)
                        for user in message.mentions:
                            if f"@{user.display_name}" in section or f"<@{user.id}>" in section:
                                results.append((user.id, user.display_name, attempts))

                # Insert scores and fails
                async with self.bot.pg_pool.acquire() as conn:
                    for uid, uname, att in results:
                        try:
                            await conn.execute("""
                                INSERT INTO scores (user_id, username, wordle_number, date, attempts)
                                VALUES ($1, $2, $3, $4, $5)
                                ON CONFLICT (username, wordle_number) DO NOTHING
                            """, uid, uname, wn, date, att)
                            count += 1
                            if att is None:
                                await conn.execute("""
                                    INSERT INTO fails (user_id, username, wordle_number, date)
                                    VALUES ($1, $2, $3, $4)
                                    ON CONFLICT (user_id, wordle_number) DO NOTHING
                                """, uid, uname, wn, date)
                                fail_count += 1
                        except:
                            pass

                # Crowns
                best = min((r[2] for r in results if r[2] is not None), default=None)
                top_users = [(uid, uname) for uid, uname, a in results if a == best]
                async with self.bot.pg_pool.acquire() as conn:
                    for uid, uname in top_users:
                        try:
                            await conn.execute("""
                                INSERT INTO crowns (user_id, username, wordle_number, date)
                                VALUES ($1, $2, $3, $4)
                                ON CONFLICT DO NOTHING
                            """, uid, uname, wn, date)
                            crown_count += 1
                        except:
                            pass

                    # Uncontended crowns — only increment if crown was actually new
                    if len(top_users) == 1:
                        existing = await conn.fetchval(
                            "SELECT 1 FROM crowns WHERE user_id = $1 AND wordle_number = $2",
                            top_users[0][0], wn
                        )
                        if existing:
                            uc_count += 1

        # Rebuild uncontended_crowns from crowns (wordles with exactly one crown)
        async with self.bot.pg_pool.acquire() as conn:
            await conn.execute("DELETE FROM uncontended_crowns")
            await conn.execute("""
                INSERT INTO uncontended_crowns (user_id, username, wordle_number, date)
                SELECT user_id, username, wordle_number, date FROM crowns
                WHERE wordle_number IN (
                    SELECT wordle_number FROM crowns
                    GROUP BY wordle_number HAVING COUNT(*) = 1
                )
            """)

        # Cleanup and rebuild fails from scores to keep tables consistent
        async with self.bot.pg_pool.acquire() as conn:
            await conn.execute("""
                DELETE FROM scores
                WHERE LOWER(username) IN ('wordle bot', 'wordle')
            """)
            await conn.execute("DELETE FROM fails")
            await conn.execute("""
                INSERT INTO fails (user_id, username, wordle_number, date)
                SELECT DISTINCT ON (user_id, wordle_number)
                       user_id, username, wordle_number, date
                FROM scores
                WHERE attempts IS NULL
                ORDER BY user_id, wordle_number, date
            """)

            real_scores = await conn.fetchval("SELECT COUNT(*) FROM scores")
            real_fails = await conn.fetchval("SELECT COUNT(*) FROM fails")
            real_crowns = await conn.fetchval("SELECT COUNT(*) FROM crowns")
            real_uc = await conn.fetchval("SELECT COUNT(*) FROM uncontended_crowns")

        await interaction.followup.send(
            f"✅ Import complete. {real_scores} scores, {real_fails} fails, "
            f"{real_crowns} crowns, {real_uc} uncontended crowns."
        )

    @app_commands.command(
        name="set_uncontended_crowns",
        description="(Admin) Set a user's uncontended‐crown count."
    )
    @app_commands.describe(
        user="The user whose uncontended crowns to set.",
        count="The exact number of uncontended crowns."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_uncontended_crowns(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        count: int
    ):
        if count < 0:
            await interaction.response.send_message("❌ Count cannot be negative.", ephemeral=True)
            return

        async with self.bot.pg_pool.acquire() as conn:
            current = await conn.fetchval(
                "SELECT COUNT(*) FROM uncontended_crowns WHERE user_id = $1", user.id
            ) or 0
            diff = count - current
            if diff > 0:
                for i in range(diff):
                    dummy_wordle = 79999 - i
                    await conn.execute("""
                        INSERT INTO uncontended_crowns (user_id, username, wordle_number, date)
                        VALUES ($1, $2, $3, CURRENT_DATE)
                        ON CONFLICT (user_id, wordle_number) DO NOTHING
                    """, user.id, user.display_name, dummy_wordle)
            elif diff < 0:
                to_remove = await conn.fetch("""
                    SELECT wordle_number FROM uncontended_crowns
                    WHERE user_id = $1
                    ORDER BY date ASC
                    LIMIT $2
                """, user.id, -diff)
                if to_remove:
                    wn_list = [r['wordle_number'] for r in to_remove]
                    await conn.execute("""
                        DELETE FROM uncontended_crowns
                        WHERE user_id = $1 AND wordle_number = ANY($2)
                    """, user.id, wn_list)

        await interaction.response.send_message(
            f"🥇 Uncontended crowns for {user.mention} set to {count}.",
            ephemeral=True
        )

    @app_commands.command(
        name="set_crowns",
        description="(Admin) Set a user's crown count."
    )
    @app_commands.describe(
        user="The user whose crowns to set.",
        count="The exact number of crowns."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_crowns(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        count: int
    ):
        if count < 0:
            await interaction.response.send_message("❌ Crown count cannot be negative.", ephemeral=True)
            return

        async with self.bot.pg_pool.acquire() as conn:
            current_count = await conn.fetchval(
                "SELECT COUNT(*) FROM crowns WHERE user_id = $1", user.id
            ) or 0

            difference = count - current_count

            if difference > 0:
                for i in range(difference):
                    dummy_wordle = 89999 - i
                    await conn.execute("""
                        INSERT INTO crowns (user_id, username, wordle_number, date)
                        VALUES ($1, $2, $3, CURRENT_DATE)
                        ON CONFLICT DO NOTHING
                    """, user.id, user.display_name, dummy_wordle)
            elif difference < 0:
                to_remove = await conn.fetch("""
                    SELECT wordle_number FROM crowns
                    WHERE user_id = $1
                    ORDER BY date ASC
                    LIMIT $2
                """, user.id, -difference)
                if to_remove:
                    wn_list = [r['wordle_number'] for r in to_remove]
                    await conn.execute("""
                        DELETE FROM crowns
                        WHERE user_id = $1 AND wordle_number = ANY($2)
                    """, user.id, wn_list)

        await interaction.response.send_message(
            f"👑 Crown count for {user.mention} set to {count}.",
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(AdminCog(bot))