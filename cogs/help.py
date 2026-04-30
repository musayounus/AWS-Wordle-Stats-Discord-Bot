import discord
from discord import app_commands
from discord.ext import commands

class HelpCog(commands.Cog):
    """Displays a summary of all Wordle Bot commands and features."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="help", description="View all Wordle Bot commands and features")
    async def help_command(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🧩 Wordle Bot Help",
            description="Here’s everything you can do with the Wordle Bot:",
            color=0x7289da
        )

        # Gameplay & Stats
        embed.add_field(
            name="🎯 Gameplay & Stats",
            value=(
                "/leaderboard [year] [month] [exclude_fails] [min_games] [era] – Top players\n"
                "/stats [user] [exclude_fails] [era] – See detailed personal Wordle stats\n"
                "/crowns [year] [month] [min_games] [era] – 👑 crown leaderboard\n"
                "/uncontended [year] [month] [min_games] [era] – 🥇 uncontested crown leaderboard\n"
                "/fails_leaderboard [year] [month] [min_games] [era] – 💀 fails leaderboard\n"
                "/monthly_winners [era] – 🏆 1st-place winner of each past month\n"
                "/streak – 🔥 Show your current Wordle streak (current era only)\n"
                "/streaks – 🔥 Top 15 streaks (current era only)\n"
                "*era: `current` (Wordle #1777+, default) or `legacy` (pre-#1777)*"
            ),
            inline=False
        )

        # Automatic Features
        embed.add_field(
            name="🤖 Automatic Features",
            value=(
                "• Parses manual Wordle messages (`Wordle 1234 3/6`)\n"
                "• Parses official `/share` embeds and daily summaries\n"
                "• Tracks 👑 crowns (first‑place finishes)\n"
                "• Tracks 🥇 uncontested crowns (solo first‑place)\n"
                "• Auto‑posts leaderboard after each summary"
            ),
            inline=False
        )

        # Admin Tools
        embed.add_field(
            name="🛠️ Admin Tools",
            value=(
                "/import – Bulk import historical Wordle messages\n"
                "/reset_leaderboard – Reset all scores, crowns, uncontended crowns\n"
                "/add_scores, /remove_scores – Set or delete a user's score for a Wordle\n"
                "/add_fails, /remove_fails – Set or delete a user's fail for a Wordle\n"
                "/add_crowns, /remove_crowns – Award or remove a user's crown for a Wordle\n"
                "/ban_user – Ban a user from appearing in stats/leaderboard\n"
                "/unban_user – Unban a previously banned user\n"
                "/void_wordle, /unvoid_wordle – Void a whole Wordle day so no one's stats are affected (e.g. spoiler)\n"
                "/voided_wordles – List all currently voided Wordle days\n"
                "/void_user_wordle, /unvoid_user_wordle – Void one user's result on a specific Wordle (e.g. cheating)\n"
                "/voided_user_wordles – List per-user voided Wordle results"
            ),
            inline=False
        )

        embed.set_footer(text="Good luck 👍")

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(HelpCog(bot))