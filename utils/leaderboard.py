import discord

# Penalty attempts value for X/6 fails in avg calculations. NULLs in scores.attempts
# are substituted with this value so fails count against a user's avg.
FAIL_PENALTY = 7


async def generate_leaderboard_embed(bot, user_id=None, range=None):
    where_clause = "WHERE s.user_id NOT IN (SELECT user_id FROM banned_users)"
    date_filter = ""

    if range == "week":
        date_filter = "AND s.date >= CURRENT_DATE - INTERVAL '7 days'"
    elif range == "month":
        date_filter = "AND date_trunc('month', s.date) = date_trunc('month', CURRENT_DATE)"

    async with bot.pg_pool.acquire() as conn:
        try:
            # Main leaderboard query. Fails (attempts IS NULL) count as FAIL_PENALTY in avg.
            leaderboard_rows = await conn.fetch(f"""
                SELECT
                    s.user_id,
                    MAX(s.username) AS username,
                    COUNT(*) AS games_played,
                    COUNT(*) FILTER (WHERE s.attempts IS NULL) AS fails,
                    MIN(s.attempts) FILTER (WHERE s.attempts IS NOT NULL) AS best_score,
                    ROUND(AVG(COALESCE(s.attempts, {FAIL_PENALTY}))::numeric, 2) AS avg_attempts
                FROM scores s
                {where_clause} {date_filter}
                GROUP BY s.user_id
                ORDER BY avg_attempts ASC, games_played DESC
                LIMIT 10
            """)

            # User rank query
            user_rank_row = None
            if user_id:
                user_rank_row = await conn.fetchrow(f"""
                    SELECT
                        s.user_id,
                        MAX(s.username) AS username,
                        COUNT(*) AS games_played,
                        COUNT(*) FILTER (WHERE s.attempts IS NULL) AS fails,
                        MIN(s.attempts) FILTER (WHERE s.attempts IS NOT NULL) AS best_score,
                        ROUND(AVG(COALESCE(s.attempts, {FAIL_PENALTY}))::numeric, 2) AS avg_attempts,
                        RANK() OVER (
                            ORDER BY
                                ROUND(AVG(COALESCE(s.attempts, {FAIL_PENALTY}))::numeric, 2),
                                COUNT(*) DESC
                        ) AS rank
                    FROM scores s
                    {where_clause} {date_filter}
                    GROUP BY s.user_id
                    HAVING s.user_id = $1
                """, user_id)
        except Exception as e:
            print(f"Error generating leaderboard: {e}")
            raise

    title_map = {
        None: "🏆 Wordle Leaderboard (All Time)",
        "week": "📅 Wordle Leaderboard (Last 7 Days)",
        "month": "🗓️ Wordle Leaderboard (This Month)"
    }

    embed = discord.Embed(title=title_map.get(range, "🏆 Wordle Leaderboard"), color=0x00ff00)

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