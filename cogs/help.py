import discord
from discord import app_commands
from discord.ext import commands


def _is_admin_only(command) -> bool:
    """Admin commands are marked with default_permissions(administrator=True)."""
    perms = getattr(command, "default_permissions", None)
    return bool(perms and perms.administrator)


def _signature(command) -> str:
    """`/name [param] [param] – description`, built from the live command."""
    params = " ".join(f"[{p.name}]" for p in command.parameters if not p.required)
    required = " ".join(f"<{p.name}>" for p in command.parameters if p.required)
    head = " ".join(x for x in (f"/{command.name}", required, params) if x)
    return f"{head} – {command.description}"


def _command_lines(tree, admin: bool):
    commands_ = [
        c for c in tree.walk_commands()
        if isinstance(c, app_commands.Command) and _is_admin_only(c) == admin
    ]
    return [_signature(c) for c in sorted(commands_, key=lambda c: c.name)]


FIELD_LIMIT = 1024


def add_lines_field(embed, name, lines, footer=""):
    """Add `lines` as one or more fields, respecting Discord's 1024-char cap.

    The generated command list grows with every new command, so a single field
    would silently start failing the whole /help call once it crossed the limit.
    Continuation fields are titled with a zero-width space, which Discord
    accepts as a blank heading.
    """
    chunks, current = [], ""
    for line in list(lines) + ([footer] if footer else []):
        if current and len(current) + len(line) + 1 > FIELD_LIMIT:
            chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)

    for i, chunk in enumerate(chunks):
        embed.add_field(name=name if i == 0 else "​", value=chunk, inline=False)


class HelpCog(commands.Cog):
    """Displays a summary of all Wordle Bot commands and features."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="help", description="View all Wordle Bot commands and features")
    async def help_command(self, interaction: discord.Interaction):
        # Generated from the live command tree so it can never drift from the
        # commands actually registered, the way the old hardcoded list did.
        embed = discord.Embed(
            title="🧩 Wordle Bot Help",
            description="Here's everything you can do with the Wordle Bot:",
            color=0x7289da,
        )

        add_lines_field(
            embed, "🎯 Commands",
            _command_lines(self.bot.tree, admin=False),
            footer=(
                "\n*season: `current` (this quarter, default) or `all` (full era)*\n"
                "*era: `current` (Wordle #1777+, default), `legacy` (pre-#1777) "
                "or `combined` (both eras together)*"
            ),
        )

        embed.add_field(
            name="🤖 Automatic Features",
            value=(
                "• Parses manual Wordle messages (`Wordle 1234 3/6`)\n"
                "• Parses official `/share` embeds and daily summaries\n"
                "• Tracks 👑 crowns (first-place finishes)\n"
                "• Tracks 🥇 uncontested crowns (solo first-place)\n"
                "• Auto-posts leaderboard after each summary\n"
                "• Leaderboards reset each quarter; past seasons stay queryable"
            ),
            inline=False,
        )

        admin_lines = _command_lines(self.bot.tree, admin=True)
        if admin_lines:
            add_lines_field(embed, "🛠️ Admin Tools", admin_lines)

        embed.set_footer(text="Good luck 👍")

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(HelpCog(bot))
