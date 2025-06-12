import re

def calculate_streak(wordles):
    wordles = sorted(set(wordles))
    if not wordles:
        return 0
    streak = 1
    for i in range(len(wordles) - 2, -1, -1):
        if wordles[i] == wordles[i + 1] - 1:
            streak += 1
        else:
            break
    return streak

def parse_wordle_message(content):
    """
    Improved parser that handles:
    - 'Wordle 1234 3/6'
    - 'Wordle 1234 X/6'
    - 'Wordle 1234 3/6*' (with emoji)
    - 'Wordle 1234 3/6\n...'
    - Case insensitivity
    """
    # Case-insensitive match with flexible spacing
    pattern = r'wordle\s+(\d+)\s+(\d+|x)/6\b'
    match = re.search(pattern, content, re.IGNORECASE)
    
    if match:
        wordle_number = int(match.group(1))
        raw_attempts = match.group(2).upper()
        attempts = None if raw_attempts == "X" else int(raw_attempts)
        return wordle_number, attempts
    return None, None

def parse_summary_lines(content):
    """Handle summary messages with flexible formatting"""
    return [
        line.strip() for line in content.split('\n') 
        if line.strip() and not line.strip().startswith(('Your group', '🔥', '🟥', '🟨', '⬛'))
    ]

def parse_summary_result_line(line):
    """Handle crown indicators and different mention formats"""
    # Match both '👑 3/6' and regular '3/6'
    match = re.search(r'(\d|X)/6:\s*(.*)', line, re.IGNORECASE)
    if not match:
        return None, None
    
    raw_attempt = match.group(1).upper()
    user_section = match.group(2)
    attempts = None if raw_attempt == "X" else int(raw_attempt)
    return attempts, user_section

def parse_mentions(user_section, mentions):
    """Improved mention parser handles display name changes"""
    results = []
    
    # 1. Check direct user mentions
    for user in mentions:
        if f"<@{user.id}>" in user_section or f"<@!{user.id}>" in user_section:
            results.append((user.id, user.display_name))
    
    # 2. Check @username mentions (fallback)
    if not results:
        for user in mentions:
            if f"@{user.display_name}" in user_section:
                results.append((user.id, user.display_name))
    
    return results