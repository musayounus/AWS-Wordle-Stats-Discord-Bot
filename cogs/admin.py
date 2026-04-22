import discord
from discord import app_commands
from discord.ext import commands
import datetime
import re
import asyncio
from zoneinfo import ZoneInfo

import config
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
    @app_commands.default_permissions(administrator=True)
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
                await conn.execute("DELETE FROM summary_log")
            await interaction.followup.send("✅ Leaderboard reset.")
        except asyncio.TimeoutError:
            await interaction.followup.send("❌ Reset cancelled.")
        except Exception as e:
            await interaction.followup.send(f"❌ Reset failed: {e}")

    @app_commands.command(name="ban_user", description="Ban a user from leaderboard and stats")
    @app_commands.describe(user="User to ban")
    @app_commands.default_permissions(administrator=True)
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
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def unbanuser(self, interaction: discord.Interaction, user: discord.User):
        async with self.bot.pg_pool.acquire() as conn:
            try:
                await conn.execute("DELETE FROM banned_users WHERE user_id = $1", user.id)
                await interaction.response.send_message(f"✅ {user.mention} has been unbanned.")
            except Exception as e:
                await interaction.response.send_message(f"❌ Failed to unban user: {e}", ephemeral=True)

    @app_commands.command(name="add_scores", description="Add a Wordle score for a user")
    @app_commands.describe(
        user="User to adjust",
        wordle_number="Wordle number",
        attempts="Attempts (1-6 or X for fail)",
        crown="Also award the crown for this Wordle",
    )
    @app_commands.choices(
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
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def add_scores(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        wordle_number: int,
        attempts: app_commands.Choice[str],
        crown: bool = False,
    ):
        err = validate_wordle_number(wordle_number)
        if err:
            await interaction.response.send_message(f"❌ {err}", ephemeral=True)
            return

        date = wordle_date_for_number(wordle_number)
        attempts_val = None if attempts.value == "X" else int(attempts.value)
        label = "X/6" if attempts_val is None else f"{attempts_val}/6"

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

            if not crown:
                await interaction.response.send_message(
                    f"✅ Set {user.mention}'s Wordle #{wordle_number} score to **{label}**.",
                    ephemeral=True,
                )
                return

            already = await conn.fetchval(
                "SELECT 1 FROM crowns WHERE user_id = $1 AND wordle_number = $2",
                user.id, wordle_number,
            )
            if already:
                await interaction.response.send_message(
                    f"✅ Set {user.mention}'s Wordle #{wordle_number} score to **{label}**. "
                    f"ℹ️ Already holds a crown for #{wordle_number} — crown unchanged.",
                    ephemeral=True,
                )
                return
            await conn.execute(
                """
                INSERT INTO crowns (user_id, username, wordle_number, date)
                VALUES ($1, $2, $3, $4)
                """,
                user.id, user.display_name, wordle_number, date,
            )
            await sync_uncontended_for_wordle(conn, wordle_number)

        await interaction.response.send_message(
            f"✅ Set {user.mention}'s Wordle #{wordle_number} score to **{label}** and awarded 👑.",
            ephemeral=True,
        )

    @app_commands.command(name="remove_scores", description="Remove a Wordle score for a user")
    @app_commands.describe(user="User to adjust", wordle_number="Wordle number")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_scores(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        wordle_number: int,
    ):
        err = validate_wordle_number(wordle_number)
        if err:
            await interaction.response.send_message(f"❌ {err}", ephemeral=True)
            return

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
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def import_scores(self, interaction: discord.Interaction):
        await interaction.response.send_message("⏳ Scanning channel messages for Wordle scores...")
        count = 0
        fail_count = 0
        crown_count = 0
        uc_count = 0
        reject_count = 0
        channel = interaction.channel
        wordle_start = datetime.date(2021, 6, 19)
        import_cache: dict = {}

        # Chain anchor for summary processing: seed from any existing
        # summary_log rows so re-runs interleave correctly. Reset wipes this
        # table, so a fresh import starts with None.
        async with self.bot.pg_pool.acquire() as conn:
            last_summary_wordle = await conn.fetchval(
                "SELECT MAX(wordle_number) FROM summary_log"
            )

        async for message in channel.history(limit=None, oldest_first=True):
            content = message.content

            # Direct manual submissions
            m = re.search(r'Wordle\s+(\d+)\s+(\d|X)/6', content, re.IGNORECASE)
            if m:
                if message.author.bot or message.author.display_name.lower() in ("wordle bot", "wordle"):
                    continue
                wn = int(m.group(1))
                if validate_wordle_number(wn):
                    reject_count += 1
                    continue
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

            # Summary messages — only from the official Wordle Discord app
            if "Here are yesterday's results:" in content:
                if message.author.id != config.OFFICIAL_WORDLE_BOT_ID:
                    continue
                local_date = message.created_at.astimezone(ZoneInfo(config.WORDLE_TZ)).date()
                tentative_date = local_date - datetime.timedelta(days=1)
                tentative_wn = (tentative_date - wordle_start).days

                # Chain: second summary on same KSA day represents next wordle.
                if last_summary_wordle is not None and tentative_wn <= last_summary_wordle:
                    wn = last_summary_wordle + 1
                    date = wordle_start + datetime.timedelta(days=wn)
                else:
                    wn = tentative_wn
                    date = tentative_date

                streak_match = re.search(r"(\d+)\s*day streak", content)
                group_streak = int(streak_match.group(1)) if streak_match else None

                lines = content.strip().splitlines()
                pattern = re.compile(r"(\d|X)/6:\s+(.*)")

                async with self.bot.pg_pool.acquire() as conn:
                    already = await conn.fetchval(
                        "SELECT wordle_number FROM summary_log WHERE message_id = $1",
                        message.id,
                    )
                    if already is not None:
                        last_summary_wordle = max(last_summary_wordle or already, already)
                        continue

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

                    await conn.execute(
                        """
                        INSERT INTO summary_log (message_id, posted_at, wordle_number, group_streak)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT (message_id) DO NOTHING
                        """,
                        message.id, message.created_at, wn, group_streak,
                    )
                    last_summary_wordle = wn

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

        summary = (
            f"✅ Import complete. {real_scores} scores, {real_fails} fails, "
            f"{real_crowns} crowns, {real_uc} uncontended crowns."
        )
        if reject_count:
            summary += f" Rejected {reject_count} out-of-range wordle numbers."
        await interaction.followup.send(summary)

    @app_commands.command(name="add_crowns", description="Award a crown to a user for a specific Wordle")
    @app_commands.describe(
        user="User to adjust",
        wordle_number="Wordle number the crown is for",
        attempts="If provided, also set the user's score for this Wordle",
    )
    @app_commands.choices(
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
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def add_crowns(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        wordle_number: int,
        attempts: Optional[app_commands.Choice[str]] = None,
    ):
        err = validate_wordle_number(wordle_number)
        if err:
            await interaction.response.send_message(f"❌ {err}", ephemeral=True)
            return

        date = wordle_date_for_number(wordle_number)

        async with self.bot.pg_pool.acquire() as conn:
            already = await conn.fetchval(
                "SELECT 1 FROM crowns WHERE user_id = $1 AND wordle_number = $2",
                user.id, wordle_number,
            )
            if already:
                await interaction.response.send_message(
                    f"ℹ️ {user.mention} already holds a crown for Wordle #{wordle_number} — no change.",
                    ephemeral=True,
                )
                return

            if attempts is not None:
                attempts_val = None if attempts.value == "X" else int(attempts.value)
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

            await conn.execute(
                """
                INSERT INTO crowns (user_id, username, wordle_number, date)
                VALUES ($1, $2, $3, $4)
                """,
                user.id, user.display_name, wordle_number, date,
            )
            await sync_uncontended_for_wordle(conn, wordle_number)

        if attempts is not None:
            label = "X/6" if attempts.value == "X" else f"{attempts.value}/6"
            await interaction.response.send_message(
                f"👑 Awarded crown to {user.mention} for Wordle #{wordle_number} (score: **{label}**).",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"👑 Awarded crown to {user.mention} for Wordle #{wordle_number}.",
                ephemeral=True,
            )

    @app_commands.command(name="remove_crowns", description="Remove a user's crown for a specific Wordle")
    @app_commands.describe(user="User to adjust", wordle_number="Wordle number")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_crowns(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        wordle_number: int,
    ):
        err = validate_wordle_number(wordle_number)
        if err:
            await interaction.response.send_message(f"❌ {err}", ephemeral=True)
            return

        async with self.bot.pg_pool.acquire() as conn:
            existing = await conn.fetchval(
                "SELECT 1 FROM crowns WHERE user_id = $1 AND wordle_number = $2",
                user.id, wordle_number,
            )
            if not existing:
                await interaction.response.send_message(
                    f"ℹ️ {user.mention} didn't hold a crown for Wordle #{wordle_number} — no change.",
                    ephemeral=True,
                )
                return
            await conn.execute(
                "DELETE FROM crowns WHERE user_id = $1 AND wordle_number = $2",
                user.id, wordle_number,
            )
            await sync_uncontended_for_wordle(conn, wordle_number)

        await interaction.response.send_message(
            f"🗑️ Removed {user.mention}'s crown for Wordle #{wordle_number}.",
            ephemeral=True,
        )

    @app_commands.command(name="void_wordle", description="Void a Wordle day — results won't count for anyone")
    @app_commands.describe(wordle_number="Wordle number to void", reason="Why this day is being voided (optional)")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def void_wordle(
        self,
        interaction: discord.Interaction,
        wordle_number: int,
        reason: Optional[str] = None,
    ):
        err = validate_wordle_number(wordle_number)
        if err:
            await interaction.response.send_message(f"❌ {err}", ephemeral=True)
            return
        async with self.bot.pg_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO voided_wordles (wordle_number, reason)
                VALUES ($1, $2)
                ON CONFLICT (wordle_number) DO UPDATE SET reason = EXCLUDED.reason
                """,
                wordle_number, reason,
            )
        reason_str = reason or "not specified"
        await interaction.response.send_message(
            f"🚫 **Wordle {wordle_number} voided.** Results for this day will not count toward anyone's stats. "
            f"Reason: {reason_str}."
        )

    @app_commands.command(name="unvoid_wordle", description="Un-void a Wordle day — results count again")
    @app_commands.describe(wordle_number="Wordle number to un-void")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def unvoid_wordle(self, interaction: discord.Interaction, wordle_number: int):
        async with self.bot.pg_pool.acquire() as conn:
            existed = await conn.fetchval(
                "DELETE FROM voided_wordles WHERE wordle_number = $1 RETURNING wordle_number",
                wordle_number,
            )
            if existed is None:
                await interaction.response.send_message(
                    f"ℹ️ Wordle {wordle_number} was not voided — no change.", ephemeral=True
                )
                return
            await sync_uncontended_for_wordle(conn, wordle_number)
        await interaction.response.send_message(
            f"✅ **Wordle {wordle_number} unvoided.** Results for this day now count again."
        )

    @app_commands.command(name="voided_wordles", description="List all voided Wordle days")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def voided_wordles_list(self, interaction: discord.Interaction):
        async with self.bot.pg_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT wordle_number, voided_at, reason FROM voided_wordles ORDER BY wordle_number DESC"
            )
        if not rows:
            await interaction.response.send_message("No wordles are currently voided.", ephemeral=True)
            return
        embed = discord.Embed(title="🚫 Voided Wordles", color=0xff0000)
        for r in rows[:25]:
            reason = r["reason"] or "not specified"
            voided_at = r["voided_at"].strftime("%Y-%m-%d") if r["voided_at"] else "—"
            embed.add_field(
                name=f"Wordle #{r['wordle_number']}",
                value=f"Reason: {reason}\nVoided: {voided_at}",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="void_user_wordle", description="Void one user's result on a specific Wordle (e.g. cheating)")
    @app_commands.describe(
        user="User whose result is being voided",
        wordle_number="Wordle number",
        reason="Why this result is being voided (optional)",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def void_user_wordle(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        wordle_number: int,
        reason: Optional[str] = None,
    ):
        err = validate_wordle_number(wordle_number)
        if err:
            await interaction.response.send_message(f"❌ {err}", ephemeral=True)
            return
        async with self.bot.pg_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO voided_user_wordles (user_id, wordle_number, reason)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id, wordle_number) DO UPDATE SET reason = EXCLUDED.reason
                """,
                user.id, wordle_number, reason,
            )
            await sync_uncontended_for_wordle(conn, wordle_number)
        reason_str = reason or "not specified"
        await interaction.response.send_message(
            f"🚫 **{user.mention}'s result for Wordle {wordle_number} has been voided.** "
            f"Reason: {reason_str}."
        )

    @app_commands.command(name="unvoid_user_wordle", description="Restore one user's voided Wordle result")
    @app_commands.describe(user="User to restore", wordle_number="Wordle number")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def unvoid_user_wordle(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        wordle_number: int,
    ):
        async with self.bot.pg_pool.acquire() as conn:
            existed = await conn.fetchval(
                "DELETE FROM voided_user_wordles WHERE user_id = $1 AND wordle_number = $2 RETURNING wordle_number",
                user.id, wordle_number,
            )
            if existed is None:
                await interaction.response.send_message(
                    f"ℹ️ {user.mention}'s result for Wordle {wordle_number} was not voided — no change.",
                    ephemeral=True,
                )
                return
            await sync_uncontended_for_wordle(conn, wordle_number)
        await interaction.response.send_message(
            f"✅ **{user.mention}'s result for Wordle {wordle_number} has been restored.**"
        )

    @app_commands.command(name="voided_user_wordles", description="List per-user voided Wordle results")
    @app_commands.describe(user="Filter to a specific user (optional)")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def voided_user_wordles_list(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.User] = None,
    ):
        async with self.bot.pg_pool.acquire() as conn:
            if user is not None:
                rows = await conn.fetch(
                    "SELECT user_id, wordle_number, voided_at, reason "
                    "FROM voided_user_wordles WHERE user_id = $1 "
                    "ORDER BY wordle_number DESC",
                    user.id,
                )
            else:
                rows = await conn.fetch(
                    "SELECT user_id, wordle_number, voided_at, reason "
                    "FROM voided_user_wordles ORDER BY wordle_number DESC"
                )
        if not rows:
            await interaction.response.send_message(
                "No per-user voids to show.", ephemeral=True
            )
            return
        embed = discord.Embed(title="🚫 Per-User Voided Wordles", color=0xff0000)
        for r in rows[:25]:
            reason = r["reason"] or "not specified"
            voided_at = r["voided_at"].strftime("%Y-%m-%d") if r["voided_at"] else "—"
            embed.add_field(
                name=f"<@{r['user_id']}> — Wordle #{r['wordle_number']}",
                value=f"Reason: {reason}\nVoided: {voided_at}",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(AdminCog(bot))