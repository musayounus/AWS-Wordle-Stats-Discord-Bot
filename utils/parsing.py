import re

WORDLE_REGEX = re.compile(r'Wordle\s+(\d+)\s+(\d|X)/6', re.IGNORECASE)
SUMMARY_PATTERN = re.compile(r"(\d|X)/6:\s+(.*)")

def parse_wordle_message(content):
    match = WORDLE_REGEX.search(content)
    if match:
        wordle_number = int(match.group(1))
        raw = match.group(2).upper()
        attempts = None if raw == "X" else int(raw)
        return wordle_number, attempts
    return None, None

def parse_summary_lines(content):
    return [line for line in content.strip().splitlines()]

def parse_summary_result_line(line):
    match = SUMMARY_PATTERN.search(line)
    if match:
        raw_attempt = match.group(1)
        attempts = None if raw_attempt.upper() == "X" else int(raw_attempt)
        user_section = match.group(2)
        return attempts, user_section
    return None, None

def parse_mentions(user_section, mentions):
    found = []
    if mentions:
        for user in mentions:
            if f"@{user.display_name}" in user_section or f"<@{user.id}>" in user_section:
                found.append((user.id, user.display_name))
    return found