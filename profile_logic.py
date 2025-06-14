import sqlite3
import re

# DB_NAME_PROFILE_LOGIC is not needed here anymore if connection is passed.

# No longer need get_db_connection_for_logic here,
# the calling context (tests or scanner) will provide the connection.

def check_buy_conditions(db_conn, profile_id, zacks_rank_str, style_scores_dict):
    """
    Checks buy conditions for a given profile_id using a provided db connection.
    """
    cursor = db_conn.cursor()

    cursor.execute("SELECT category, condition, value1 FROM profile_rules WHERE profile_id = ?", (profile_id,))
    rules = cursor.fetchall()
    # No conn.close() here as the connection is managed by the caller

    if not rules:
        # print(f"Profile {profile_id}: No rules defined in DB. Buy condition = False.")
        return False

    zacks_rank_rule_defined = False
    zacks_rank_met = False
    style_pattern_rule_defined = False
    style_pattern_met = False
    individual_style_rules_state = {}

    for rule_row in rules: # sqlite3.Row object allows access by column name
        category = rule_row['category']
        condition = rule_row['condition']
        value1 = rule_row['value1']

        if category == 'ZACKS_RANK':
            zacks_rank_rule_defined = True
            if condition == 'IN_LIST' and isinstance(zacks_rank_str, str) and value1:
                allowed_ranks = value1.split(',')
                rank_numeric_match = re.match(r"(\d+)", zacks_rank_str)
                if rank_numeric_match:
                    actual_rank_numeric = rank_numeric_match.group(1)
                    if actual_rank_numeric in allowed_ranks:
                        zacks_rank_met = True

        elif category == 'STYLE_SCORE_PATTERN':
            style_pattern_rule_defined = True
            if condition == 'MATCHES_PATTERN' and style_scores_dict and value1:
                required_keys = ['Value', 'Growth', 'Momentum', 'VGM']
                if not all(key in style_scores_dict and style_scores_dict[key] is not None for key in required_keys):
                    style_pattern_met = False; continue

                scores = [style_scores_dict.get(k, 'F') for k in required_keys]
                if value1 == 'AAAA':
                    if all(s == 'A' for s in scores): style_pattern_met = True
                elif value1 == 'AAAB':
                    count_a = scores.count('A'); count_b = scores.count('B')
                    if count_a == 4 or (count_a == 3 and count_b == 1): style_pattern_met = True

        elif category.startswith('STYLE_SCORE_'):
            score_type_key = category.split('_')[-1].capitalize()
            if score_type_key not in ['Value', 'Growth', 'Momentum', 'VGM']: continue

            current_state = individual_style_rules_state.get(score_type_key, {'defined': False, 'met': True})
            current_state['defined'] = True

            if condition == 'EQUALS' and style_scores_dict and value1:
                actual_score = style_scores_dict.get(score_type_key)
                if actual_score != value1: # If one rule is not met, this category is not met
                    current_state['met'] = False
            else: # Malformed rule or missing data
                 current_state['met'] = False
            individual_style_rules_state[score_type_key] = current_state


    # --- Determine overall outcome ---
    final_zacks_ok = zacks_rank_met if zacks_rank_rule_defined else True

    final_style_ok = False
    if style_pattern_rule_defined:
        final_style_ok = style_pattern_met
    elif individual_style_rules_state: # Individual rules were defined
        # All *defined* individual style rules must be met
        all_defined_individual_rules_met = True
        if not individual_style_rules_state: # No individual rules were actually processed (e.g. bad category names)
            all_defined_individual_rules_met = False # Or True if "no individual rules = pass"
        for score_type_info in individual_style_rules_state.values():
            if not score_type_info['met']: # If any defined rule is not met
                all_defined_individual_rules_met = False
                break
        final_style_ok = all_defined_individual_rules_met
    else: # No style rules of any kind were defined for this profile
        final_style_ok = True

    at_least_one_rule_category_defined = zacks_rank_rule_defined or \
                                         style_pattern_rule_defined or \
                                         bool(individual_style_rules_state) # True if dict is not empty

    if not at_least_one_rule_category_defined:
        return False

    return final_zacks_ok and final_style_ok


def check_sell_conditions(db_conn, profile_id, zacks_rank_str, style_scores_dict):
    return not check_buy_conditions(db_conn, profile_id, zacks_rank_str, style_scores_dict)


