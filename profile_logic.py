import sqlite3
import re
import math

def grade_to_numeric(grade: str) -> int:
    if grade is None: return 99
    grade = grade.upper()
    mapping = {'A': 1, 'B': 2, 'C': 3, 'D': 3, 'F': 4}
    return mapping.get(grade, 99)

def calculate_rating_score(style_scores_dict: dict) -> float:
    if not style_scores_dict: return float('inf')
    v_num = grade_to_numeric(style_scores_dict.get('Value'))
    g_num = grade_to_numeric(style_scores_dict.get('Growth'))
    m_num = grade_to_numeric(style_scores_dict.get('Momentum'))
    vgm_num = grade_to_numeric(style_scores_dict.get('VGM'))
    if 99 in (v_num, g_num, m_num, vgm_num): return float('inf')
    return (v_num + g_num + m_num) * vgm_num

def check_buy_conditions(zacks_rank_str: str, style_scores_dict: dict) -> bool:
    if not isinstance(zacks_rank_str, str) or not zacks_rank_str.startswith("1"): return False
    if not style_scores_dict: return False
    required_keys = ['Value', 'Growth', 'Momentum', 'VGM']
    if not all(key in style_scores_dict and style_scores_dict[key] is not None for key in required_keys): return False
    scores = [style_scores_dict.get(k) for k in required_keys]
    if any(s not in ['A', 'B', 'C', 'D', 'F'] for s in scores): return False
    count_a = scores.count('A'); count_b = scores.count('B')
    if not ((count_a == 4) or (count_a == 3 and count_b == 1)): return False
    return True

def check_exit_conditions(db_conn: sqlite3.Connection, profile_id: int,
                           current_zacks_rank_str: str, current_style_scores: dict,
                           entry_price: float | None, current_price: float | None) -> bool:
    cursor = db_conn.cursor()
    # Ensure row_factory is set on the connection for dict-like access if not already
    # For this function, assuming db_conn might not have it, so direct indexing after fetch.
    # If db_conn is guaranteed to have row_factory=sqlite3.Row, then profile_row['profile_type'] is better.
    cursor.execute("SELECT profile_type FROM investor_profiles WHERE profile_id = ?", (profile_id,))
    profile_row_tuple = cursor.fetchone()

    if not profile_row_tuple:
        print(f"Warning: Profile ID {profile_id} not found. Defaulting to strict exit (sell).")
        return True

    profile_type = profile_row_tuple[0] # Access by index as row_factory might not be set on passed conn
                                     # Or, ensure all conns passed to this have row_factory set.
                                     # For now, assuming index 0 for safety if called from various places.
                                     # If called from scanner.py, its conn has row_factory. Let's use that.
    # Re-evaluating: the conn from scanner *does* have row_factory.
    # So, if profile_row was a dict-like row, profile_row['profile_type'] would be ideal.
    # Let's assume the passed db_conn has row_factory set.
    # No, the cursor created from db_conn does not automatically inherit row_factory.
    # The connection itself should have it set.
    # The `get_db_connection` in scanner.py sets it. `profile_logic.py`'s own test setup also sets it.
    # So, `profile_row['profile_type']` should be safe.

    # Fetching again with a new cursor from the passed connection
    # This cursor will inherit row_factory from db_conn if set there.
    # It's cleaner to just use the fetched tuple if row_factory isn't guaranteed on the connection object itself
    # for all callers. The test setup for profile_logic now sets it on its connection. Scanner's connection also has it.
    # So, using profile_row['profile_type'] should be fine.

    # Re-fetch with a cursor that definitely uses the connection's row_factory
    temp_cursor_for_profile_type = db_conn.cursor() # New cursor from the connection
    temp_cursor_for_profile_type.execute("SELECT profile_type FROM investor_profiles WHERE profile_id = ?", (profile_id,))
    profile_row_for_type = temp_cursor_for_profile_type.fetchone() # This will be a Row object if conn.row_factory was set

    if not profile_row_for_type:
         print(f"Warning: Profile ID {profile_id} not found (refetch). Defaulting to strict exit (sell).")
         return True
    profile_type = profile_row_for_type['profile_type'] # Access by column name

    calculated_score = calculate_rating_score(current_style_scores)
    rank_no_longer_1 = not (isinstance(current_zacks_rank_str, str) and current_zacks_rank_str.startswith("1"))
    score_is_penalty = (calculated_score == float('inf'))
    profit_pct = None
    if entry_price is not None and entry_price > 0 and current_price is not None and current_price > 0 : # ensure current_price > 0 too
        profit_pct = ((current_price - entry_price) / entry_price) * 100

    if profile_type == "Cautious":
        rank_is_exit = not (isinstance(current_zacks_rank_str, str) and (current_zacks_rank_str.startswith("1") or current_zacks_rank_str.startswith("2")))
        return rank_is_exit or calculated_score > 4 or score_is_penalty
    elif profile_type == "Hesitant":
        return rank_no_longer_1 or calculated_score > 5 or score_is_penalty
    elif profile_type == "Brave":
        rank_is_exit = not (isinstance(current_zacks_rank_str, str) and (current_zacks_rank_str.startswith("1") or current_zacks_rank_str.startswith("2") or current_zacks_rank_str.startswith("3")))
        return rank_is_exit or calculated_score > 6 or score_is_penalty
    elif profile_type == "Reckless":
        rank_is_exit = not (isinstance(current_zacks_rank_str, str) and (current_zacks_rank_str.startswith("1") or current_zacks_rank_str.startswith("2") or current_zacks_rank_str.startswith("3") or current_zacks_rank_str.startswith("4")))
        return rank_is_exit or score_is_penalty
    elif profile_type == "Greedy2Pct":
        base_exit = rank_no_longer_1 or calculated_score > 4 or score_is_penalty
        if profit_pct is not None and profit_pct > 2.0: return True
        return base_exit
    elif profile_type == "Greedy3Pct":
        base_exit = rank_no_longer_1 or calculated_score > 4 or score_is_penalty
        if profit_pct is not None and profit_pct > 3.0: return True
        return base_exit
    elif profile_type == "Greedy4Pct":
        base_exit = rank_no_longer_1 or calculated_score > 4 or score_is_penalty
        if profit_pct is not None and profit_pct > 4.0: return True
        return base_exit
    else:
        print(f"Warning: Unknown profile_type '{profile_type}' for ID {profile_id}. Defaulting to strict exit.")
        return True

