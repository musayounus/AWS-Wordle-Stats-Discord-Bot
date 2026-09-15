import asyncio
from io import BytesIO

import discord
from discord import app_commands
from discord.ext import commands

from utils.admin_helpers import NOT_VOIDED_SQL
from utils.leaderboard import FAIL_PENALTY
from utils.range_filters import (
    MONTH_CHOICES, ERA_CHOICES, QUARTER_CHOICES, SEASON_CHOICES,
    build_era_filter, build_window_filter, window_kwargs,
)

# Row order top to bottom; None is an X/6 fail.
ROWS = [(1, "1"), (2, "2"), (3, "3"), (4, "4"), (5, "5"), (6, "6"), (None, "X")]

BACKGROUND = "#121213"
GREY = "#3a3a3c"
GREEN = "#538d4e"
RED = "#c0392b"


def render_distribution(counts, title):
    """PNG bytes of a Wordle-app style guess distribution.

    `counts` maps attempts (1-6, None for X) to a game count; missing keys are 0.
    Uses Figure directly rather than pyplot, which keeps global state and is not
    safe to call from the worker thread the cog renders on.
    """
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    values = [counts.get(key, 0) for key, _ in ROWS]
    top = max(values) or 1
    peak = max(values[:6])
    # Zero and tiny counts still get a stub wide enough to hold their number.
    widths = [max(v, top * 0.07) for v in values]
    colours = [
        RED if key is None else GREEN if peak and v == peak else GREY
        for (key, _), v in zip(ROWS, values)
    ]

    fig = Figure(figsize=(8, 4.5), dpi=100, facecolor=BACKGROUND)
    FigureCanvasAgg(fig)
    heading = fig.text(0.5, 0.92, title.upper(), ha="center", va="center",
                       color="white", fontsize=16, fontweight="bold")
    # A 32-char display name plus window and "Legacy" can overflow at 16pt, and
    # glyph widths vary too much to guess from len(), so measure and shrink.
    width = heading.get_window_extent(fig.canvas.get_renderer()).width
    max_width = fig.bbox.width * 0.95
    if width > max_width:
        heading.set_fontsize(16 * max_width / width)

    ax = fig.add_axes([0.06, 0.04, 0.9, 0.78])
    ax.set_facecolor(BACKGROUND)
    ax.barh(range(len(ROWS)), widths, color=colours, height=0.72)
    ax.invert_yaxis()
    ax.set_xlim(0, top * 1.01)
    ax.set_xticks([])
    ax.set_yticks(range(len(ROWS)), [label for _, label in ROWS])
    ax.tick_params(axis="y", length=0, colors="white", labelsize=14)
    for tick in ax.get_yticklabels():
        tick.set_fontweight("bold")
    for spine in ax.spines.values():
        spine.set_visible(False)

    for i, (w, v) in enumerate(zip(widths, values)):
        ax.text(w - top * 0.012, i, str(v), ha="right", va="center",
                color="white", fontsize=13, fontweight="bold")

    buf = BytesIO()
    fig.savefig(buf, format="png", facecolor=BACKGROUND)
    return buf.getvalue()


class DistributionCog(commands.Cog):
    """Solve distribution chart for the server or one user."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="distribution", description="Show the Wordle solve distribution as a chart")
    @app_commands.describe(
        user="Only this user's games (defaults to everyone)",
        year="Specific year to filter by (e.g. 2024)",
        month="Specific month to filter by (1–12); combined with year or current year",
        quarter="Specific quarter to show (uses current year if year is omitted; overrides month)",
        season="current season (default) or all for the full era",
        era="current (Wordle #1777+, default) or legacy (pre-#1777)",
    )
    @app_commands.choices(
        month=MONTH_CHOICES, era=ERA_CHOICES,
        season=SEASON_CHOICES, quarter=QUARTER_CHOICES,
    )
    async def distribution(
        self,
        interaction: discord.Interaction,
        user: discord.User = None,
        year: app_commands.Range[int, 2021, 2100] = None,
        month: app_commands.Choice[int] = None,
        quarter: app_commands.Choice[int] = None,
        season: app_commands.Choice[str] = None,
        era: app_commands.Choice[str] = None,
    ):
        await interaction.response.defer(thinking=True)
        era_value = era.value if era else "current"
        date_filter, window_suffix = build_window_filter(
            **window_kwargs(season=season, year=year, month=month, quarter=quarter),
            era=era_value,
        )
        era_filter, era_suffix = build_era_filter(era_value, column="s.wordle_number")
        user_clause, args = ("AND s.user_id = $1", [user.id]) if user else ("", [])
        where = f"""
            WHERE s.user_id NOT IN (SELECT user_id FROM banned_users)
              AND {NOT_VOIDED_SQL.format(alias='s')}
              {date_filter} {era_filter} {user_clause}
        """

        async with self.bot.pg_pool.acquire() as conn:
            if user and await conn.fetchval("SELECT 1 FROM banned_users WHERE user_id = $1", user.id):
                await interaction.followup.send("⛔ This user is banned from leaderboards.")
                return
            rows = await conn.fetch(
                f"SELECT s.attempts, COUNT(*) AS n FROM scores s {where} GROUP BY s.attempts", *args,
            )
            players = await conn.fetchval(
                f"SELECT COUNT(DISTINCT s.user_id) FROM scores s {where}", *args,
            )

        if not rows:
            await interaction.followup.send("No scores yet for this range.")
            return

        counts = {r["attempts"]: r["n"] for r in rows}
        total = sum(counts.values())
        avg = sum((k or FAIL_PENALTY) * n for k, n in counts.items()) / total

        window = window_suffix or "All Time"
        heading = ["Guess Distribution", window]
        title = f"📊 Solve Distribution ({window})"
        if user:
            heading.append(user.display_name)
            title += f" — {user.display_name}"
        if era_suffix:
            heading.append(era_suffix)
            title += f" — {era_suffix}"

        png = await asyncio.to_thread(render_distribution, counts, " · ".join(heading))

        embed = discord.Embed(
            title=title,
            description=" · ".join(f"{label}: {counts.get(key, 0)}" for key, label in ROWS),
            color=0x538d4e,
        )
        embed.set_image(url="attachment://distribution.png")
        footer = f"{total} games · avg {avg:.2f}"
        if not user:
            footer += f" · {players} players"
        embed.set_footer(text=footer)

        await interaction.followup.send(
            embed=embed, file=discord.File(BytesIO(png), filename="distribution.png"),
        )


async def setup(bot):
    await bot.add_cog(DistributionCog(bot))
