from rule_parser import parse_profile_rules # Import the new parser

def check_buy_conditions(parsed_rules, zacks_rank_str, style_scores_dict):
    """
    Checks buy conditions based on parsed rules from a profile's description.

    :param parsed_rules: Dict from parse_profile_rules,
                         e.g., {'zacks_rank_condition': ['1', '2'], 'style_pattern': 'AAAA'}
    :param zacks_rank_str: String like "1-Strong Buy", "2-Buy", etc.
    :param style_scores_dict: Dict like {'Value': 'A', 'Growth': 'B', ...}
    :return: Boolean
    """
    if not parsed_rules: # No rules means no buy
        return False

    # --- Zacks Rank Check ---
    # If zacks_rank_condition is specified in rules, it must be met.
    # If not specified, then any Zacks rank is considered acceptable (or this check is skipped).
    if 'zacks_rank_condition' in parsed_rules:
        if not isinstance(zacks_rank_str, str): return False # Rank must be a string

        # Extract the numeric part of the zacks_rank_str (e.g., "1" from "1-Strong Buy")
        rank_numeric_part_match = re.match(r"(\d+)", zacks_rank_str)
        if not rank_numeric_part_match: return False # Could not extract numeric rank

        actual_rank_numeric = rank_numeric_part_match.group(1)

        allowed_ranks = parsed_rules['zacks_rank_condition'] # This is a list of strings
        if actual_rank_numeric not in allowed_ranks:
            return False
    # If 'zacks_rank_condition' is NOT in parsed_rules, we don't filter by rank here.
    # Or, we could decide that means "any rank is fine" or "rank rule missing, so False".
    # Current: if not present, this condition is ignored. If present, it must match.
    # For a stricter interpretation where the rule *must* be present:
    # elif 'zacks_rank_condition' not in parsed_rules: return False

    # --- Style Score Check ---
    # If style_pattern is specified, it must be met.
    # If not specified, style scores are not considered for buy condition.
    if 'style_pattern' in parsed_rules:
        if not style_scores_dict: return False # Scores must be provided if pattern is checked

        required_score_keys = ['Value', 'Growth', 'Momentum', 'VGM']
        actual_scores_list = []
        for key in required_score_keys:
            score = style_scores_dict.get(key)
            if score is None or score not in ['A', 'B', 'C', 'D', 'F']:
                # print(f"Debug: Missing or invalid style score for {key}: {score}")
                return False # All 4 scores must be present and valid if checking pattern
            actual_scores_list.append(score)

        pattern = parsed_rules['style_pattern']

        if pattern == 'AAAA': # All scores must be 'A'
            if not all(s == 'A' for s in actual_scores_list):
                return False
        elif pattern == 'AAAB': # At least 3 A's, at most 1 B
            count_a = actual_scores_list.count('A')
            count_b = actual_scores_list.count('B')
            if not ((count_a == 4) or (count_a == 3 and count_b == 1)):
                return False
        # Add more patterns here if needed, e.g., 'AABB', 'ANY'
        else:
            # Unknown pattern implies a misconfiguration or unsupported rule
            # print(f"Debug: Unknown style pattern '{pattern}'")
            return False
    # If 'style_pattern' is not in parsed_rules, this condition is ignored.
    # Stricter: elif 'style_pattern' not in parsed_rules: return False

    # --- Final Check: At least one rule must have been defined and evaluated ---
    # If parsed_rules was not empty, but neither zacks_rank_condition nor style_pattern
    # were found, it means the rules are malformed or empty.
    # Example: rules = {'some_other_condition': 'value'} -> should not result in a buy.
    if not ('zacks_rank_condition' in parsed_rules or 'style_pattern' in parsed_rules):
        # print("Debug: No valid rule keys (zacks_rank_condition, style_pattern) found in parsed_rules.")
        return False

    # If we passed all relevant checks defined in parsed_rules, then it's a buy.
    return True


def check_sell_conditions(parsed_rules, zacks_rank_str, style_scores_dict):
    """
    Checks sell conditions based on parsed rules.
    Sells if the stock NO LONGER meets the buy conditions.
    Returns True if it SHOULD be sold, False otherwise.
    """
    return not check_buy_conditions(parsed_rules, zacks_rank_str, style_scores_dict)

# Need to import re for the zacks rank numeric part extraction
import re

