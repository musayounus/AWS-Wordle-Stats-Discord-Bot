import discord

from utils.admin_helpers import NOT_VOIDED_SQL
from utils.range_filters import build_date_filter, build_era_filter

# Penalty attempts value for X/6 fails in avg calculations. NULLs in scores.attempts
# are substituted with this value so fails count against a user's avg.
FAIL_PENALTY = 7


async def generate_leaderboard_embed(
    bot,
    user_id=None,
    exclude_fails=False,
    year=None,
    month=None,
    min_games=None,
    era="current",
):
    where_clause = (
        "WHERE s.user_id NOT IN (SELECT user_id FROM banned_users) "
        f"AND {NOT_VOIDED_SQL.format(alias='s')}"
    )
    date_filter, title_suffix = build_date_filter(year=year, month=month)
    era_filter, era_suffix = build_era_filter(era, column="s.wordle_number")
    min_clause = f"COUNT(*) >= {int(min_games)}" if min_games else "TRUE"
    having_min = f"HAVING {min_clause}" if min_games else ""
    having_min_and = f"AND {min_clause}" if min_games else ""

    # In exclude_fails mode, avg is over successful games only (NULLs skipped);
    # users with no successful games get NULL avg and sort last.
    if exclude_fails:
        avg_expr = "ROUND(AVG(s.attempts) FILTER (WHERE s.attempts IS NOT NULL)::numeric, 2)"
    else:
        avg_expr = f"ROUND(AVG(COALESCE(s.attempts, {FAIL_PENALTY}))::numeric, 2)"

    async with bot.pg_pool.acquire() as conn:
        try:
            leaderboard_rows = await conn.fetch(f"""
                SELECT
                    s.user_id,
                    MAX(s.username) AS username,
                    COUNT(*) AS games_played,
                    COUNT(*) FILTER (WHERE s.attempts IS NULL) AS fails,
                    MIN(s.attempts) FILTER (WHERE s.attempts IS NOT NULL) AS best_score,
                    {avg_expr} AS avg_attempts
                FROM scores s
                {where_clause} {date_filter} {era_filter}
                GROUP BY s.user_id
                {having_min}
                ORDER BY avg_attempts ASC NULLS LAST, games_played DESC
                LIMIT 15
            """)

            user_rank_row = None
            if user_id:
                user_rank_row = await conn.fetchrow(f"""
                    SELECT
                        s.user_id,
                        MAX(s.username) AS username,
                        COUNT(*) AS games_played,
                        COUNT(*) FILTER (WHERE s.attempts IS NULL) AS fails,
                        MIN(s.attempts) FILTER (WHERE s.attempts IS NOT NULL) AS best_score,
                        {avg_expr} AS avg_attempts,
                        RANK() OVER (
                            ORDER BY
                                CASE WHEN {min_clause} THEN {avg_expr} END ASC NULLS LAST,
                                CASE WHEN {min_clause} THEN COUNT(*) END DESC NULLS LAST
                        ) AS rank
                    FROM scores s
                    {where_clause} {date_filter} {era_filter}
                    GROUP BY s.user_id
                    HAVING s.user_id = $1 {having_min_and}
                """, user_id)
        except Exception as e:
            print(f"Error generating leaderboard: {e}")
            raise

    title = "🏆 Wordle Leaderboard"
    title += f" ({title_suffix})" if title_suffix else " (All Time)"
    if era_suffix:
        title += f" — {era_suffix}"
    if exclude_fails:
        title += " — no-fail avg"
    if min_games:
        title += f" — ≥{int(min_games)} games"
    embed = discord.Embed(title=title, color=0x00ff00)

    if not leaderboard_rows:
        embed.description = "No scores yet for this range."
    else:
        for idx, row in enumerate(leaderboard_rows, start=1):
            emoji_best = "🧠" if row['best_score'] == 1 else ""
            emoji_fail = "💀" if row['fails'] > 0 else ""
            
            avg_score = f"{row['avg_attempts']:.2f}" if row['avg_attempts'] is not None else "—"
            best_score = row['best_score'] or "—"
            
            embed.add_field(
                name=f"#{idx} {row['username']}",
                value=(f"Avg: {avg_score} | Best: {best_score} {emoji_best}\n"
                       f"Games: {row['games_played']} | Fails: {row['fails']} {emoji_fail}"),
                inline=False
            )

        if user_rank_row and user_rank_row['user_id'] not in [r['user_id'] for r in leaderboard_rows]:
            avg_score = f"{user_rank_row['avg_attempts']:.2f}" if user_rank_row['avg_attempts'] is not None else "—"
            best_score = user_rank_row['best_score'] or "—"
            emoji_best = "🧠" if user_rank_row['best_score'] == 1 else ""
            emoji_fail = "💀" if user_rank_row['fails'] > 0 else ""
            
            embed.add_field(
                name=f"⬇️ Your Rank: #{user_rank_row['rank']} {user_rank_row['username']}",
                value=(f"Avg: {avg_score} | Best: {best_score} {emoji_best}\n"
                       f"Games: {user_rank_row['games_played']} | Fails: {user_rank_row['fails']} {emoji_fail}"),
                inline=False
            )

    return embed