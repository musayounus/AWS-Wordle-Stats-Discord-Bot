import calendar

from discord import app_commands

RANGE_CHOICES = [
    app_commands.Choice(name="week", value="week"),
    app_commands.Choice(name="month", value="month"),
    app_commands.Choice(name="year", value="year"),
]

MONTH_CHOICES = [
    app_commands.Choice(name=calendar.month_name[m], value=m) for m in range(1, 13)
]


def build_date_filter(range=None, year=None, month=None, column="s.date"):
    """Return (sql_fragment, title_suffix) for the given range/year/month.

    Explicit year/month override the relative range. Integers are coerced and
    inlined — callers pass validated app_commands inputs so no injection risk.
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
    if range == "week":
        return f"AND {column} >= CURRENT_DATE - INTERVAL '7 days'", "Last 7 Days"
    if range == "month":
        return (
            f"AND date_trunc('month', {column}) = date_trunc('month', CURRENT_DATE)",
            "This Month",
        )
    if range == "year":
        return (
            f"AND date_trunc('year', {column}) = date_trunc('year', CURRENT_DATE)",
            "This Year",
        )
    return "", None