if __name__ == "__main__":
    print("--- Testing Generalized Profile Logic ---")

    # Sample Parsed Rules
    rules_profile1_strict = {'zacks_rank_condition': ['1'], 'style_pattern': 'AAAB'}
    rules_profile2_all_a = {'zacks_rank_condition': ['1', '2'], 'style_pattern': 'AAAA'}
    rules_profile3_rank_only = {'zacks_rank_condition': ['1']}
    rules_profile4_style_only_aaaa = {'style_pattern': 'AAAA'}
    rules_profile5_malformed = {} # No valid rule keys
    rules_profile6_unknown_pattern = {'style_pattern': 'ABBB'}


    # Sample Scores
    style_scores_all_a = {'Value': 'A', 'Growth': 'A', 'Momentum': 'A', 'VGM': 'A'}
    style_scores_three_a_one_b = {'Value': 'A', 'Growth': 'B', 'Momentum': 'A', 'VGM': 'A'}
    style_scores_two_a_two_b = {'Value': 'A', 'Growth': 'B', 'Momentum': 'B', 'VGM': 'A'}
    style_scores_one_c = {'Value': 'C', 'Growth': 'A', 'Momentum': 'A', 'VGM': 'A'}
    style_scores_missing = {'Value': 'A', 'Growth': 'A', 'Momentum': 'A'} # VGM missing

    print("\n--- Testing check_buy_conditions ---")
    # Profile 1 Type Tests (Rank 1, Max 1 B)
    print(f"P1: Rank 1, All A: {check_buy_conditions(rules_profile1_strict, '1-Strong Buy', style_scores_all_a)} (Exp: True)")
    print(f"P1: Rank 1, 3A1B: {check_buy_conditions(rules_profile1_strict, '1-Strong Buy', style_scores_three_a_one_b)} (Exp: True)")
    print(f"P1: Rank 2, All A: {check_buy_conditions(rules_profile1_strict, '2-Buy', style_scores_all_a)} (Exp: False - Rank fail)")
    print(f"P1: Rank 1, 2A2B: {check_buy_conditions(rules_profile1_strict, '1-Strong Buy', style_scores_two_a_two_b)} (Exp: False - Style fail)")
    print(f"P1: Rank 1, 1C:   {check_buy_conditions(rules_profile1_strict, '1-Strong Buy', style_scores_one_c)} (Exp: False - Style fail)")
    print(f"P1: Rank 1, MissingScore: {check_buy_conditions(rules_profile1_strict, '1-Strong Buy', style_scores_missing)} (Exp: False - Style fail due to missing)")

    # Profile 2 Type Tests (Rank 1 or 2, All A)
    print(f"P2: Rank 1, All A: {check_buy_conditions(rules_profile2_all_a, '1-Strong Buy', style_scores_all_a)} (Exp: True)")
    print(f"P2: Rank 2, All A: {check_buy_conditions(rules_profile2_all_a, '2-Buy', style_scores_all_a)} (Exp: True)")
    print(f"P2: Rank 3, All A: {check_buy_conditions(rules_profile2_all_a, '3-Hold', style_scores_all_a)} (Exp: False - Rank fail)")
    print(f"P2: Rank 1, 3A1B: {check_buy_conditions(rules_profile2_all_a, '1-Strong Buy', style_scores_three_a_one_b)} (Exp: False - Style fail)")

    # Rank Only Profile
    print(f"P3 RankOnly: Rank 1, All A: {check_buy_conditions(rules_profile3_rank_only, '1-Strong Buy', style_scores_all_a)} (Exp: True)")
    print(f"P3 RankOnly: Rank 1, 2A2B: {check_buy_conditions(rules_profile3_rank_only, '1-Strong Buy', style_scores_two_a_two_b)} (Exp: True - Style ignored)")
    print(f"P3 RankOnly: Rank 2, All A: {check_buy_conditions(rules_profile3_rank_only, '2-Buy', style_scores_all_a)} (Exp: False - Rank fail)")

    # Style Only Profile (All A)
    print(f"P4 StyleOnly: Rank 1, All A: {check_buy_conditions(rules_profile4_style_only_aaaa, '1-Strong Buy', style_scores_all_a)} (Exp: True)")
    print(f"P4 StyleOnly: Rank 5, All A: {check_buy_conditions(rules_profile4_style_only_aaaa, '5-Strong Sell', style_scores_all_a)} (Exp: True - Rank ignored)")
    print(f"P4 StyleOnly: Rank 1, 3A1B: {check_buy_conditions(rules_profile4_style_only_aaaa, '1-Strong Buy', style_scores_three_a_one_b)} (Exp: False - Style fail)")

    # Malformed/Empty Rules
    print(f"P5 Malformed: Rank 1, All A: {check_buy_conditions(rules_profile5_malformed, '1-Strong Buy', style_scores_all_a)} (Exp: False)")
    print(f"P6 UnknownPattern: Rank 1, All A: {check_buy_conditions(rules_profile6_unknown_pattern, '1-Strong Buy', style_scores_all_a)} (Exp: False)")


    print("\n--- Testing check_sell_conditions ---")
    # Sell if NOT meeting buy conditions
    print(f"P1 Sell: Rank 1, All A (Don't Sell): {check_sell_conditions(rules_profile1_strict, '1-Strong Buy', style_scores_all_a)} (Exp: False)")
    print(f"P1 Sell: Rank 2, All A (Do Sell): {check_sell_conditions(rules_profile1_strict, '2-Buy', style_scores_all_a)} (Exp: True)")
    print(f"P1 Sell: Rank 1, 2A2B (Do Sell): {check_sell_conditions(rules_profile1_strict, '1-Strong Buy', style_scores_two_a_two_b)} (Exp: True)")

    print("\n--- End of Generalized Tests ---")
