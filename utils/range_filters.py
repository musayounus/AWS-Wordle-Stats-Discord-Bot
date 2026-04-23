import calendar

from discord import app_commands

MONTH_CHOICES = [
    app_commands.Choice(name=calendar.month_name[m], value=m) for m in range(1, 13)
]


def build_date_filter(year=None, month=None, column="s.date"):
    """Return (sql_fragment, title_suffix) for the given year/month.

    Integers are coerced and inlined — callers pass validated app_commands
    inputs so no injection risk.
    """
    if year is not None and month is not None:
        return (
            f"AND EXTRACT(YEAR FROM {column}) = {int(year)} "
            f"AND EXTRACT(MONTH FROM {column}) = {int(month)}",
            f"{calendar.month_name[int(month)]} {int(year)}",
        )
    if year is not None:
        return f"AND EXTRACT(YEAR FROM {column}) = {int(year)}", str(int(year))
    if month is not None:
        return (
            f"AND EXTRACT(MONTH FROM {column}) = {int(month)} "
            f"AND EXTRACT(YEAR FROM {column}) = EXTRACT(YEAR FROM CURRENT_DATE)",
            calendar.month_name[int(month)],
        )
    return "", None
