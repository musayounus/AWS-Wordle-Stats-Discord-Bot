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
                SELECT 
                    user_id,
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
                    dummy_wordle = 99999 - i
                    await conn.execute("""
                        INSERT INTO fails (user_id, username, wordle_number, date)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT (user_id, wordle_number) DO NOTHING
                    """, user.id, user.display_name, dummy_wordle, datetime.date.today())
                    
                    # Ensure corresponding NULL attempt exists in scores
                    await conn.execute("""
                        INSERT INTO scores (user_id, username, wordle_number, date, attempts)
                        VALUES ($1, $2, $3, $4, NULL)
                        ON CONFLICT (username, wordle_number) DO UPDATE
                        SET attempts = NULL
                    """, user.id, user.display_name, dummy_wordle, datetime.date.today())
            elif difference < 0:
                # Remove oldest fails from both tables
                await conn.execute("""
                    DELETE FROM fails
                    WHERE (user_id, wordle_number) IN (
                        SELECT user_id, wordle_number FROM fails
                        WHERE user_id = $1
                        ORDER BY date ASC
                        LIMIT $2
                    )
                """, user.id, -difference)
                
                await conn.execute("""
                    DELETE FROM scores
                    WHERE (user_id, wordle_number) IN (
                        SELECT user_id, wordle_number FROM fails
                        WHERE user_id = $1
                        ORDER BY date ASC
                        LIMIT $2
                    )
                """, user.id, -difference)

        await interaction.followup.send(
            f"✅ Set fail count for {user.mention} to {count}."
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author == self.bot.user:
            return

        # Handle summary messages
        if "Here are yesterday's results:" in message.content:
            await self.update_fails_from_summary(message)

    async def update_fails_from_summary(self, message: discord.Message):
        lines = message.content.split('\n')
        date = message.created_at.date() - datetime.timedelta(days=1)
        
        for line in lines:
            if "X/6:" in line:
                # Extract user mentions
                for mention in message.mentions:
                    if f"@{mention.display_name}" in line or f"<@{mention.id}>" in line:
                        async with self.bot.pg_pool.acquire() as conn:
                            # Get the Wordle number for this date
                            wordle_number = await conn.fetchval("""
                                SELECT wordle_number FROM scores
                                WHERE date = $1 LIMIT 1
                            """, date)
                            
                            if wordle_number:
                                # Record fail in both tables
                                await conn.execute("""
                                    INSERT INTO fails (user_id, username, wordle_number, date)
                                    VALUES ($1, $2, $3, $4)
                                    ON CONFLICT (user_id, wordle_number) DO NOTHING
                                """, mention.id, mention.display_name, wordle_number, date)
                                
                                await conn.execute("""
                                    INSERT INTO scores (user_id, username, wordle_number, date, attempts)
                                    VALUES ($1, $2, $3, $4, NULL)
                                    ON CONFLICT (username, wordle_number) DO UPDATE
                                    SET attempts = NULL
                                """, mention.id, mention.display_name, wordle_number, date)

async def setup(bot):
    await bot.add_cog(FailsCog(bot))