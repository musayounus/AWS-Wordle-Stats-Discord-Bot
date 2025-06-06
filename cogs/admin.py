from discord.ext import commands
from discord import app_commands, Interaction
from db.queries import reset_leaderboard, ban_user, unban_user, remove_scores

class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="resetleaderboard", description="Reset the Wordle leaderboard")
    @app_commands.checks.has_permissions(administrator=True)
    async def resetleaderboard(self, interaction: Interaction):
        await interaction.response.send_message("⚠️ Are you sure you want to reset the leaderboard? Type `yes` within 30s to confirm reset.")
        def check(m): return m.author.id == interaction.user.id and m.content.lower() == "yes"
        try:
            await self.bot.wait_for("message", timeout=30.0, check=check)
            async with self.bot.pg_pool.acquire() as conn:
                await reset_leaderboard(conn)
            await interaction.followup.send("✅ Leaderboard reset.")
        except Exception:
            await interaction.followup.send("❌ Reset cancelled or failed.")

    @app_commands.command(name="banuser", description="Ban a user from leaderboard and stats")
    @app_commands.describe(user="User to ban")
    @app_commands.checks.has_permissions(administrator=True)
    async def banuser(self, interaction: Interaction, user):
        async with self.bot.pg_pool.acquire() as conn:
            await ban_user(conn, user.id, user.display_name)
        await interaction.response.send_message(f"🚫 {user.mention} has been banned.")

    @app_commands.command(name="unbanuser", description="Unban a previously banned user")
    @app_commands.describe(user="User to unban")
    @app_commands.checks.has_permissions(administrator=True)
    async def unbanuser(self, interaction: Interaction, user):
        async with self.bot.pg_pool.acquire() as conn:
            await unban_user(conn, user.id)
        await interaction.response.send_message(f"✅ {user.mention} has been unbanned.")

    @app_commands.command(name="removescores", description="Remove multiple Wordle scores from a user")
    @app_commands.describe(
        user="User to remove scores for",
        wordle_numbers="Comma-separated Wordle numbers (e.g. 123,124,125)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def removescores(self, interaction: Interaction, user, wordle_numbers: str):
        numbers = [int(num.strip()) for num in wordle_numbers.split(",") if num.strip().isdigit()]
        async with self.bot.pg_pool.acquire() as conn:
            deleted_rows = await remove_scores(conn, user.id, numbers)
        deleted_count = len(deleted_rows)
        await interaction.response.send_message(
            f"✅ Removed {deleted_count} out of {len(numbers)} requested scores for {user.mention}.",
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(AdminCog(bot))