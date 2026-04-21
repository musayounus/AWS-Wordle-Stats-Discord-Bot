"""User resolution for @mentions in Wordle summary messages.

Handles both proper <@id> mentions (which populate message.mentions) and
plain-text @name references (which do not, when Discord fails to render
the @ as a real mention).
"""

import re
from typing import List, Optional, Tuple

import discord


# ("id", int) or ("name", str)
UserToken = Tuple[str, object]

# Note: plain-text @ names terminate at whitespace, so display names containing
# spaces are not supported. Revisit if a real summary breaks on this.
_TOKEN_RE = re.compile(
    r"<@!?(?P<id>\d{15,20})>"
    r"|@(?P<name>[^\s@,<>][^@,<>\n]*?)"
    r"(?=$|[\s,]|<@|👑)"
)

_TRAILING_PUNCT = ".,;:!?"


def extract_user_tokens(text: str) -> List[UserToken]:
    tokens: List[UserToken] = []
    if not text:
        return tokens
    for m in _TOKEN_RE.finditer(text):
        if m.group("id"):
            tokens.append(("id", int(m.group("id"))))
        elif m.group("name") is not None:
            name = m.group("name").rstrip(_TRAILING_PUNCT)
            if name:
                tokens.append(("name", name))
    return tokens


def add_user_to_cache(cache: dict, user) -> None:
    value = (user.id, user.display_name)
    cache[str(user.id)] = value
    display = getattr(user, "display_name", None)
    if display:
        cache[display.lower()] = value
    raw = getattr(user, "name", None)
    if raw:
        cache[raw.lower()] = value
    global_name = getattr(user, "global_name", None)
    if global_name:
        cache[global_name.lower()] = value


def build_cache_from_mentions(message: discord.Message) -> dict:
    cache: dict = {}
    for user in message.mentions:
        add_user_to_cache(cache, user)
    return cache


async def resolve_user(
    guild: Optional[discord.Guild],
    token: UserToken,
    *,
    cache: dict,
    conn,
) -> Tuple[Optional[int], Optional[str]]:
    """Resolve a token to (user_id, display_name), or (None, None) if unresolvable.

    Order: cache → guild members → historical DB. Logs a warning to stdout
    for unresolvable tokens (visible in CloudWatch).
    """
    kind, value = token

    if kind == "id":
        uid = int(value)
        key = str(uid)
        if key in cache:
            return cache[key]
        if guild is not None:
            member = guild.get_member(uid)
            if member is not None:
                add_user_to_cache(cache, member)
                return (member.id, member.display_name)
        row = await conn.fetchrow(
            """
            SELECT username FROM (
                SELECT username, date FROM scores WHERE user_id = $1
                UNION ALL SELECT username, date FROM crowns WHERE user_id = $1
                UNION ALL SELECT username, date FROM fails WHERE user_id = $1
                UNION ALL SELECT username, CURRENT_DATE AS date FROM banned_users WHERE user_id = $1
            ) t
            ORDER BY date DESC
            LIMIT 1
            """,
            uid,
        )
        name = row["username"] if row else str(uid)
        cache[key] = (uid, name)
        return (uid, name)

    name = str(value)
    key = name.lower()
    if key in cache:
        return cache[key]

    if guild is not None:
        matches = [
            m for m in guild.members
            if (m.display_name and m.display_name.lower() == key)
            or (m.name and m.name.lower() == key)
            or (getattr(m, "global_name", None) and m.global_name.lower() == key)
        ]
        if len(matches) == 1:
            add_user_to_cache(cache, matches[0])
            return (matches[0].id, matches[0].display_name)
        if len(matches) > 1:
            ids = [m.id for m in matches]
            row = await conn.fetchrow(
                """
                SELECT user_id FROM (
                    SELECT user_id, MAX(date) AS d FROM scores
                        WHERE user_id = ANY($1::bigint[]) GROUP BY user_id
                    UNION ALL
                    SELECT user_id, MAX(date) AS d FROM crowns
                        WHERE user_id = ANY($1::bigint[]) GROUP BY user_id
                    UNION ALL
                    SELECT user_id, MAX(date) AS d FROM fails
                        WHERE user_id = ANY($1::bigint[]) GROUP BY user_id
                ) t
                ORDER BY d DESC NULLS LAST
                LIMIT 1
                """,
                ids,
            )
            if row is not None:
                uid = row["user_id"]
                member = guild.get_member(uid)
                display = member.display_name if member else name
                cache[key] = (uid, display)
                return (uid, display)
            print(
                f"⚠️ Ambiguous name '{name}' — multiple guild members {ids} "
                f"with no DB history; skipping",
                flush=True,
            )
            return (None, None)

    row = await conn.fetchrow(
        """
        SELECT user_id, username FROM (
            SELECT user_id, username, date FROM scores WHERE LOWER(username) = $1
            UNION ALL SELECT user_id, username, date FROM crowns WHERE LOWER(username) = $1
            UNION ALL SELECT user_id, username, date FROM fails WHERE LOWER(username) = $1
            UNION ALL SELECT user_id, username, CURRENT_DATE AS date FROM banned_users WHERE LOWER(username) = $1
        ) t
        ORDER BY date DESC
        LIMIT 1
        """,
        key,
    )
    if row is not None:
        result = (row["user_id"], row["username"])
        cache[key] = result
        return result

    print(f"⚠️ Could not resolve user '{name}'", flush=True)
    return (None, None)


if __name__ == "__main__":
    cases = [
        ("@ENDLESS", [("name", "ENDLESS")]),
        ("<@123456789012345678>", [("id", 123456789012345678)]),
        ("<@111111111111111111> @jack195", [("id", 111111111111111111), ("name", "jack195")]),
        ("@alice, @bob_smith", [("name", "alice"), ("name", "bob_smith")]),
        ("@alice.", [("name", "alice")]),
        ("@alice.eats", [("name", "alice.eats")]),
        ("", []),
        ("👑 @alice", [("name", "alice")]),
        ("<@&99999999999999999>", []),
    ]
    failed = 0
    for text, expected in cases:
        got = extract_user_tokens(text)
        ok = got == expected
        if not ok:
            failed += 1
        print(f"[{'ok' if ok else 'FAIL'}] {text!r} -> {got}  (expected {expected})")
    print(f"\n{len(cases) - failed}/{len(cases)} passed")
    raise SystemExit(0 if failed == 0 else 1)
