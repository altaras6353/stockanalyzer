import sqlite3
import datetime
import requests

# Import generalized functions
from rule_parser import parse_profile_rules
from profile_logic import check_buy_conditions, check_sell_conditions
# Assuming database_setup.py provides DB_NAME and functions to ensure schema
import database_setup as db_setup # Using an alias for clarity

PROFILE_ID_1_FALLBACK = 1 # Fallback for specific uses if needed, though logic is now generic
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

# Helper to get DB connection (can also be imported from database_setup)
def get_db_connection(db_name=db_setup.DB_NAME):
    conn = sqlite3.connect(db_name)
    conn.row_factory = sqlite3.Row # Enable column access by name
    cursor = conn.cursor()
    return conn, cursor

def scan_and_update_all_active_profiles():
    """
    Scans for new stocks, updates currently held stocks, and processes sales
    for ALL active investor profiles based on their parsed rules.
    """
    print(f"\n--- Starting scan for ALL ACTIVE PROFILES ---")
    conn, cursor = get_db_connection()
    now_iso_timestamp = datetime.datetime.now().isoformat()

    # Fetch all active profiles
    cursor.execute("SELECT profile_id, name, description FROM investor_profiles WHERE is_active=1")
    active_profiles = cursor.fetchall() # List of Row objects

    if not active_profiles:
        print("No active profiles found to scan.")
        conn.close()
        return

    print(f"Found {len(active_profiles)} active profile(s) to process.")

    # --- Part 1: Fetch Main Page for Candidate Stocks (once for all profiles) ---
    main_page_html_content = None
    try:
        print("Attempting to fetch main page (https://www.zacks.com/) live...")
        response = requests.get('https://www.zacks.com/', headers=HEADERS, timeout=10)
        response.raise_for_status()
        main_page_html_content = response.text
        print("Successfully fetched main page live.")
    except Exception as e:
        print(f"Failed to fetch main page live: {e}. Falling back to local main_page.html.")
        try:
            with open("main_page.html", "r", encoding="utf-8") as f:
                main_page_html_content = f.read()
            print("Loaded main page from local main_page.html.")
        except FileNotFoundError:
            print("CRITICAL Error: main_page.html not found for fallback. Cannot proceed.")
            conn.close()
            return

    # Import here to avoid circular if parse_main_page also imports from scanner (it doesn't currently)
    from parse_main_page import extract_top_vgm_stocks
    candidate_stocks = extract_top_vgm_stocks(main_page_html_content)
    print(f"Found {len(candidate_stocks)} candidates from main page analysis.")

    # --- Loop through each active profile ---
    for profile_row in active_profiles:
        profile_id = profile_row['profile_id']
        profile_name = profile_row['name']
        profile_description = profile_row['description']

        print(f"\n=== Processing Profile ID: {profile_id} ({profile_name}) ===")
        parsed_rules = parse_profile_rules(profile_description)

        if not parsed_rules or not ('zacks_rank_condition' in parsed_rules or 'style_pattern' in parsed_rules):
            print(f"Skipping Profile ID {profile_id} ({profile_name}) due to empty or invalid rules from description: '{profile_description}' -> {parsed_rules}")
            continue
        print(f"Applying rules for Profile {profile_id}: {parsed_rules}")

        new_buys_count = 0
        # --- Part 2: Process Candidate Stocks for Potential Buys for current profile ---
        # Import here to avoid potential circular dependency issues if called at top level by other modules
        from parse_stock_page import extract_stock_ratings

        for candidate in candidate_stocks:
            ticker = candidate.get('Ticker Symbol')
            company_name = candidate.get('Company Name')
            url = candidate.get('Stock Page URL')

            if not ticker or not url: continue

            print(f"\n  Processing candidate for Profile {profile_id}: {ticker} - {company_name}")

            # Fetch individual stock page details
            individual_page_html_content = None
            try:
                # print(f"    Attempting live fetch for {ticker} ({url})...")
                response_stock = requests.get(url, headers=HEADERS, timeout=10)
                response_stock.raise_for_status()
                individual_page_html_content = response_stock.text
                # print(f"    Successfully fetched page for {ticker} live.")
            except Exception as e:
                # print(f"    Failed live fetch for {ticker}: {e}. Falling back to local sample.")
                try:
                    with open("individual_stock_page.html", "r", encoding="utf-8") as f:
                        individual_page_html_content = f.read()
                    # print(f"    Loaded ratings for {ticker} from local individual_stock_page.html (fallback).")
                except FileNotFoundError:
                    print(f"    CRITICAL: individual_stock_page.html fallback not found for {ticker}. Skipping.")
                    continue

            ratings_data = extract_stock_ratings(individual_page_html_content)
            current_zacks_rank_str = ratings_data.get('Zacks Rank')
            current_style_scores_dict = {k: ratings_data.get(k) for k in ['Value', 'Growth', 'Momentum', 'VGM']}

            # print(f"    Ratings for {ticker}: Rank='{current_zacks_rank_str}', Scores={current_style_scores_dict}")

            if check_buy_conditions(parsed_rules, current_zacks_rank_str, current_style_scores_dict):
                print(f"  BUY condition MET for {ticker} for Profile {profile_id}.")
                cursor.execute("SELECT holding_id FROM stock_holdings WHERE profile_id=? AND ticker=?", (profile_id, ticker))
                if cursor.fetchone() is None:
                    print(f"    Adding {ticker} to holdings for Profile {profile_id}...")
                    # ... (INSERT logic as before, using profile_id) ...
                    entry_values = (
                        profile_id, ticker, company_name, now_iso_timestamp,
                        current_zacks_rank_str, current_style_scores_dict.get('Value'),
                        current_style_scores_dict.get('Growth'), current_style_scores_dict.get('Momentum'),
                        current_style_scores_dict.get('VGM'), now_iso_timestamp,
                        current_zacks_rank_str, current_style_scores_dict.get('Value'),
                        current_style_scores_dict.get('Growth'), current_style_scores_dict.get('Momentum'),
                        current_style_scores_dict.get('VGM'), f"Initial scan buy for profile {profile_id}"
                    )
                    cursor.execute('''
                    INSERT INTO stock_holdings (
                        profile_id, ticker, company_name, entry_timestamp,
                        entry_zacks_rank, entry_style_value, entry_style_growth, entry_style_momentum, entry_style_vgm,
                        last_checked_timestamp, current_zacks_rank, current_style_value, current_style_growth,
                        current_style_momentum, current_style_vgm, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', entry_values)
                    new_buys_count += 1
                else:
                    print(f"    {ticker} already in holdings for Profile {profile_id}.")
            # else:
            #     print(f"  Buy condition NOT MET for {ticker} for Profile {profile_id}.")
        conn.commit()
        print(f"  Profile {profile_id} candidate scan complete. New buys for this profile: {new_buys_count}")

        # --- Part 3: Re-check Tracked Stocks for current profile ---
        print(f"\n  --- Re-checking tracked stocks for Profile ID: {profile_id} ---")
        cursor.execute('''
            SELECT holding_id, ticker, company_name,
                   entry_timestamp, entry_zacks_rank, entry_style_value,
                   entry_style_growth, entry_style_momentum, entry_style_vgm
            FROM stock_holdings WHERE profile_id=?
        ''', (profile_id,))
        tracked_stocks_for_profile = cursor.fetchall()
        print(f"  Found {len(tracked_stocks_for_profile)} stocks in holdings for Profile {profile_id}.")

        sold_count_profile = 0
        updated_count_profile = 0
        for stock_row in tracked_stocks_for_profile:
            holding_id, ticker, company_name, entry_ts, ezr, esv, esg, esm, esvgm = stock_row # Unpack tuple directly
            print(f"\n    Re-checking held stock for Profile {profile_id}: {ticker} (Holding ID: {holding_id})")

            stock_page_url = f"https://www.zacks.com/stock/quote/{ticker}"
            # ... (Fetch individual page HTML for recheck, with fallback - same as above) ...
            individual_page_html_content_recheck = None
            try:
                response_recheck = requests.get(stock_page_url, headers=HEADERS, timeout=10)
                response_recheck.raise_for_status()
                individual_page_html_content_recheck = response_recheck.text
            except Exception: # Simplified fallback
                try:
                    with open("individual_stock_page.html", "r", encoding="utf-8") as f:
                        individual_page_html_content_recheck = f.read()
                    print(f"      Used fallback for {ticker} re-check.")
                except FileNotFoundError:
                    print(f"      CRITICAL: Fallback HTML not found for {ticker} re-check. Skipping update.")
                    continue

            ratings_data_recheck = extract_stock_ratings(individual_page_html_content_recheck)
            new_zacks_rank_str = ratings_data_recheck.get('Zacks Rank')
            new_style_scores_dict = {k: ratings_data_recheck.get(k) for k in ['Value', 'Growth', 'Momentum', 'VGM']}
            # print(f"      New ratings for {ticker}: Rank='{new_zacks_rank_str}', Scores={new_style_scores_dict}")

            # Update stock_holdings
            # ... (UPDATE logic as before, using holding_id) ...
            update_values = (
                now_iso_timestamp, new_zacks_rank_str,
                new_style_scores_dict.get('Value'), new_style_scores_dict.get('Growth'),
                new_style_scores_dict.get('Momentum'), new_style_scores_dict.get('VGM'),
                f"Re-checked at {now_iso_timestamp}", holding_id
            )
            cursor.execute('''
                UPDATE stock_holdings SET
                last_checked_timestamp=?, current_zacks_rank=?,
                current_style_value=?, current_style_growth=?,
                current_style_momentum=?, current_style_vgm=?, notes=?
                WHERE holding_id=?
            ''', update_values)
            updated_count_profile += 1

            if check_sell_conditions(parsed_rules, new_zacks_rank_str, new_style_scores_dict):
                print(f"    SELL condition MET for {ticker} for Profile {profile_id}. Logging and removing.")
                # ... (INSERT to trade_logs and DELETE from stock_holdings logic as before) ...
                trade_log_values = (
                    profile_id, ticker, company_name, entry_ts, ezr, esv, esg, esm, esvgm,
                    now_iso_timestamp, new_zacks_rank_str, new_style_scores_dict.get('Value'),
                    new_style_scores_dict.get('Growth'), new_style_scores_dict.get('Momentum'),
                    new_style_scores_dict.get('VGM'), 0.0, "Criteria no longer met by profile rules."
                )
                cursor.execute('''
                INSERT INTO trade_logs (
                    profile_id, ticker, company_name, entry_timestamp, entry_zacks_rank,
                    entry_style_value, entry_style_growth, entry_style_momentum, entry_style_vgm,
                    exit_timestamp, exit_zacks_rank, exit_style_value, exit_style_growth,
                    exit_style_momentum, exit_style_vgm, return_percentage, reason_for_exit
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', trade_log_values)
                cursor.execute("DELETE FROM stock_holdings WHERE holding_id=?", (holding_id,))
                sold_count_profile += 1
            # else:
            #     print(f"    Sell condition NOT MET for {ticker} for Profile {profile_id}.")
        conn.commit()
        print(f"  Profile {profile_id} re-check complete. Updated: {updated_count_profile}, Sold: {sold_count_profile}")
        print(f"=== Profile ID: {profile_id} ({profile_name}) processing complete. ===")

    conn.close()
    print("\n--- Scan for ALL ACTIVE PROFILES complete. ---")


if __name__ == "__main__":
    print("--- Running Scanner Test (Generalized for All Active Profiles) ---")

    # Ensure DB and initial profile exist
    temp_conn_main, temp_cursor_main = get_db_connection()
    print("Ensuring database tables and initial profile exist via database_setup.py...")
    db_setup.create_tables(temp_cursor_main) # Call from imported module
    temp_conn_main.commit()
    db_setup.add_initial_profile(temp_conn_main, temp_cursor_main) # Call from imported module
    print("Database structure and Profile #1 (description updated for parser) confirmed.")

    # Optional: Add a second profile for testing multiple profile logic
    try:
        profile2_name = "Profile 2 - Rank 1or2, All A Styles"
        profile2_desc = "Zacks Rank: 1 or 2. Style Scores: All A (Value,Growth,Momentum,VGM)."
        temp_cursor_main.execute("SELECT profile_id FROM investor_profiles WHERE name = ?", (profile2_name,))
        if temp_cursor_main.fetchone() is None:
            temp_cursor_main.execute("INSERT INTO investor_profiles (name, description, is_active) VALUES (?, ?, ?)",
                               (profile2_name, profile2_desc, 1))
            temp_conn_main.commit()
            print(f"Added '{profile2_name}' for testing.")
        else:
            print(f"'{profile2_name}' already exists.")
    except Exception as e:
        print(f"Error adding second test profile: {e}")
    finally:
        if temp_conn_main:
            temp_conn_main.close()

    scan_and_update_all_active_profiles()

    print("\n--- Verifying Database Contents Post-Scan (All Profiles) ---")
    final_conn_main, final_cursor_main = get_db_connection()
    print("\nStock Holdings (All Profiles):")
    for row in final_cursor_main.execute("SELECT profile_id, ticker, company_name, entry_zacks_rank, current_zacks_rank FROM stock_holdings"):
        print(dict(row)) # Print as dict due to row_factory

    print("\nTrade Logs (All Profiles):")
    for row in final_cursor_main.execute("SELECT profile_id, ticker, company_name, entry_zacks_rank, exit_zacks_rank, reason_for_exit FROM trade_logs"):
        print(dict(row))
    final_conn_main.close()
    print("\n--- Generalized Scanner Test Complete ---")