def setup_in_memory_db_for_profile_logic_tests(): # Returns connection
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row # IMPORTANT: Set row_factory on the connection
    cursor = conn.cursor()
    # ... (table creations as before)
    cursor.execute("CREATE TABLE investor_profiles (profile_id INTEGER PRIMARY KEY, name TEXT, profile_type TEXT, description TEXT, is_active INTEGER)")
    cursor.execute("CREATE TABLE profile_rules (rule_id INTEGER PRIMARY KEY AUTOINCREMENT, profile_id INTEGER, category TEXT, condition TEXT, value1 TEXT, value2 TEXT, FOREIGN KEY (profile_id) REFERENCES investor_profiles (profile_id))")

    profiles = [
        (1, "Cautious Test", "Cautious", "Desc", 1), (2, "Hesitant Test", "Hesitant", "Desc", 1),
        (3, "Brave Test", "Brave", "Desc", 1), (4, "Reckless Test", "Reckless", "Desc", 1),
        (5, "Greedy2 Test", "Greedy2Pct", "Desc", 1), (6, "Greedy3 Test", "Greedy3Pct", "Desc", 1),
        (7, "Greedy4 Test", "Greedy4Pct", "Desc", 1)
    ]
    cursor.executemany("INSERT INTO investor_profiles VALUES (?,?,?,?,?)", profiles)
    # No need to insert into profile_rules as check_buy_conditions is standardized
    # and check_exit_conditions uses profile_type, not profile_rules table.
    conn.commit()
    return conn

