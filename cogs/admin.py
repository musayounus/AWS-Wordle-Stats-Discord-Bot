import discord
from discord import app_commands
from discord.ext import commands
import datetime
import re
import asyncio

from utils.user_resolver import (
    add_user_to_cache,
    extract_user_tokens,
    resolve_user,
)
from utils.admin_helpers import (
    sync_uncontended_for_wordle,
    validate_wordle_number,
    wordle_date_for_number,
)
from typing import Optional

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

    @app_commands.command(
        name="adjust_scores",
        description="Add or remove a Wordle score for a user on a specific Wordle",
    )
    @app_commands.describe(
        user="User to adjust",
        wordle_number="Wordle number",
        action="add or remove",
        attempts="Attempts (1-6 or X for fail) — required when action is add",
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="add", value="add"),
            app_commands.Choice(name="remove", value="remove"),
        ],
        attempts=[
            app_commands.Choice(name="1", value="1"),
            app_commands.Choice(name="2", value="2"),
            app_commands.Choice(name="3", value="3"),
            app_commands.Choice(name="4", value="4"),
            app_commands.Choice(name="5", value="5"),
            app_commands.Choice(name="6", value="6"),
            app_commands.Choice(name="X (fail)", value="X"),
        ],
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def adjust_scores(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        wordle_number: int,
        action: app_commands.Choice[str],
        attempts: Optional[app_commands.Choice[str]] = None,
    ):
        err = validate_wordle_number(wordle_number)
        if err:
            await interaction.response.send_message(f"❌ {err}", ephemeral=True)
            return

        date = wordle_date_for_number(wordle_number)

        if action.value == "add":
            if attempts is None:
                await interaction.response.send_message(
                    "❌ `attempts` is required when action is `add`.", ephemeral=True
                )
                return
            attempts_val = None if attempts.value == "X" else int(attempts.value)
            async with self.bot.pg_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO scores (user_id, username, wordle_number, date, attempts)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (username, wordle_number) DO UPDATE
                    SET attempts = $5
                    """,
                    user.id, user.display_name, wordle_number, date, attempts_val,
                )
                if attempts_val is None:
                    await conn.execute(
                        """
                        INSERT INTO fails (user_id, username, wordle_number, date)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT (user_id, wordle_number) DO NOTHING
                        """,
                        user.id, user.display_name, wordle_number, date,
                    )
                else:
                    await conn.execute(
                        "DELETE FROM fails WHERE user_id = $1 AND wordle_number = $2",
                        user.id, wordle_number,
                    )
            label = "X/6" if attempts_val is None else f"{attempts_val}/6"
            await interaction.response.send_message(
                f"✅ Set {user.mention}'s Wordle #{wordle_number} score to **{label}**.",
                ephemeral=True,
            )
            return

        # remove: nuke score + fail + crown for this (user, wordle), then sync uncontended
        async with self.bot.pg_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM scores WHERE user_id = $1 AND wordle_number = $2",
                user.id, wordle_number,
            )
            await conn.execute(
                "DELETE FROM fails WHERE user_id = $1 AND wordle_number = $2",
                user.id, wordle_number,
            )
            await conn.execute(
                "DELETE FROM crowns WHERE user_id = $1 AND wordle_number = $2",
                user.id, wordle_number,
            )
            await sync_uncontended_for_wordle(conn, wordle_number)
        await interaction.response.send_message(
            f"🗑️ Removed {user.mention}'s score, fail, and crown for Wordle #{wordle_number}.",
            ephemeral=True,
        )

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
        import_cache: dict = {}

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

                async with self.bot.pg_pool.acquire() as conn:
                    for user in message.mentions:
                        add_user_to_cache(import_cache, user)

                    results = []
                    for line in lines:
                        mm = pattern.search(line)
                        if not mm:
                            continue
                        raw = mm.group(1).upper()
                        attempts = None if raw == "X" else int(raw)
                        section = mm.group(2)
                        for token in extract_user_tokens(section):
                            uid, uname = await resolve_user(
                                message.guild, token, cache=import_cache, conn=conn
                            )
                            if uid is None:
                                continue
                            results.append((uid, uname, attempts))

                    crown_tokens = []
                    for line in lines:
                        if line.startswith("👑"):
                            for token in extract_user_tokens(line):
                                uid, uname = await resolve_user(
                                    message.guild, token, cache=import_cache, conn=conn
                                )
                                if uid is None:
                                    continue
                                crown_tokens.append((uid, uname))

                    # Insert scores and fails
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

                    # Crowns: prefer explicit 👑 lines, otherwise fall back to best score
                    if crown_tokens:
                        top_users = crown_tokens
                    else:
                        best = min((r[2] for r in results if r[2] is not None), default=None)
                        top_users = [(uid, uname) for uid, uname, a in results if a == best]
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
        name="adjust_crowns",
        description="Add or remove a crown for a user on a specific Wordle",
    )
    @app_commands.describe(
        user="User to adjust",
        wordle_number="Wordle number the crown is for",
        action="add or remove",
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="add", value="add"),
            app_commands.Choice(name="remove", value="remove"),
        ],
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def adjust_crowns(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        wordle_number: int,
        action: app_commands.Choice[str],
    ):
        err = validate_wordle_number(wordle_number)
        if err:
            await interaction.response.send_message(f"❌ {err}", ephemeral=True)
            return

        date = wordle_date_for_number(wordle_number)

        async with self.bot.pg_pool.acquire() as conn:
            if action.value == "add":
                await conn.execute(
                    """
                    INSERT INTO crowns (user_id, username, wordle_number, date)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT DO NOTHING
                    """,
                    user.id, user.display_name, wordle_number, date,
                )
            else:
                await conn.execute(
                    "DELETE FROM crowns WHERE user_id = $1 AND wordle_number = $2",
                    user.id, wordle_number,
                )
            await sync_uncontended_for_wordle(conn, wordle_number)

        verb = "Added" if action.value == "add" else "Removed"
        await interaction.response.send_message(
            f"👑 {verb} crown for {user.mention} on Wordle #{wordle_number}.",
            ephemeral=True,
        )

async def setup(bot):
    await bot.add_cog(AdminCog(bot))