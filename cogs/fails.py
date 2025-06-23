import discord
from discord import app_commands
from discord.ext import commands
import datetime

class FailsCog(commands.Cog):
    """Track and show Wordle fails (X/6)."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="fails_leaderboard",
        description="Show the Wordle fails leaderboard (who's missed Wordle most)"
    )
    async def fails_leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        async with self.bot.pg_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT user_id,
                       MAX(username) AS display_name,
                       COUNT(*) AS fail_count
                FROM fails
                WHERE user_id NOT IN (SELECT user_id FROM banned_users)
                GROUP BY user_id
                ORDER BY fail_count DESC
                LIMIT 10
            """)
        if not rows:
            await interaction.followup.send("💀 No fails recorded yet.")
            return

        embed = discord.Embed(
            title="💀 Wordle Fails Leaderboard",
            color=0xff0000
        )
        for idx, r in enumerate(rows, start=1):
            embed.add_field(
                name=f"#{idx} {r['display_name']}",
                value=f"{r['fail_count']} Fails 💀",
                inline=False
            )
        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="set_fails",
        description="[Admin] Set the number of fails for a user"
    )
    @app_commands.describe(
        user="The user to adjust",
        count="The new fail count"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_fails(self, interaction: discord.Interaction, user: discord.User, count: int):
        if count < 0:
            await interaction.response.send_message("❌ Fail count cannot be negative.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)
        
        async with self.bot.pg_pool.acquire() as conn:
            # Get current fails count
            current_count = await conn.fetchval("""
                SELECT COUNT(*) FROM fails WHERE user_id = $1
            """, user.id) or 0

            difference = count - current_count

            if difference > 0:
                # Add dummy fails
                for i in range(difference):
                    dummy_wordle = 99999 - i  # High number to avoid conflicts
                    await conn.execute("""
                        INSERT INTO fails (user_id, username, wordle_number, date)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT (user_id, wordle_number) DO NOTHING
                    """, user.id, user.display_name, dummy_wordle, datetime.date.today())
            elif difference < 0:
                # Remove oldest fails
                await conn.execute("""
                    DELETE FROM fails
                    WHERE ctid IN (
                        SELECT ctid FROM fails
                        WHERE user_id = $1
                        ORDER BY date ASC
                        LIMIT $2
                    )
                """, user.id, -difference)

            # Ensure corresponding NULL attempts exist in scores table
            await conn.execute("""
                INSERT INTO scores (user_id, username, wordle_number, date, attempts)
                SELECT user_id, username, wordle_number, date, NULL
                FROM fails
                WHERE user_id = $1
                ON CONFLICT (username, wordle_number) DO UPDATE
                SET attempts = NULL
            """, user.id)

        await interaction.followup.send(
            f"✅ Set fail count for {user.mention} to {count}."
        )

async def setup(bot):
    await bot.add_cog(FailsCog(bot))