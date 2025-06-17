import discord
from discord.ext import commands
from discord import app_commands

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
                "/uncontended_crowns – See how many 🥇 uncontested crowns each user has"
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
                "• Auto‑posts leaderboard after each summary\n"
                "• Auto‑posts daily predictions based on past averages"
            ),
            inline=False
        )

        # Admin Tools
        embed.add_field(
            name="🛠️ Admin Tools",
            value=(
                "/import – Bulk import historical Wordle messages\n"
                "/resetleaderboard – Reset all scores, crowns, uncontended crowns\n"
                "/removescores – Remove specific scores for a user\n"
                "/banuser – Ban a user from appearing in stats/leaderboard\n"
                "/unbanuser – Unban a previously banned user\n"
                "/set_uncontended_crowns – Set a user’s uncontested crown count\n"
                "/adjust_crowns – Add or remove raw crown events for a user"
            ),
            inline=False
        )

        embed.set_footer(text="Good luck, and happy Wordling! 👍")

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(HelpCog(bot))