import discord
from discord import app_commands
from discord.ext import commands

class UncontendedCrownsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="uncontended", description="Show the uncontended crowns leaderboard.")
    async def uncontended_crowns(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        async with self.bot.pg_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT uc.user_id, uc.count, MAX(u.username) AS username
                FROM uncontended_crowns uc
                LEFT JOIN (
                    SELECT user_id, MAX(username) AS username 
                    FROM crowns 
                    GROUP BY user_id
                ) u ON uc.user_id = u.user_id
                WHERE uc.user_id NOT IN (SELECT user_id FROM banned_users)
                GROUP BY uc.user_id, uc.count
                ORDER BY uc.count DESC
                LIMIT 10
            """)
            
            if not rows:
                await interaction.followup.send("🥇 No uncontended data available yet.")
                return

            leaderboard = ""
            for i, row in enumerate(rows, 1):
                user = interaction.guild.get_member(row["user_id"])
                name = user.display_name if user else row["username"] or f"User ID {row['user_id']}"
                leaderboard += f"**{i}.** 🥇 {name} — `{row['count']}`\n"

            embed = discord.Embed(
                title="🥇 Uncontended Leaderboard 🥇",
                description=leaderboard,
                color=discord.Color.gold()
            )
            await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(UncontendedCrownsCog(bot))