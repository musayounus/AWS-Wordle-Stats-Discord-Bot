import discord

async def generate_leaderboard_embed(bot, user_id=None, range: str = None):
    where_clause = "WHERE user_id NOT IN (SELECT user_id FROM banned_users)"
    date_filter = ""

    if range == "week":
        date_filter = "AND date >= CURRENT_DATE - INTERVAL '7 days'"
    elif range == "month":
        date_filter = "AND date_trunc('month', date) = date_trunc('month', CURRENT_DATE)"

    async with bot.pg_pool.acquire() as conn:
        # Main leaderboard query combining scores and fails
        leaderboard_rows = await conn.fetch(f"""
            WITH combined_data AS (
                SELECT 
                    user_id,
                    username,
                    wordle_number,
                    date,
                    attempts
                FROM scores
                {where_clause} {date_filter}
                
                UNION ALL
                
                SELECT 
                    user_id,
                    username,
                    wordle_number,
                    date,
                    NULL AS attempts
                FROM fails
                {where_clause} {date_filter}
            )
            SELECT 
                user_id, 
                MAX(username) AS username,
                COUNT(*) FILTER (WHERE attempts IS NOT NULL) AS games_played,
                COUNT(*) FILTER (WHERE attempts IS NULL) AS fails,
                MIN(attempts) FILTER (WHERE attempts IS NOT NULL) AS best_score,
                ROUND(AVG(attempts)::numeric, 2) AS avg_attempts
            FROM combined_data
            GROUP BY user_id
            ORDER BY avg_attempts ASC, games_played DESC
            LIMIT 10
        """)

        # User rank query
        user_rank_row = None
        if user_id:
            user_rank_row = await conn.fetchrow(f"""
                WITH combined_data AS (
                    SELECT 
                        user_id,
                        username,
                        wordle_number,
                        date,
                        attempts
                    FROM scores
                    {where_clause} {date_filter}
                    
                    UNION ALL
                    
                    SELECT 
                        user_id,
                        username,
                        wordle_number,
                        date,
                        NULL AS attempts
                    FROM fails
                    {where_clause} {date_filter}
                )
                SELECT 
                    user_id, 
                    MAX(username) AS username,
                    COUNT(*) FILTER (WHERE attempts IS NOT NULL) AS games_played,
                    COUNT(*) FILTER (WHERE attempts IS NULL) AS fails,
                    MIN(attempts) FILTER (WHERE attempts IS NOT NULL) AS best_score,
                    ROUND(AVG(attempts)::numeric, 2) AS avg_attempts,
                    RANK() OVER (
                        ORDER BY 
                            ROUND(AVG(attempts)::numeric, 2), 
                            COUNT(*) FILTER (WHERE attempts IS NOT NULL) DESC
                    ) AS rank
                FROM combined_data
                GROUP BY user_id
                HAVING user_id = $1
            """, user_id)

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
            embed.add_field(
                name=f"#{idx} {row['username']}",
                value=(f"Avg: {row['avg_attempts']:.2f} | Best: {row['best_score'] or '—'} {emoji_best}\n"
                       f"Games: {row['games_played']} | Fails: {row['fails']} {emoji_fail}"),
                inline=False
            )

        if user_rank_row and user_rank_row['user_id'] not in [r['user_id'] for r in leaderboard_rows]:
            emoji_best = "🧠" if user_rank_row['best_score'] == 1 else ""
            emoji_fail = "💀" if user_rank_row['fails'] > 0 else ""
            embed.add_field(
                name=f"⬇️ Your Rank: #{user_rank_row['rank']} {user_rank_row['username']}",
                value=(f"Avg: {user_rank_row['avg_attempts']:.2f} | Best: {user_rank_row['best_score'] or '—'} {emoji_best}\n"
                       f"Games: {user_rank_row['games_played']} | Fails: {user_rank_row['fails']} {emoji_fail}"),
                inline=False
            )

    return embed