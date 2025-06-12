import discord
from discord.ext import commands
from utils.parsing import parse_wordle_message, parse_summary_message

class EventsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore messages sent by bots
        if message.author.bot:
            return

        # Check if the message is in a guild
        if not message.guild:
            return  # Ignore DMs

        # Check if the message might be a Wordle score or a summary
        is_wordle = "Wordle" in message.content
        is_summary = "Here are yesterday's results:" in message.content

        if not is_wordle and not is_summary:
            return  # Not a message we care about

        # Check admin permissions
        member = message.guild.get_member(message.author.id)
        if not member.guild_permissions.administrator:
            await message.reply("❌ Only admins can post Wordle scores or summary messages.")
            return

        # Process messages from admins
        if is_wordle:
            await parse_wordle_message(self.bot, message)
        elif is_summary:
            await parse_summary_message(self.bot, message)

# Load the cog
async def setup(bot):
    await bot.add_cog(EventsCog(bot))