# --- Test Area ---
def setup_in_memory_db_for_testing(): # Returns connection
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE investor_profiles (profile_id INTEGER PRIMARY KEY, name TEXT, description TEXT, is_active INTEGER)")
    cursor.execute("""
        CREATE TABLE profile_rules (
            rule_id INTEGER PRIMARY KEY AUTOINCREMENT, profile_id INTEGER,
            category TEXT, condition TEXT, value1 TEXT, value2 TEXT,
            FOREIGN KEY (profile_id) REFERENCES investor_profiles (profile_id)
        )""")

    # P1: Zacks Rank 1, Style Pattern AAAB
    cursor.execute("INSERT INTO investor_profiles (profile_id, name, is_active) VALUES (1, 'P1 Rank1_AAAB', 1)")
    cursor.execute("INSERT INTO profile_rules (profile_id, category, condition, value1) VALUES (1, 'ZACKS_RANK', 'IN_LIST', '1')")
    cursor.execute("INSERT INTO profile_rules (profile_id, category, condition, value1) VALUES (1, 'STYLE_SCORE_PATTERN', 'MATCHES_PATTERN', 'AAAB')")

    # P2: Zacks Rank 1 or 2, Style Pattern AAAA
    cursor.execute("INSERT INTO investor_profiles (profile_id, name, is_active) VALUES (2, 'P2 Rank1or2_AAAA', 1)")
    cursor.execute("INSERT INTO profile_rules (profile_id, category, condition, value1) VALUES (2, 'ZACKS_RANK', 'IN_LIST', '1,2')")
    cursor.execute("INSERT INTO profile_rules (profile_id, category, condition, value1) VALUES (2, 'STYLE_SCORE_PATTERN', 'MATCHES_PATTERN', 'AAAA')")

    # P3: Zacks Rank 1 Only
    cursor.execute("INSERT INTO investor_profiles (profile_id, name, is_active) VALUES (3, 'P3 Rank1Only', 1)")
    cursor.execute("INSERT INTO profile_rules (profile_id, category, condition, value1) VALUES (3, 'ZACKS_RANK', 'IN_LIST', '1')")

    # P4: Indiv Style V=A, G=A (Momentum and VGM not specified, so they don't fail the style check)
    cursor.execute("INSERT INTO investor_profiles (profile_id, name, is_active) VALUES (4, 'P4 Indiv_V=A_G=A', 1)")
    cursor.execute("INSERT INTO profile_rules (profile_id, category, condition, value1) VALUES (4, 'STYLE_SCORE_VALUE', 'EQUALS', 'A')")
    cursor.execute("INSERT INTO profile_rules (profile_id, category, condition, value1) VALUES (4, 'STYLE_SCORE_GROWTH', 'EQUALS', 'A')")

    # P5: No rules defined
    cursor.execute("INSERT INTO investor_profiles (profile_id, name, is_active) VALUES (5, 'P5 NoRules', 1)")

    # P6: Indiv Style V=A, but G=MustBeB (to test failure)
    cursor.execute("INSERT INTO investor_profiles (profile_id, name, is_active) VALUES (6, 'P6 Indiv_V=A_G=B', 1)")
    cursor.execute("INSERT INTO profile_rules (profile_id, category, condition, value1) VALUES (6, 'STYLE_SCORE_VALUE', 'EQUALS', 'A')")
    cursor.execute("INSERT INTO profile_rules (profile_id, category, condition, value1) VALUES (6, 'STYLE_SCORE_GROWTH', 'EQUALS', 'B')")

    conn.commit()
    return conn

