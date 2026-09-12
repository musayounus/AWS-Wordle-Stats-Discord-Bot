import discord

from utils.admin_helpers import NOT_VOIDED_SQL
from utils.range_filters import build_era_filter, build_window_filter

# Penalty attempts value for X/6 fails in avg calculations. NULLs in scores.attempts
# are substituted with this value so fails count against a user's avg.
FAIL_PENALTY = 7


async def generate_leaderboard_embed(
    bot,
    user_id=None,
    exclude_fails=False,
    year=None,
    month=None,
    quarter=None,
    season="current",
    min_games=None,
    era="current",
    deltas=None,
):
    where_clause = (
        "WHERE s.user_id NOT IN (SELECT user_id FROM banned_users) "
        f"AND {NOT_VOIDED_SQL.format(alias='s')}"
    )
    date_filter, title_suffix = build_window_filter(
        season=season, year=year, month=month, quarter=quarter,
    )
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
                ORDER BY avg_attempts ASC NULLS LAST, games_played DESC, s.user_id ASC
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

            # Trailing, so the arrow always sits at the end of the line
            # regardless of how long the name is.
            arrow = ""
            if deltas:
                d = deltas.get(row["user_id"], 0)
                if d > 0:
                    arrow = f" ⬆️ {d}" if d > 1 else " ⬆️"
                elif d < 0:
                    arrow = f" ⬇️ {-d}" if d < -1 else " ⬇️"

            embed.add_field(
                name=f"#{idx} {row['username']}{arrow}",
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

async def generate_count_board_embed(
    bot, table, title, value_label, colour, empty_message,
    window, era="current", min_games=None,
):
    """Embed for the boards that just count rows per user.

    Crowns, uncontended crowns and fails are the same query: count rows in
    `table` per user over a window, filtered by era, optionally requiring a
    minimum number of games in `scores` over that same window.

    `window` is the dict from range_filters.window_kwargs(). Every table is
    aliased `s`, so all three share one date column.
    """
    alias = "s"
    date_filter, title_suffix = build_window_filter(**window, column=f"{alias}.date")
    scores_date_filter, _ = build_window_filter(**window, column="sc.date")
    era_filter, era_suffix = build_era_filter(era, column=f"{alias}.wordle_number")
    scores_era_filter, _ = build_era_filter(era, column="sc.wordle_number")

    min_games_clause = ""
    if min_games:
        min_games_clause = f"""
            HAVING (
                SELECT COUNT(*) FROM scores sc
                WHERE sc.user_id = {alias}.user_id
                  AND sc.user_id NOT IN (SELECT user_id FROM banned_users)
                  AND {NOT_VOIDED_SQL.format(alias='sc')}
                  {scores_date_filter} {scores_era_filter}
            ) >= {int(min_games)}
        """

    async with bot.pg_pool.acquire() as conn:
        rows = await conn.fetch(f"""
            SELECT
                {alias}.user_id,
                MAX({alias}.username) AS display_name,
                COUNT(*) AS total
            FROM {table} {alias}
            WHERE {alias}.user_id NOT IN (SELECT user_id FROM banned_users)
              AND {NOT_VOIDED_SQL.format(alias=alias)}
              {date_filter} {era_filter}
            GROUP BY {alias}.user_id
            {min_games_clause}
            ORDER BY total DESC, {alias}.user_id ASC
            LIMIT 15
        """)

    if not rows:
        return None, empty_message

    if title_suffix:
        title += f" ({title_suffix})"
    if era_suffix:
        title += f" — {era_suffix}"
    if min_games:
        title += f" — ≥{int(min_games)} games"

    embed = discord.Embed(title=title, color=colour)
    for idx, row in enumerate(rows, start=1):
        embed.add_field(
            name=f"#{idx} {row['display_name']}",
            value=f"{row['total']} {value_label}",
            inline=False,
        )
    return embed, None
