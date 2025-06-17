async def insert_score(conn, user_id, username, wordle_number, date, attempts):
    await conn.execute("""
        INSERT INTO scores (user_id, username, wordle_number, date, attempts)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (user_id, wordle_number) DO NOTHING
    """, user_id, username, wordle_number, date, attempts)

async def get_leaderboard(conn, range=None):
    where_clause = "WHERE attempts IS NOT NULL AND user_id NOT IN (SELECT user_id FROM banned_users)"
    date_filter = ""
    if range == "week":
        date_filter = "AND date >= CURRENT_DATE - INTERVAL '7 days'"
    elif range == "month":
        date_filter = "AND date_trunc('month', date) = date_trunc('month', CURRENT_DATE)"

    sql = f"""
        SELECT user_id, username,
               COUNT(*) FILTER (WHERE attempts IS NULL) AS fails,
               COUNT(*) FILTER (WHERE attempts IS NOT NULL) AS games_played,
               MIN(attempts) FILTER (WHERE attempts IS NOT NULL) AS best_score,
               ROUND(AVG(attempts)::numeric, 2) AS avg_attempts
        FROM scores
        {where_clause} {date_filter}
        GROUP BY user_id, username
        ORDER BY avg_attempts ASC, games_played DESC
        LIMIT 10
    """
    return await conn.fetch(sql)

async def get_user_rank_row(conn, user_id, range=None):
    where_clause = "WHERE attempts IS NOT NULL AND user_id NOT IN (SELECT user_id FROM banned_users)"
    date_filter = ""
    if range == "week":
        date_filter = "AND date >= CURRENT_DATE - INTERVAL '7 days'"
    elif range == "month":
        date_filter = "AND date_trunc('month', date) = date_trunc('month', CURRENT_DATE)"

    sql = f"""
        SELECT user_id, username,
               COUNT(*) FILTER (WHERE attempts IS NULL) AS fails,
               COUNT(*) FILTER (WHERE attempts IS NOT NULL) AS games_played,
               MIN(attempts) FILTER (WHERE attempts IS NOT NULL) AS best_score,
               ROUND(AVG(attempts)::numeric, 2) AS avg_attempts,
               RANK() OVER (ORDER BY ROUND(AVG(attempts)::numeric, 2), COUNT(*) FILTER (WHERE attempts IS NOT NULL) DESC) AS rank
        FROM scores
        {where_clause} {date_filter}
        GROUP BY user_id, username
        HAVING user_id = $1
    """
    return await conn.fetchrow(sql, user_id)

async def is_user_banned(conn, user_id):
    return await conn.fetchval("SELECT 1 FROM banned_users WHERE user_id = $1", user_id)

async def get_previous_best(conn, user_id):
    return await conn.fetchval("""
        SELECT MIN(attempts) FROM scores
        WHERE user_id = $1 AND attempts IS NOT NULL
    """, user_id)

async def insert_crown(conn, user_id, username, wordle_number, date):
    await conn.execute("""
        INSERT INTO crowns (user_id, username, wordle_number, date)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT DO NOTHING
    """, user_id, username, wordle_number, date)

async def get_crowns(conn):
    return await conn.fetch("""
        SELECT user_id,
            MAX(username) AS display_name,
            COUNT(*) AS crown_count
        FROM crowns
        GROUP BY user_id
        ORDER BY crown_count DESC
    """)

async def reset_leaderboard(conn):
    await conn.execute("DELETE FROM scores")
    await conn.execute("DELETE FROM crowns")

async def ban_user(conn, user_id, username):
    await conn.execute("""
        INSERT INTO banned_users (user_id, username)
        VALUES ($1, $2)
        ON CONFLICT (user_id) DO NOTHING
    """, user_id, username)

async def unban_user(conn, user_id):
    await conn.execute("DELETE FROM banned_users WHERE user_id = $1", user_id)

async def remove_scores(conn, user_id, numbers):
    return await conn.fetch("""
        DELETE FROM scores
        WHERE user_id = $1 AND wordle_number = ANY($2)
        RETURNING wordle_number
    """, user_id, numbers)

async def get_stats(conn, user_id):
    return await conn.fetchrow("""
        SELECT
            COUNT(*) FILTER (WHERE attempts IS NOT NULL) AS games_played,
            COUNT(*) FILTER (WHERE attempts IS NULL) AS fails,
            MIN(attempts) AS best_score,
            ROUND(AVG(attempts)::numeric, 2) AS avg_score,
            MAX(date) AS last_game
        FROM scores
        WHERE user_id = $1 AND user_id NOT IN (SELECT user_id FROM banned_users)
    """, user_id)

async def get_streak_wordles(conn, user_id):
    return await conn.fetch("""
        SELECT wordle_number FROM scores
        WHERE user_id = $1 AND attempts IS NOT NULL AND user_id NOT IN (SELECT user_id FROM banned_users)
        ORDER BY wordle_number
    """, user_id)

async def get_all_streak_users(conn):
    return await conn.fetch("""
        SELECT DISTINCT user_id, username
        FROM scores
        WHERE attempts IS NOT NULL AND user_id NOT IN (SELECT user_id FROM banned_users)
    """)

async def get_user_stats_for_predictions(conn):
    return await conn.fetch("""
        SELECT user_id, username,
               ROUND(AVG(attempts)::numeric, 2) AS avg_score,
               COUNT(*) AS games_played
        FROM scores
        WHERE attempts IS NOT NULL AND user_id NOT IN (SELECT user_id FROM banned_users)
        GROUP BY user_id, username
        ORDER BY avg_score ASC
    """)