import discord
from discord import app_commands
from discord.ext import commands

from utils.admin_helpers import NOT_VOIDED_SQL, validate_wordle_number, wordle_date_for_number


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
            rows = await conn.fetch(f"""
                SELECT
                    f.user_id,
                    MAX(f.username) AS display_name,
                    COUNT(*) AS fail_count
                FROM fails f
                WHERE f.user_id NOT IN (SELECT user_id FROM banned_users)
                  AND {NOT_VOIDED_SQL.format(alias='f')}
                GROUP BY f.user_id
                ORDER BY fail_count DESC
                LIMIT 15
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

    @app_commands.command(name="add_fails", description="Add a fail (X/6) for a user on a specific Wordle")
    @app_commands.describe(user="User to adjust", wordle_number="Wordle number")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def add_fails(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        wordle_number: int,
    ):
        err = validate_wordle_number(wordle_number)
        if err:
            await interaction.response.send_message(f"❌ {err}", ephemeral=True)
            return

        date = wordle_date_for_number(wordle_number)

        async with self.bot.pg_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO fails (user_id, username, wordle_number, date)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id, wordle_number) DO NOTHING
                """,
                user.id, user.display_name, wordle_number, date,
            )
            await conn.execute(
                """
                INSERT INTO scores (user_id, username, wordle_number, date, attempts)
                VALUES ($1, $2, $3, $4, NULL)
                ON CONFLICT (username, wordle_number) DO UPDATE
                SET attempts = NULL
                """,
                user.id, user.display_name, wordle_number, date,
            )

        await interaction.response.send_message(
            f"💀 Added fail for {user.mention} on Wordle #{wordle_number}.",
            ephemeral=True,
        )

    @app_commands.command(name="remove_fails", description="Remove a fail (X/6) for a user on a specific Wordle")
    @app_commands.describe(user="User to adjust", wordle_number="Wordle number")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_fails(
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
                "DELETE FROM fails WHERE user_id = $1 AND wordle_number = $2",
                user.id, wordle_number,
            )
            await conn.execute(
                """
                DELETE FROM scores
                WHERE user_id = $1 AND wordle_number = $2 AND attempts IS NULL
                """,
                user.id, wordle_number,
            )

        await interaction.response.send_message(
            f"💀 Removed fail for {user.mention} on Wordle #{wordle_number}.",
            ephemeral=True,
        )

async def setup(bot):
    await bot.add_cog(FailsCog(bot))