if __name__ == "__main__":
    print("--- Testing Profile Logic (New Scoring & Exit Strategies) ---")
    # ... (grade_to_numeric, calculate_rating_score, check_buy_conditions tests as before) ...
    print("\n--- Testing grade_to_numeric ---")
    print(f"A -> {grade_to_numeric('A')} (Exp: 1)")
    print(f"F -> {grade_to_numeric('F')} (Exp: 4)")
    print(f"None -> {grade_to_numeric(None)} (Exp: 99)")

    print("\n--- Testing calculate_rating_score ---")
    print(f"All A's: {calculate_rating_score({'Value':'A','Growth':'A','Momentum':'A','VGM':'A'})} (Exp: 3)")
    print(f"A,A,A,B: {calculate_rating_score({'Value':'A','Growth':'A','Momentum':'A','VGM':'B'})} (Exp: 6)")
    print(f"Missing VGM: {calculate_rating_score({'Value':'A','Growth':'A','Momentum':'A'})} (Exp: inf)")

    print("\n--- Testing standardized check_buy_conditions ---")
    all_a = {'Value':'A','Growth':'A','Momentum':'A','VGM':'A'}
    three_a_one_b = {'Value':'A','Growth':'B','Momentum':'A','VGM':'A'}
    print(f"Rank 1, All A: {check_buy_conditions('1-Strong Buy', all_a)} (Exp: True)")
    print(f"Rank 1, 3A1B: {check_buy_conditions('1-Strong Buy', three_a_one_b)} (Exp: True)")

    test_db_conn = setup_in_memory_db_for_profile_logic_tests()
    print("\n--- Testing check_exit_conditions (using In-Memory DB) ---")
    scores_good = {'Value':'A','Growth':'A','Momentum':'A','VGM':'A'} # Calc = 3
    scores_caution_borderline = {'Value':'A','Growth':'A','Momentum':'B','VGM':'A'} # Calc = 4
    scores_caution_sell = {'Value':'B','Growth':'A','Momentum':'B','VGM':'A'}    # Calc = 5
    scores_hesitant_sell_vgm_b = {'Value':'A','Growth':'C','Momentum':'A','VGM':'B'} # (1+3+1)*2 = 10
    scores_inf = {'Value':'Z','Growth':'A','Momentum':'A','VGM':'A'}

    print("Cautious Profile (ID 1): Sell if Rank > 2 or Score > 4")
    print(f"  Rank 1, Score 3 (Good): {check_exit_conditions(test_db_conn, 1, '1-SB', scores_good, 10, 10)} (Exp: False)")
    print(f"  Rank 2, Score 4 (Border): {check_exit_conditions(test_db_conn, 1, '2-Buy', scores_caution_borderline, 10, 10)} (Exp: False)")
    print(f"  Rank 3, Score 3 (Rank fail): {check_exit_conditions(test_db_conn, 1, '3-H', scores_good, 10, 10)} (Exp: True)")
    print(f"  Rank 1, Score 5 (Score fail): {check_exit_conditions(test_db_conn, 1, '1-SB', scores_caution_sell, 10, 10)} (Exp: True)")
    print(f"  Rank 1, Score inf (Penalty): {check_exit_conditions(test_db_conn, 1, '1-SB', scores_inf, 10, 10)} (Exp: True)")

    print("Hesitant Profile (ID 2): Sell if Rank != 1 or Score > 5")
    # scores_hesitant_sell = {'Value':'A','Growth':'C','Momentum':'A','VGM':'A'} # Calc = 5
    print(f"  Rank 1, Score 5 (Border): {check_exit_conditions(test_db_conn, 2, '1-SB', {'Value':'A','Growth':'C','Momentum':'A','VGM':'A'}, 10, 10)} (Exp: False)")
    print(f"  Rank 1, Score 10 (Score fail): {check_exit_conditions(test_db_conn, 2, '1-SB', scores_hesitant_sell_vgm_b, 10, 10)} (Exp: True)")

    print("Greedy2Pct Profile (ID 5): Sell if (Rank != 1 or Score > 4) OR Profit > 2%")
    print(f"  Base OK, Profit 1% (No Sell): {check_exit_conditions(test_db_conn, 5, '1-SB', scores_good, 100, 101)} (Exp: False)")
    print(f"  Base OK, Profit 3% (Sell): {check_exit_conditions(test_db_conn, 5, '1-SB', scores_good, 100, 103)} (Exp: True)")
    print(f"  Base OK, No prices (No Sell by profit): {check_exit_conditions(test_db_conn, 5, '1-SB', scores_good, None, None)} (Exp: False)")
    print(f"  Base OK, current_price=0 (No Sell by profit): {check_exit_conditions(test_db_conn, 5, '1-SB', scores_good, 100, 0)} (Exp: False)")


    test_db_conn.close()
    print("\n--- End of Profile Logic Tests ---")
