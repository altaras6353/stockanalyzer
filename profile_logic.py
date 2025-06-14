import sqlite3
import re
import math

# --- Helper Functions ---
def grade_to_numeric(grade: str) -> int:
    if grade is None: return 99
    grade = grade.upper()
    mapping = {'A': 1, 'B': 2, 'C': 3, 'D': 3, 'F': 4} # D=3, F=4 as per problem doc
    return mapping.get(grade, 99)

def calculate_rating_score(style_scores_dict: dict) -> float:
    if not style_scores_dict: return float('inf')
    v_num = grade_to_numeric(style_scores_dict.get('Value'))
    g_num = grade_to_numeric(style_scores_dict.get('Growth'))
    m_num = grade_to_numeric(style_scores_dict.get('Momentum'))
    vgm_num = grade_to_numeric(style_scores_dict.get('VGM')) # Assuming VGM is also A-F and uses same mapping
    if 99 in (v_num, g_num, m_num, vgm_num): return float('inf')
    return (v_num + g_num + m_num) * vgm_num

# --- Standardized Entry Criteria ---
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

# --- Profile-Specific Exit Criteria ---
def check_exit_conditions(db_conn: sqlite3.Connection, profile_id: int,
                           current_zacks_rank_str: str, current_style_scores: dict,
                           entry_price: float | None, current_price: float | None) -> bool:
    temp_cursor_for_profile_type = db_conn.cursor()
    temp_cursor_for_profile_type.execute("SELECT profile_type FROM investor_profiles WHERE profile_id = ?", (profile_id,))
    profile_row_for_type = temp_cursor_for_profile_type.fetchone()

    if not profile_row_for_type:
        print(f"Warning: Profile ID {profile_id} not found. Defaulting to strict exit (sell).")
        return True
    profile_type = profile_row_for_type['profile_type']

    calculated_score = calculate_rating_score(current_style_scores)
    rank_is_not_1 = not (isinstance(current_zacks_rank_str, str) and current_zacks_rank_str.startswith("1"))
    score_is_penalty = (calculated_score == float('inf'))
    profit_pct = None
    if entry_price is not None and entry_price > 0 and current_price is not None and current_price > 0 :
        profit_pct = ((current_price - entry_price) / entry_price) * 100

    # Updated Exit Logic as per new rules:
    if profile_type == "Cautious":      # Exit if Rank is not 1 OR Calc Score > 4 OR Score is Invalid
        return rank_is_not_1 or calculated_score > 4 or score_is_penalty
    elif profile_type == "Hesitant":    # Exit if Rank is not 1 OR Calc Score > 5 OR Score is Invalid
        return rank_is_not_1 or calculated_score > 5 or score_is_penalty
    elif profile_type == "Brave":       # Exit if Rank is not 1 OR Calc Score > 6 OR Score is Invalid
        return rank_is_not_1 or calculated_score > 6 or score_is_penalty
    elif profile_type == "Reckless":    # Exit if Rank is not 1 OR Calc Score > 7 OR Score is Invalid
        return rank_is_not_1 or calculated_score > 7 or score_is_penalty
    elif profile_type == "Greedy2Pct":  # Exit if (Rank is not 1 OR Calc Score > 4 OR Score is Invalid) OR Profit >= 2%
        base_exit = rank_is_not_1 or calculated_score > 4 or score_is_penalty
        if profit_pct is not None and profit_pct >= 2.0: return True
        return base_exit
    elif profile_type == "Greedy3Pct":  # Exit if (Rank is not 1 OR Calc Score > 4 OR Score is Invalid) OR Profit >= 3%
        base_exit = rank_is_not_1 or calculated_score > 4 or score_is_penalty
        if profit_pct is not None and profit_pct >= 3.0: return True
        return base_exit
    elif profile_type == "Greedy4Pct":  # Exit if (Rank is not 1 OR Calc Score > 5 OR Score is Invalid) OR Profit >= 4%
        base_exit = rank_is_not_1 or calculated_score > 5 or score_is_penalty # Score threshold is > 5 here
        if profit_pct is not None and profit_pct >= 4.0: return True
        return base_exit
    else:
        print(f"Warning: Unknown profile_type '{profile_type}' for ID {profile_id}. Defaulting to strict exit.")
        return True

# --- Test Area ---
def setup_in_memory_db_for_profile_logic_tests(): # Returns connection
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE investor_profiles (profile_id INTEGER PRIMARY KEY, name TEXT, profile_type TEXT, description TEXT, is_active INTEGER)")
    # No profile_rules table needed for these tests as rules are now in profile_logic.py
    profiles = [
        (1, "Cautious Test", "Cautious", "Desc", 1), (2, "Hesitant Test", "Hesitant", "Desc", 1),
        (3, "Brave Test", "Brave", "Desc", 1), (4, "Reckless Test", "Reckless", "Desc", 1),
        (5, "Greedy2 Test", "Greedy2Pct", "Desc", 1), (6, "Greedy3 Test", "Greedy3Pct", "Desc", 1),
        (7, "Greedy4 Test", "Greedy4Pct", "Desc", 1),
        (8, "UnknownType Test", "Unknown", "Desc", 1) # For default exit
    ]
    cursor.executemany("INSERT INTO investor_profiles VALUES (?,?,?,?,?)", profiles)
    conn.commit()
    return conn

