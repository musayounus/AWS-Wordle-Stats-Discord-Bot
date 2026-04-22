import discord
from discord import app_commands
from discord.ext import commands
from utils.leaderboard import FAIL_PENALTY, generate_leaderboard_embed
from utils.parsing import calculate_streak
from utils.admin_helpers import NOT_VOIDED_SQL, load_voided_set as _load_voided_set
from utils.range_filters import MONTH_CHOICES, RANGE_CHOICES

class LeaderboardCog(commands.Cog):
    """Leaderboard display and personal stats commands."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="leaderboard", description="Show Wordle leaderboard")
    @app_commands.describe(
        range="Relative window: week, month, year (ignored if year/month are set)",
        year="Specific year to filter by (e.g. 2024)",
        month="Specific month to filter by (1–12); combined with year or current year",
        exclude_fails="If true, X/6 fails don't penalize avg (ranking uses successful games only)",
    )
    @app_commands.choices(range=RANGE_CHOICES, month=MONTH_CHOICES)
    async def leaderboard(
        self,
        interaction: discord.Interaction,
        range: app_commands.Choice[str] = None,
        year: app_commands.Range[int, 2021, 2100] = None,
        month: app_commands.Choice[int] = None,
        exclude_fails: bool = False,
    ):
        await interaction.response.defer(thinking=True)
        embed = await generate_leaderboard_embed(
            self.bot,
            user_id=interaction.user.id,
            range=range.value if range else None,
            exclude_fails=exclude_fails,
            year=year,
            month=month.value if month else None,
        )
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="stats", description="View your Wordle stats")
    @app_commands.describe(
        user="Optional user to check (defaults to yourself)",
        exclude_fails="If true, X/6 fails don't penalize avg score",
    )
    async def stats(
        self,
        interaction: discord.Interaction,
        user: discord.User = None,
        exclude_fails: bool = False,
    ):
        await interaction.response.defer(thinking=True)
        target_user = user or interaction.user

        avg_expr = (
            "ROUND(AVG(attempts) FILTER (WHERE attempts IS NOT NULL)::numeric, 2)"
            if exclude_fails
            else f"ROUND(AVG(COALESCE(attempts, {FAIL_PENALTY}))::numeric, 2)"
        )

        async with self.bot.pg_pool.acquire() as conn:
            is_banned = await conn.fetchval("SELECT 1 FROM banned_users WHERE user_id = $1", target_user.id)
            if is_banned:
                await interaction.followup.send("⛔ This user is banned from leaderboards.")
                return

            stats = await conn.fetchrow(f"""
                SELECT
                    COUNT(*) AS games_played,
                    COUNT(*) FILTER (WHERE attempts IS NULL) AS fails,
                    MIN(attempts) FILTER (WHERE attempts IS NOT NULL) AS best_score,
                    {avg_expr} AS avg_score,
                    MAX(date) AS last_game
                FROM scores s
                WHERE s.user_id = $1
                AND s.user_id NOT IN (SELECT user_id FROM banned_users)
                AND {NOT_VOIDED_SQL.format(alias='s')}
            """, target_user.id)

            # Get streak data (only successful attempts)
            rows = await conn.fetch(f"""
                SELECT wordle_number FROM scores s
                WHERE s.user_id = $1 AND s.attempts IS NOT NULL
                AND s.user_id NOT IN (SELECT user_id FROM banned_users)
                AND {NOT_VOIDED_SQL.format(alias='s')}
                ORDER BY wordle_number
            """, target_user.id)

            voided_set = await _load_voided_set(conn, target_user.id)

        streak_count = calculate_streak([r["wordle_number"] for r in rows], voided=voided_set)

        if not stats or stats['games_played'] == 0:
            await interaction.followup.send(
                f"ℹ️ No Wordle scores found for {target_user.display_name}."
            )
            return

        title = f"📊 Wordle Stats for {target_user.display_name}"
        if exclude_fails:
            title += " — no-fail avg"
        embed = discord.Embed(title=title, color=0x3498db)
        
        avg_score = f"{stats['avg_score']:.2f}" if stats['avg_score'] is not None else "—"
        best_score = stats['best_score'] or "—"
        
        embed.add_field(name="Best Score", value=best_score, inline=True)
        embed.add_field(name="Avg Score", value=avg_score, inline=True)
        embed.add_field(name="Fails (X/6)", value=stats['fails'], inline=True)
        embed.add_field(name="Games Played", value=stats['games_played'], inline=True)
        embed.add_field(name="Current Streak", value=streak_count, inline=True)
        embed.add_field(name="Last Played", value=stats['last_game'] or "—", inline=True)

        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(LeaderboardCog(bot))