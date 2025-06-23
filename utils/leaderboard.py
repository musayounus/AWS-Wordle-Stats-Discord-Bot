import discord

async def generate_leaderboard_embed(bot, user_id=None, range: str = None):
    where_clause = "WHERE s.user_id NOT IN (SELECT user_id FROM banned_users)"
    date_filter = ""

    if range == "week":
        date_filter = "AND s.date >= CURRENT_DATE - INTERVAL '7 days'"
    elif range == "month":
        date_filter = "AND date_trunc('month', s.date) = date_trunc('month', CURRENT_DATE)"

    async with bot.pg_pool.acquire() as conn:
        try:
            # Main leaderboard query - fixed ambiguous column references
            leaderboard_rows = await conn.fetch(f"""
                SELECT 
                    s.user_id, 
                    MAX(s.username) AS username,
                    COUNT(*) FILTER (WHERE s.attempts IS NOT NULL) AS games_played,
                    COALESCE(f.fail_count, 0) AS fails,
                    MIN(s.attempts) FILTER (WHERE s.attempts IS NOT NULL) AS best_score,
                    CASE 
                        WHEN COUNT(*) FILTER (WHERE s.attempts IS NOT NULL) > 0 
                        THEN ROUND(AVG(s.attempts)::numeric, 2)
                        ELSE NULL
                    END AS avg_attempts
                FROM scores s
                LEFT JOIN (
                    SELECT user_id, COUNT(*) AS fail_count 
                    FROM fails 
                    WHERE user_id NOT IN (SELECT user_id FROM banned_users)
                    {date_filter.replace('s.', '')}
                    GROUP BY user_id
                ) f ON s.user_id = f.user_id
                {where_clause} {date_filter}
                GROUP BY s.user_id, f.fail_count
                ORDER BY 
                    CASE WHEN COUNT(*) FILTER (WHERE s.attempts IS NOT NULL) > 0 
                         THEN ROUND(AVG(s.attempts)::numeric, 2)
                         ELSE 999 END ASC,
                    games_played DESC
                LIMIT 10
            """)

            # User rank query - fixed ambiguous column references
            user_rank_row = None
            if user_id:
                user_rank_row = await conn.fetchrow(f"""
                    SELECT 
                        s.user_id, 
                        MAX(s.username) AS username,
                        COUNT(*) FILTER (WHERE s.attempts IS NOT NULL) AS games_played,
                        COALESCE(f.fail_count, 0) AS fails,
                        MIN(s.attempts) FILTER (WHERE s.attempts IS NOT NULL) AS best_score,
                        CASE 
                            WHEN COUNT(*) FILTER (WHERE s.attempts IS NOT NULL) > 0 
                            THEN ROUND(AVG(s.attempts)::numeric, 2)
                            ELSE NULL
                        END AS avg_attempts,
                        RANK() OVER (
                            ORDER BY 
                                CASE WHEN COUNT(*) FILTER (WHERE s.attempts IS NOT NULL) > 0 
                                     THEN ROUND(AVG(s.attempts)::numeric, 2)
                                     ELSE 999 END,
                                COUNT(*) FILTER (WHERE s.attempts IS NOT NULL) DESC
                        ) AS rank
                    FROM scores s
                    LEFT JOIN (
                        SELECT user_id, COUNT(*) AS fail_count 
                        FROM fails 
                        WHERE user_id NOT IN (SELECT user_id FROM banned_users)
                        {date_filter.replace('s.', '')}
                        GROUP BY user_id
                    ) f ON s.user_id = f.user_id
                    {where_clause} {date_filter}
                    GROUP BY s.user_id, f.fail_count
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