if __name__ == "__main__":
    print("--- Testing Profile Logic (Updated Scoring & Exit Strategies) ---")

    # Test grade_to_numeric
    print("\n--- Testing grade_to_numeric ---")
    assert grade_to_numeric('A') == 1, "Test Failed: A"
    assert grade_to_numeric('B') == 2, "Test Failed: B"
    assert grade_to_numeric('C') == 3, "Test Failed: C"
    assert grade_to_numeric('D') == 3, "Test Failed: D" # As per problem doc
    assert grade_to_numeric('F') == 4, "Test Failed: F" # As per problem doc
    assert grade_to_numeric('Z') == 99, "Test Failed: Z"
    assert grade_to_numeric(None) == 99, "Test Failed: None"
    print("grade_to_numeric tests passed.")

    # Test calculate_rating_score
    print("\n--- Testing calculate_rating_score ---")
    assert calculate_rating_score({'Value':'A','Growth':'A','Momentum':'A','VGM':'A'}) == 3, "Test Failed: All A" # (1+1+1)*1=3
    assert calculate_rating_score({'Value':'A','Growth':'A','Momentum':'A','VGM':'B'}) == 6, "Test Failed: AAA VGM B" # (1+1+1)*2=6
    assert calculate_rating_score({'Value':'A','Growth':'A','Momentum':'B','VGM':'A'}) == 4, "Test Failed: AAB VGM A" # (1+1+2)*1=4
    assert calculate_rating_score({'Value':'A','Growth':'B','Momentum':'C','VGM':'A'}) == 6, "Test Failed: ABC VGM A" # (1+2+3)*1=6
    assert calculate_rating_score({'Value':'A','Growth':'A','Momentum':'A','VGM':'F'}) == 12, "Test Failed: AAA VGM F" # (1+1+1)*4=12
    assert calculate_rating_score({'Value':'A','Growth':'A','Momentum':'A'}) == float('inf'), "Test Failed: Missing VGM"
    assert calculate_rating_score({'Value':'A','Growth':'Z','Momentum':'A','VGM':'A'}) == float('inf'), "Test Failed: Invalid Grade"
    assert calculate_rating_score({}) == float('inf'), "Test Failed: Empty dict"
    print("calculate_rating_score tests passed.")

    # Test standardized check_buy_conditions
    print("\n--- Testing standardized check_buy_conditions ---")
    all_a = {'Value':'A','Growth':'A','Momentum':'A','VGM':'A'}
    three_a_one_b = {'Value':'A','Growth':'B','Momentum':'A','VGM':'A'}
    two_a_two_b = {'Value':'A','Growth':'B','Momentum':'B','VGM':'A'}
    assert check_buy_conditions('1-Strong Buy', all_a) == True, "Buy Test Failed: Rank 1, All A"
    assert check_buy_conditions('1-Strong Buy', three_a_one_b) == True, "Buy Test Failed: Rank 1, 3A1B"
    assert check_buy_conditions('2-Buy', all_a) == False, "Buy Test Failed: Rank 2, All A"
    assert check_buy_conditions('1-Strong Buy', two_a_two_b) == False, "Buy Test Failed: Rank 1, 2A2B"
    assert check_buy_conditions('1-Strong Buy', {'Value':'A'}) == False, "Buy Test Failed: Rank 1, Missing score"
    print("check_buy_conditions tests passed.")

    test_db_conn = setup_in_memory_db_for_profile_logic_tests()
    print("\n--- Testing check_exit_conditions (using In-Memory DB & New Rules) ---")

    # Scores for testing exit conditions
    s_rank1_score3 = ('1-SB', {'Value':'A','Growth':'A','Momentum':'A','VGM':'A'}) # Score (1+1+1)*1 = 3
    s_rank1_score4 = ('1-SB', {'Value':'A','Growth':'A','Momentum':'B','VGM':'A'}) # Score (1+1+2)*1 = 4
    s_rank1_score5 = ('1-SB', {'Value':'B','Growth':'A','Momentum':'B','VGM':'A'}) # Score (2+1+2)*1 = 5
    s_rank1_score6 = ('1-SB', {'Value':'A','Growth':'B','Momentum':'C','VGM':'A'}) # Score (1+2+3)*1 = 6
    s_rank1_score7 = ('1-SB', {'Value':'B','Growth':'B','Momentum':'C','VGM':'A'}) # Score (2+2+3)*1 = 7
    s_rank1_score8 = ('1-SB', {'Value':'B','Growth':'C','Momentum':'C','VGM':'A'}) # Score (2+3+3)*1 = 8
    s_rank2_score3 = ('2-Buy', s_rank1_score3[1])
    s_rank1_score_inf = ('1-SB', {'Value':'Z','Growth':'A','Momentum':'A','VGM':'A'})


    # Cautious (ID 1): Exit if Rank is not 1 OR Calc Score > 4 OR Score is Invalid
    print("Cautious (ID 1): Exit if Rank != 1 or Score > 4 or Invalid")
    assert check_exit_conditions(test_db_conn,1,*s_rank1_score3,10,10) == False, "Cautious 1" # R1,S3 -> F
    assert check_exit_conditions(test_db_conn,1,*s_rank1_score4,10,10) == False, "Cautious 2" # R1,S4 -> F
    assert check_exit_conditions(test_db_conn,1,*s_rank1_score5,10,10) == True,  "Cautious 3" # R1,S5 (>4) -> T
    assert check_exit_conditions(test_db_conn,1,*s_rank2_score3,10,10) == True,  "Cautious 4" # R2 (!=1) -> T
    assert check_exit_conditions(test_db_conn,1,*s_rank1_score_inf,10,10) == True, "Cautious 5" # R1,Sinf -> T

    # Hesitant (ID 2): Exit if Rank is not 1 OR Calc Score > 5 OR Score is Invalid
    print("Hesitant (ID 2): Exit if Rank != 1 or Score > 5 or Invalid")
    assert check_exit_conditions(test_db_conn,2,*s_rank1_score5,10,10) == False, "Hesitant 1" # R1,S5 -> F
    assert check_exit_conditions(test_db_conn,2,*s_rank1_score6,10,10) == True,  "Hesitant 2" # R1,S6 (>5) -> T
    assert check_exit_conditions(test_db_conn,2,*s_rank2_score3,10,10) == True,  "Hesitant 3" # R2 (!=1) -> T

    # Brave (ID 3): Exit if Rank is not 1 OR Calc Score > 6 OR Score is Invalid
    print("Brave (ID 3): Exit if Rank != 1 or Score > 6 or Invalid")
    assert check_exit_conditions(test_db_conn,3,*s_rank1_score6,10,10) == False, "Brave 1" # R1,S6 -> F
    assert check_exit_conditions(test_db_conn,3,*s_rank1_score7,10,10) == True,  "Brave 2" # R1,S7 (>6) -> T
    assert check_exit_conditions(test_db_conn,3,*s_rank2_score3,10,10) == True,  "Brave 3" # R2 (!=1) -> T

    # Reckless (ID 4): Exit if Rank is not 1 OR Calc Score > 7 OR Score is Invalid
    print("Reckless (ID 4): Exit if Rank != 1 or Score > 7 or Invalid")
    assert check_exit_conditions(test_db_conn,4,*s_rank1_score7,10,10) == False, "Reckless 1" # R1,S7 -> F
    assert check_exit_conditions(test_db_conn,4,*s_rank1_score8,10,10) == True,  "Reckless 2" # R1,S8 (>7) -> T
    assert check_exit_conditions(test_db_conn,4,*s_rank2_score3,10,10) == True,  "Reckless 3" # R2 (!=1) -> T

    # Greedy2Pct (ID 5): Exit if (Rank != 1 or Score > 4 or Invalid) OR Profit >= 2%
    print("Greedy2Pct (ID 5): Exit if (Rank != 1 or Score > 4 or Invalid) OR Profit >= 2%")
    assert check_exit_conditions(test_db_conn,5,*s_rank1_score3,100,101.9) == False, "Greedy2 1" # R1,S3, Profit 1.9% -> F
    assert check_exit_conditions(test_db_conn,5,*s_rank1_score3,100,102.0) == True,  "Greedy2 2" # R1,S3, Profit 2.0% -> T
    assert check_exit_conditions(test_db_conn,5,*s_rank1_score5,100,101.0) == True,  "Greedy2 3" # R1,S5(>4) -> T
    assert check_exit_conditions(test_db_conn,5,*s_rank2_score3,100,101.0) == True,  "Greedy2 4" # R2(!=1) -> T

    # Greedy4Pct (ID 7): Exit if (Rank != 1 or Score > 5 or Invalid) OR Profit >= 4%
    print("Greedy4Pct (ID 7): Exit if (Rank != 1 or Score > 5 or Invalid) OR Profit >= 4%")
    assert check_exit_conditions(test_db_conn,7,*s_rank1_score5,100,103.9) == False, "Greedy4 1" # R1,S5, Profit 3.9% -> F
    assert check_exit_conditions(test_db_conn,7,*s_rank1_score5,100,104.0) == True,  "Greedy4 2" # R1,S5, Profit 4.0% -> T
    assert check_exit_conditions(test_db_conn,7,*s_rank1_score6,100,101.0) == True,  "Greedy4 3" # R1,S6(>5) -> T

    # Unknown Profile Type (ID 8)
    print("Unknown Profile (ID 8): Should always sell")
    assert check_exit_conditions(test_db_conn,8,*s_rank1_score3,10,10) == True, "UnknownType 1"

    print("check_exit_conditions tests passed.")
    test_db_conn.close()
    print("\n--- End of Profile Logic Tests ---")