if __name__ == "__main__":
    print("--- Testing Profile Logic with Structured Rules (In-Memory DB) ---")

    test_db_conn = setup_in_memory_db_for_testing()

    scores_all_a = {'Value': 'A', 'Growth': 'A', 'Momentum': 'A', 'VGM': 'A'}
    scores_3a1b  = {'Value': 'A', 'Growth': 'B', 'Momentum': 'A', 'VGM': 'A'}
    scores_2a2b  = {'Value': 'A', 'Growth': 'B', 'Momentum': 'B', 'VGM': 'A'}
    scores_1c    = {'Value': 'C', 'Growth': 'A', 'Momentum': 'A', 'VGM': 'A'}
    scores_missing_vgm = {'Value': 'A', 'Growth': 'A', 'Momentum': 'A'}
    scores_vA_gA_mF_vgmF = {'Value':'A', 'Growth':'A', 'Momentum':'F', 'VGM':'F'}
    scores_vA_gB_mA_vgmA = {'Value':'A', 'Growth':'B', 'Momentum':'A', 'VGM':'A'}


    print("\n--- Testing check_buy_conditions (Profile ID 1: Rank 1, Style AAAB) ---")
    print(f"P1: Rank 1, All A: {check_buy_conditions(test_db_conn, 1, '1-Strong Buy', scores_all_a)} (Exp: True)")
    print(f"P1: Rank 1, 3A1B:  {check_buy_conditions(test_db_conn, 1, '1-Strong Buy', scores_3a1b)} (Exp: True)")
    print(f"P1: Rank 2, All A: {check_buy_conditions(test_db_conn, 1, '2-Buy', scores_all_a)} (Exp: False - Rank)")
    print(f"P1: Rank 1, 2A2B:  {check_buy_conditions(test_db_conn, 1, '1-Strong Buy', scores_2a2b)} (Exp: False - Style)")
    print(f"P1: Rank 1, 1C:    {check_buy_conditions(test_db_conn, 1, '1-Strong Buy', scores_1c)} (Exp: False - Style)")
    print(f"P1: Rank 1, MissingVGM: {check_buy_conditions(test_db_conn, 1, '1-Strong Buy', scores_missing_vgm)} (Exp: False - Style validation requires all 4 scores for pattern)")

    print("\n--- Testing check_buy_conditions (Profile ID 2: Rank 1/2, Style AAAA) ---")
    print(f"P2: Rank 1, All A: {check_buy_conditions(test_db_conn, 2, '1-Strong Buy', scores_all_a)} (Exp: True)")
    print(f"P2: Rank 2, All A: {check_buy_conditions(test_db_conn, 2, '2-Buy', scores_all_a)} (Exp: True)")
    print(f"P2: Rank 3, All A: {check_buy_conditions(test_db_conn, 2, '3-Hold', scores_all_a)} (Exp: False - Rank)")
    print(f"P2: Rank 1, 3A1B:  {check_buy_conditions(test_db_conn, 2, '1-Strong Buy', scores_3a1b)} (Exp: False - Style)")

    print("\n--- Testing check_buy_conditions (Profile ID 3: Rank 1 Only) ---")
    print(f"P3: Rank 1, All A: {check_buy_conditions(test_db_conn, 3, '1-Strong Buy', scores_all_a)} (Exp: True)")
    print(f"P3: Rank 1, 2A2B:  {check_buy_conditions(test_db_conn, 3, '1-Strong Buy', scores_2a2b)} (Exp: True - Style ignored as no style rule defined)")
    print(f"P3: Rank 2, All A: {check_buy_conditions(test_db_conn, 3, '2-Buy', scores_all_a)} (Exp: False - Rank)")

    print("\n--- Testing check_buy_conditions (Profile ID 4: Indiv Style V=A, G=A) ---")
    print(f"P4: Rank 5, V=A,G=A,M=F,VGM=F: {check_buy_conditions(test_db_conn, 4, '5-Strong Sell', scores_vA_gA_mF_vgmF)} (Exp: True - Rank ignored, M/VGM not defined as rules)")
    print(f"P4: Rank 1, V=A,G=B,M=A,VGM=A: {check_buy_conditions(test_db_conn, 4, '1-Strong Buy', scores_vA_gB_mA_vgmA)} (Exp: False - Growth rule G=A not met)")
    print(f"P4: Rank 1, MissingVGM for scores: {check_buy_conditions(test_db_conn, 4, '1-Strong Buy', scores_missing_vgm)} (Exp: True, as only V and G are checked by defined rules)")


    print("\n--- Testing check_buy_conditions (Profile ID 5: No Rules) ---")
    print(f"P5: Rank 1, All A: {check_buy_conditions(test_db_conn, 5, '1-Strong Buy', scores_all_a)} (Exp: False - No rules defined)")

    print("\n--- Testing check_buy_conditions (Profile ID 6: Indiv Style V=A, G=B) ---")
    print(f"P6: Rank 1, V=A,G=B (match): {check_buy_conditions(test_db_conn, 6, '1-Strong Buy', scores_vA_gB_mA_vgmA)} (Exp: True)")
    print(f"P6: Rank 1, V=A,G=A (G fail): {check_buy_conditions(test_db_conn, 6, '1-Strong Buy', scores_all_a)} (Exp: False)")


    print("\n--- Testing check_sell_conditions (using Profile ID 1 rules) ---")
    print(f"P1 Sell: Rank 1, All A (Don't Sell): {check_sell_conditions(test_db_conn, 1, '1-Strong Buy', scores_all_a)} (Exp: False)")
    print(f"P1 Sell: Rank 2, All A (Do Sell):    {check_sell_conditions(test_db_conn, 1, '2-Buy', scores_all_a)} (Exp: True)")
    print(f"P1 Sell: Rank 1, 2A2B (Do Sell):   {check_sell_conditions(test_db_conn, 1, '1-Strong Buy', scores_2a2b)} (Exp: True)")

    test_db_conn.close()
    print("\n--- End of Profile Logic Tests (using In-Memory DB) ---")
