import re

def parse_profile_rules(description_str):
    """
    Parses a profile's description string to extract rule conditions.
    Example description: "Zacks Rank: 1. Style Scores: Max 1 B (Value,Growth,Momentum,VGM)."
                         "Zacks Rank: 1 or 2. Style Scores: All A (Value,Growth,Momentum,VGM)."
    Output: A dictionary like {'zacks_rank_condition': ['1'], 'style_pattern': 'AAAB'}
    """
    if not description_str:
        return {}

    rules = {}

    # Parse Zacks Rank
    # Looks for "Zacks Rank: 1" or "Zacks Rank: 1 or 2" or "Zacks Rank: 1,2,3"
    rank_match = re.search(r"Zacks Rank:\s*([\d\s,or]+)\b", description_str, re.IGNORECASE)
    if rank_match:
        rank_text = rank_match.group(1).strip()
        # Split by 'or' or ',', then strip whitespace and filter out empty strings
        ranks = [r.strip() for r in re.split(r'\s+or\s+|,', rank_text) if r.strip().isdigit()]
        if ranks:
            rules['zacks_rank_condition'] = ranks # Store as a list of strings, e.g., ['1'], ['1', '2']

    # Parse Style Scores
    # Looks for "Style Scores: Max 1 B" or "Style Scores: All A"
    # The part in () like (Value,Growth,Momentum,VGM) is for user info, not directly parsed yet for specific scores.
    style_match = re.search(r"Style Scores:\s*(All A|Max 1 B)\b", description_str, re.IGNORECASE)
    if style_match:
        pattern_text = style_match.group(1).strip().lower()
        if pattern_text == "all a":
            rules['style_pattern'] = 'AAAA' # All 4 scores must be A
        elif pattern_text == "max 1 b":
            rules['style_pattern'] = 'AAAB' # At least 3 A's, at most 1 B

    # Add more parsers here for other rule types if needed in the future

    print(f"Parsed rules from '{description_str}': {rules}")
    return rules

if __name__ == '__main__':
    print("--- Testing rule_parser.py ---")
    desc1 = "Zacks Rank: 1. Style Scores: Max 1 B (Value,Growth,Momentum,VGM)."
    rules1 = parse_profile_rules(desc1)
    # Expected: {'zacks_rank_condition': ['1'], 'style_pattern': 'AAAB'}
    print(f"Test 1: '{desc1}' -> {rules1}")

    desc2 = "Zacks Rank: 1 or 2. Style Scores: All A (Value,Growth,Momentum,VGM)."
    rules2 = parse_profile_rules(desc2)
    # Expected: {'zacks_rank_condition': ['1', '2'], 'style_pattern': 'AAAA'}
    print(f"Test 2: '{desc2}' -> {rules2}")

    desc3 = "Zacks Rank: 2, 3 . Style Scores: Max 1 B." # Test comma and extra space
    rules3 = parse_profile_rules(desc3)
    # Expected: {'zacks_rank_condition': ['2', '3'], 'style_pattern': 'AAAB'}
    print(f"Test 3: '{desc3}' -> {rules3}")

    desc4 = "Only Zacks Rank: 1."
    rules4 = parse_profile_rules(desc4)
    # Expected: {'zacks_rank_condition': ['1']}
    print(f"Test 4: '{desc4}' -> {rules4}")

    desc5 = "Only Style Scores: All A."
    rules5 = parse_profile_rules(desc5)
    # Expected: {'style_pattern': 'AAAA'}
    print(f"Test 5: '{desc5}' -> {rules5}")

    desc6 = "Invalid rule string."
    rules6 = parse_profile_rules(desc6)
    # Expected: {}
    print(f"Test 6: '{desc6}' -> {rules6}")

    desc7 = "Zacks Rank: 1-Strong Buy. Style Scores: Max 1 B." # Test with text in rank
    rules7 = parse_profile_rules(desc7)
    # Expected: {'zacks_rank_condition': ['1'], 'style_pattern': 'AAAB'}
    print(f"Test 7: '{desc7}' -> {rules7}")

    desc8 = "Zacks Rank: 1 or 2 or 3. Style Scores: Max 1 B."
    rules8 = parse_profile_rules(desc8)
    # Expected: {'zacks_rank_condition': ['1', '2', '3'], 'style_pattern': 'AAAB'}
    print(f"Test 8: '{desc8}' -> {rules8}")

    desc_empty = ""
    rules_empty = parse_profile_rules(desc_empty)
    print(f"Test Empty: '{desc_empty}' -> {rules_empty}")

    desc_none = None
    rules_none = parse_profile_rules(desc_none)
    print(f"Test None: '{desc_none}' -> {rules_none}")
