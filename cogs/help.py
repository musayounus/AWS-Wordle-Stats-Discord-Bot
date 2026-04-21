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
                "/leaderboard [range] – View top players (all time, week, month)\n"
                "/stats [user] – See detailed personal Wordle stats\n"
                "/streak – Show your current streak\n"
                "/streaks – View top 10 current streaks\n"
                "/crowns – See how many 👑 crowns each user has\n"
                "/uncontended – See how many 🥇 uncontested crowns each user has"
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
                "/unban_user – Unban a previously banned user"
            ),
            inline=False
        )

        embed.set_footer(text="Good luck 👍")

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(HelpCog(bot))