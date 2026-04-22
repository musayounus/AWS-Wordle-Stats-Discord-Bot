"""Shared helpers for admin slash commands.

- Wordle-number validation and date conversion
- Auto-derivation of uncontended_crowns from crowns for a single wordle
"""

import datetime
from typing import Optional


WORDLE_START = datetime.date(2021, 6, 19)


# SQL fragment to exclude voided wordles from any read query over a table `t`
# that has columns `user_id` and `wordle_number`. Usage:
#   AND {NOT_VOIDED_SQL.format(alias='s')}
NOT_VOIDED_SQL = (
    "{alias}.wordle_number NOT IN (SELECT wordle_number FROM voided_wordles) "
    "AND NOT EXISTS ("
    "SELECT 1 FROM voided_user_wordles v "
    "WHERE v.user_id = {alias}.user_id AND v.wordle_number = {alias}.wordle_number"
    ")"
)


def current_wordle_number(today: Optional[datetime.date] = None) -> int:
    return ((today or datetime.date.today()) - WORDLE_START).days


def wordle_date_for_number(wordle_number: int) -> datetime.date:
    return WORDLE_START + datetime.timedelta(days=wordle_number)


def validate_wordle_number(wordle_number: int) -> Optional[str]:
    if wordle_number < 0:
        return "Wordle number cannot be negative."
    current = current_wordle_number()
    if wordle_number > current:
        return (
            f"Wordle number {wordle_number} is in the future "
            f"(today's Wordle is #{current})."
        )
    return None


async def load_voided_set(conn, user_id: Optional[int] = None) -> set:
    """Return the set of wordle numbers that should be skipped for streak
    purposes: global voids ∪ this user's per-user voids (if user_id given).
    """
    rows = await conn.fetch("SELECT wordle_number FROM voided_wordles")
    voided = {r["wordle_number"] for r in rows}
    if user_id is not None:
        user_rows = await conn.fetch(
            "SELECT wordle_number FROM voided_user_wordles WHERE user_id = $1",
            user_id,
        )
        voided.update(r["wordle_number"] for r in user_rows)
    return voided


async def sync_uncontended_for_wordle(conn, wordle_number: int) -> None:
    """Reflect the crowns table's exactly-one-holder rule in uncontended_crowns
    for this single wordle. Deletes any existing uncontended row for the wordle
    and inserts a fresh one only if `crowns` has exactly one holder.
    """
    crowns = await conn.fetch(
        "SELECT user_id, username, date FROM crowns WHERE wordle_number = $1",
        wordle_number,
    )
    await conn.execute(
        "DELETE FROM uncontended_crowns WHERE wordle_number = $1",
        wordle_number,
    )
    if len(crowns) == 1:
        row = crowns[0]
        await conn.execute(
            """
            INSERT INTO uncontended_crowns (user_id, username, wordle_number, date)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (user_id, wordle_number) DO NOTHING
            """,
            row["user_id"], row["username"], wordle_number, row["date"],
        )
