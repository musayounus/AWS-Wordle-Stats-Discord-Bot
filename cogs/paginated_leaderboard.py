import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button

from db.queries import get_leaderboard_page, get_leaderboard_count

PAGE_SIZE = 10

class LeaderboardView(View):
    def __init__(self, bot, range, total):
        super().__init__(timeout=180)
        self.bot = bot
        self.range = range
        self.total = total
        self.page = 0
        self.max_page = max((total - 1) // PAGE_SIZE, 0)

    async def update_message(self, interaction: discord.Interaction):
        offset = self.page * PAGE_SIZE
        async with self.bot.pg_pool.acquire() as conn:
            rows = await get_leaderboard_page(conn, self.range, PAGE_SIZE, offset)

        title = {
            None: "🏆 Wordle Leaderboard (All Time)",
            "week": "📅 Wordle Leaderboard (Last 7 Days)",
            "month": "🗓️ Wordle Leaderboard (This Month)"
        }[self.range]

        embed = discord.Embed(
            title=f"{title} — Page {self.page + 1}/{self.max_page + 1}",
            color=0x00ff00
        )

        if not rows:
            embed.description = "No scores for this page."
        else:
            for idx, row in enumerate(rows, start=offset + 1):
                emoji_best = "🧠" if row['best_score'] == 1 else ""
                emoji_fail = "💀" if row['fails'] > 0 else ""
                embed.add_field(
                    name=f"#{idx} {row['username']}",
                    value=(
                        f"Avg: {row['avg_attempts']:.2f} | Best: {row['best_score'] or '—'} {emoji_best}\n"
                        f"Games: {row['games_played']} | Fails: {row['fails']} {emoji_fail}"
                    ),
                    inline=False
                )

        await interaction.response.edit_message(embed=embed, view=self)

    @Button(label="⬅️ Prev", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: Button):
        if self.page > 0:
            self.page -= 1
            await self.update_message(interaction)
        else:
            await interaction.response.defer()

    @Button(label="Next ➡️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: Button):
        if self.page < self.max_page:
            self.page += 1
            await self.update_message(interaction)
        else:
            await interaction.response.defer()

    @Button(label="All Time", style=discord.ButtonStyle.primary)
    async def alltime_button(self, interaction: discord.Interaction, button: Button):
        self.range = None
        self.page = 0
        async with self.bot.pg_pool.acquire() as conn:
            self.total = await get_leaderboard_count(conn, None)
            self.max_page = max((self.total - 1)//PAGE_SIZE, 0)
        await self.update_message(interaction)

    @Button(label="Last 7d", style=discord.ButtonStyle.primary)
    async def week_button(self, interaction: discord.Interaction, button: Button):
        self.range = "week"
        self.page = 0
        async with self.bot.pg_pool.acquire() as conn:
            self.total = await get_leaderboard_count(conn, "week")
            self.max_page = max((self.total - 1)//PAGE_SIZE, 0)
        await self.update_message(interaction)

    @Button(label="This Month", style=discord.ButtonStyle.primary)
    async def month_button(self, interaction: discord.Interaction, button: Button):
        self.range = "month"
        self.page = 0
        async with self.bot.pg_pool.acquire() as conn:
            self.total = await get_leaderboard_count(conn, "month")
            self.max_page = max((self.total - 1)//PAGE_SIZE, 0)
        await self.update_message(interaction)


class PaginatedLeaderboardCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="pleaderboard",
        description="Paginated Wordle leaderboard (buttons)."
    )
    @app_commands.describe(range="Filter by: week, month, or leave empty for all-time")
    async def pleaderboard(self, interaction: discord.Interaction, range: str = None):
        """Send a paginated leaderboard view with filter buttons."""
        async with self.bot.pg_pool.acquire() as conn:
            total = await get_leaderboard_count(conn, range)

        view = LeaderboardView(self.bot, range, total)
        # send initial stub, then immediately update it
        await interaction.response.send_message("Loading leaderboard…", view=view)
        await view.update_message(interaction)


async def setup(bot):
    await bot.add_cog(PaginatedLeaderboardCog(bot))