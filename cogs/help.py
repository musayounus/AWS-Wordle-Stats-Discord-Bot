import discord
from discord.ext import commands
from discord import app_commands

class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="help", description="View all Wordle Bot commands and features")
    async def help_command(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🧩 Wordle Bot Help",
            description="Here’s everything you can do with the Wordle Bot:",
            color=0x7289da
        )
        embed.add_field(
            name="🎯 Gameplay & Stats",
            value=(
                "/leaderboard [range] – View top players (all time, week, month)\n"
                "/stats [user] – See detailed personal Wordle stats\n"
                "/streak – Show your current streak\n"
                "/streaks – View top 10 current streaks\n"
                "/crowns – See how many 👑 wins each user has\n"
            ),
            inline=False
        )
        embed.add_field(
            name="🤖 Automatic Features",
            value=(
                "• Parses Wordle messages\n"
                "• Tracks 👑 top scorers, 💀 fails, 🧠 personal bests\n"
                "• Auto-posts daily predictions\n"
                "• Auto-posts leaderboard after daily summary"
            ),
            inline=False
        )
        embed.add_field(
            name="🛠️ Admin Tools",
            value=(
                "/import – Import historical messages (bulk)\n"
                "/resetleaderboard – Reset all scores\n"
                "/removescores – Remove specific scores from a user\n"
                "/banuser – Ban a user from appearing in leaderboards/stats\n"
                "/unbanuser – Unban a previously banned user"
            ),
            inline=False
        )
        embed.set_footer(text="Good Luck Brev 👍")
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(HelpCog(bot))