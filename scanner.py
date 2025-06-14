import sqlite3
import datetime
import requests

from price_fetcher import get_current_price
from profile_logic import check_buy_conditions, check_exit_conditions
import database_setup as db_setup

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
last_raw_scan_results = []

def get_db_connection(db_name=db_setup.DB_NAME):
    conn = sqlite3.connect(db_name)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def scan_and_update_all_active_profiles():
    global last_raw_scan_results
    print(f"\n--- SCANNER: Starting scan for ALL ACTIVE PROFILES (with Price Fetching & New Logic) ---")

    from parse_main_page import extract_top_vgm_stocks
    from parse_stock_page import extract_stock_ratings

    db_conn = get_db_connection()
    cursor = db_conn.cursor()
    now_iso_timestamp = datetime.datetime.now().isoformat()

    # Fetch only profiles that have a profile_type (i.e., the 7 predefined ones)
    cursor.execute("SELECT profile_id, name FROM investor_profiles WHERE is_active=1 AND profile_type IS NOT NULL")
    active_profiles = cursor.fetchall()

    if not active_profiles:
        print("SCANNER: No active profiles (with a defined profile_type) found."); db_conn.close(); return
    print(f"SCANNER: Found {len(active_profiles)} active profile(s) with defined types.")

    main_page_html_content = None
    try:
        response = requests.get('https://www.zacks.com/', headers=HEADERS, timeout=10)
        response.raise_for_status(); main_page_html_content = response.text
        print("SCANNER: Successfully fetched main page live.")
    except Exception as e:
        print(f"SCANNER: Failed to fetch main page live: {e}. Falling back to local.")
        try:
            with open("main_page.html", "r", encoding="utf-8") as f: main_page_html_content = f.read()
        except FileNotFoundError:
            print("SCANNER CRITICAL: main_page.html fallback not found."); db_conn.close(); return

    candidate_stocks_summary = extract_top_vgm_stocks(main_page_html_content)
    print(f"SCANNER: Found {len(candidate_stocks_summary)} candidate summaries from main page.")

    detailed_candidate_stocks_temp = []
    print(f"\nSCANNER: Pre-fetching details for {len(candidate_stocks_summary)} candidates...")
    for candidate_summary in candidate_stocks_summary:
        ticker = candidate_summary.get('Ticker Symbol'); company_name = candidate_summary.get('Company Name'); url = candidate_summary.get('Stock Page URL')
        if not ticker or not url: continue

        # print(f"  SCANNER: Fetching details for {ticker}...") # Verbose, can be enabled for debug
        individual_page_html_content = None
        try:
            response_stock = requests.get(url, headers=HEADERS, timeout=10); response_stock.raise_for_status()
            individual_page_html_content = response_stock.text
        except Exception as e_stock:
            # print(f"    SCANNER: Failed live fetch for {ticker}: {e_stock}. Using fallback HTML.") # Verbose
            try:
                with open("individual_stock_page.html", "r", encoding="utf-8") as f: individual_page_html_content = f.read()
            except FileNotFoundError: print(f"    SCANNER CRITICAL: Fallback HTML for {ticker} not found. Skipping."); continue

        ratings_data = extract_stock_ratings(individual_page_html_content)
        detailed_candidate = {'Company Name': company_name, 'Ticker Symbol': ticker, 'Stock Page URL': url,
                              'Zacks Rank': ratings_data.get('Zacks Rank'), 'Value Score': ratings_data.get('Value'),
                              'Growth Score': ratings_data.get('Growth'), 'Momentum Score': ratings_data.get('Momentum'),
                              'VGM Score': ratings_data.get('VGM')}
        detailed_candidate_stocks_temp.append(detailed_candidate)

    last_raw_scan_results = detailed_candidate_stocks_temp
    print(f"SCANNER: Pre-fetching complete. {len(last_raw_scan_results)} candidates have detailed data.")

    for profile_row in active_profiles:
        profile_id = profile_row['profile_id']; profile_name = profile_row['name']
        print(f"\n=== SCANNER: Processing Profile ID: {profile_id} ({profile_name}) ===")
        new_buys_count = 0
        for detailed_candidate in last_raw_scan_results:
            ticker = detailed_candidate['Ticker Symbol']; company_name = detailed_candidate['Company Name']
            current_zacks_rank_str = detailed_candidate['Zacks Rank']
            current_style_scores_dict = {k: detailed_candidate[f'{k} Score'] for k in ['Value', 'Growth', 'Momentum', 'VGM']}

            if check_buy_conditions(current_zacks_rank_str, current_style_scores_dict):
                # print(f"  SCANNER: BUY condition MET for {ticker} for Profile {profile_id}.") # Verbose
                cursor.execute("SELECT holding_id FROM stock_holdings WHERE profile_id=? AND ticker=?", (profile_id, ticker))
                if cursor.fetchone() is None:
                    entry_price = get_current_price(ticker)
                    if entry_price is None or entry_price <= 0:
                        print(f"    SCANNER: Could not fetch valid entry price for {ticker}. Skipping buy for Profile {profile_id}.")
                        continue
                    print(f"    SCANNER: Adding {ticker} (Price: {entry_price:.2f}) to holdings for Profile {profile_id}.")
                    entry_values = (profile_id, ticker, company_name, now_iso_timestamp, current_zacks_rank_str,
                                    current_style_scores_dict.get('Value'), current_style_scores_dict.get('Growth'),
                                    current_style_scores_dict.get('Momentum'), current_style_scores_dict.get('VGM'),
                                    entry_price, now_iso_timestamp, current_zacks_rank_str, current_style_scores_dict.get('Value'),
                                    current_style_scores_dict.get('Growth'), current_style_scores_dict.get('Momentum'),
                                    current_style_scores_dict.get('VGM'), f"Initial scan buy for profile {profile_id}")
                    cursor.execute("INSERT INTO stock_holdings (profile_id, ticker, company_name, entry_timestamp, entry_zacks_rank, entry_style_value, entry_style_growth, entry_style_momentum, entry_style_vgm, entry_price, last_checked_timestamp, current_zacks_rank, current_style_value, current_style_growth, current_style_momentum, current_style_vgm, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", entry_values)
                    new_buys_count += 1
        db_conn.commit()
        if new_buys_count > 0: print(f"  SCANNER: New buys for Profile {profile_id}: {new_buys_count}")

        print(f"  SCANNER: Re-checking tracked stocks for Profile ID: {profile_id}...")
        cursor.execute("SELECT holding_id, ticker, company_name, entry_timestamp, entry_zacks_rank, entry_style_value, entry_style_growth, entry_style_momentum, entry_style_vgm, entry_price FROM stock_holdings WHERE profile_id=?", (profile_id,))
        tracked_stocks_for_profile = cursor.fetchall()
        if not tracked_stocks_for_profile: print(f"    SCANNER: No stocks currently held for Profile {profile_id}.")

        sold_count_profile = 0; updated_count_profile = 0
        for stock_row in tracked_stocks_for_profile:
            # ... (unpacking stock_row fields)
            holding_id=stock_row['holding_id']; ticker=stock_row['ticker']; company_name=stock_row['company_name']; entry_ts=stock_row['entry_timestamp']
            ezr=stock_row['entry_zacks_rank']; esv=stock_row['entry_style_value']; esg=stock_row['entry_style_growth']
            esm=stock_row['entry_style_momentum']; esvgm=stock_row['entry_style_vgm']; entry_price_from_db=stock_row['entry_price']

            # print(f"    SCANNER: Re-checking {ticker} (Entry Price: {entry_price_from_db})") # Verbose
            stock_page_url = f"https://www.zacks.com/stock/quote/{ticker}"
            individual_page_html_content_recheck = None
            try:
                response_recheck = requests.get(stock_page_url, headers=HEADERS, timeout=10); response_recheck.raise_for_status()
                individual_page_html_content_recheck = response_recheck.text
            except Exception:
                try:
                    with open("individual_stock_page.html", "r", encoding="utf-8") as f: individual_page_html_content_recheck = f.read()
                except FileNotFoundError: print(f"      SCANNER CRITICAL: Fallback HTML for {ticker} re-check not found. Skipping."); continue

            ratings_data_recheck = extract_stock_ratings(individual_page_html_content_recheck)
            new_zacks_rank_str = ratings_data_recheck.get('Zacks Rank')
            new_style_scores_dict = {k: ratings_data_recheck.get(k) for k in ['Value', 'Growth', 'Momentum', 'VGM']}
            current_price = get_current_price(ticker)
            notes_update = f"Re-checked at {now_iso_timestamp}."
            if current_price is None or current_price <= 0:
                print(f"      SCANNER: Could not fetch valid current price for {ticker}. Sell evaluation skipped.")
                notes_update += " Current price fetch failed."

            update_values = (now_iso_timestamp, new_zacks_rank_str, new_style_scores_dict.get('Value'), new_style_scores_dict.get('Growth'), new_style_scores_dict.get('Momentum'), new_style_scores_dict.get('VGM'), notes_update, holding_id)
            cursor.execute("UPDATE stock_holdings SET last_checked_timestamp=?, current_zacks_rank=?, current_style_value=?, current_style_growth=?, current_style_momentum=?, current_style_vgm=?, notes=? WHERE holding_id=?", update_values)
            updated_count_profile +=1

            if current_price is not None and current_price > 0:
                if check_exit_conditions(db_conn, profile_id, new_zacks_rank_str, new_style_scores_dict, entry_price_from_db, current_price):
                    print(f"      SCANNER: SELL condition MET for {ticker} for Profile {profile_id}.")
                    return_pct = 0.0
                    if entry_price_from_db is not None and entry_price_from_db > 0:
                        return_pct = ((current_price - entry_price_from_db) / entry_price_from_db) * 100
                    print(f"        Entry: {entry_price_from_db}, Exit: {current_price}, Return: {return_pct:.2f}%")
                    trade_log_values = (profile_id, ticker, company_name, entry_ts, ezr, esv, esg, esm, esvgm, entry_price_from_db, now_iso_timestamp, new_zacks_rank_str, new_style_scores_dict.get('Value'), new_style_scores_dict.get('Growth'), new_style_scores_dict.get('Momentum'), new_style_scores_dict.get('VGM'), current_price, return_pct, "Criteria no longer met by profile rules.")
                    cursor.execute("INSERT INTO trade_logs (profile_id, ticker, company_name, entry_timestamp, entry_zacks_rank, entry_style_value, entry_style_growth, entry_style_momentum, entry_style_vgm, entry_price, exit_timestamp, exit_zacks_rank, exit_style_value, exit_style_growth, exit_style_momentum, exit_style_vgm, exit_price, return_percentage, reason_for_exit) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", trade_log_values)
                    cursor.execute("DELETE FROM stock_holdings WHERE holding_id=?", (holding_id,))
                    sold_count_profile += 1
        db_conn.commit()
        if updated_count_profile > 0 or sold_count_profile > 0 :
             print(f"  SCANNER: Profile {profile_id} re-check complete. Updated: {updated_count_profile}, Sold: {sold_count_profile}")
        print(f"=== SCANNER: Profile ID: {profile_id} ({profile_name}) processing complete. ===")

    db_conn.close()
    print("\n--- SCANNER: Scan for ALL ACTIVE PROFILES (with Price Fetching & New Logic) complete. ---")

if __name__ == "__main__":
    print("--- SCANNER MAIN: Test Run (Using New Profile Logic & Prices) ---")
    conn_main_test = get_db_connection()
    print("SCANNER MAIN: Ensuring database tables and predefined profiles exist via database_setup.py...")
    db_setup.create_tables(conn_main_test.cursor())
    conn_main_test.commit()
    # This call ensures the 7 profiles are there with their profile_type.
    # It also deactivates the old "Profile 1 - Strong Buy, Max 1 B Style" (ID 1).
    # And it updates descriptions of the 7 profiles if they differ.
    db_setup.add_predefined_profiles(conn_main_test, conn_main_test.cursor())

    # Remove any other profiles that might have been added by old test code for a cleaner test of the 7.
    # Specifically, old "Profile 2" (ID 2) and "Profile 2 ... (Structured)" (ID 3 from last run).
    cursor = conn_main_test.cursor()
    profiles_to_keep_names = [
        "The Cautious Investor", "The Hesitant Investor", "The Brave Investor",
        "The Reckless Investor", "The Greedy 2% Investor",
        "The Greedy 3% Investor", "The Greedy 4% Investor"
    ]
    # Create a placeholder string for the IN clause
    placeholders = ', '.join('?' for _ in profiles_to_keep_names)
    # Deactivate profiles NOT in this list
    cursor.execute(f"UPDATE investor_profiles SET is_active=0 WHERE name NOT IN ({placeholders})", profiles_to_keep_names)
    # Ensure the 7 predefined profiles ARE active
    cursor.execute(f"UPDATE investor_profiles SET is_active=1 WHERE name IN ({placeholders})", profiles_to_keep_names)

    # Clear any existing holdings and trade logs for a clean test run for the 7 profiles
    print("SCANNER MAIN: Clearing old stock_holdings and trade_logs for a clean test run...")
    cursor.execute("DELETE FROM stock_holdings")
    cursor.execute("DELETE FROM trade_logs")
    conn_main_test.commit()

    conn_main_test.close()
    print("SCANNER MAIN: Database setup confirmed with only 7 predefined active profiles. Holdings/logs cleared.")

    scan_and_update_all_active_profiles()

    print("\n--- SCANNER MAIN: Verifying Database Contents Post-Scan ---")
    final_conn = get_db_connection()
    print("\nActive Investor Profiles:")
    for row in final_conn.execute("SELECT profile_id, name, profile_type, is_active FROM investor_profiles WHERE is_active=1"): print(dict(row))
    print("\nStock Holdings:")
    for row in final_conn.execute("SELECT profile_id, ticker, company_name, entry_price, current_zacks_rank, current_style_vgm FROM stock_holdings"): print(dict(row))
    print("\nTrade Logs:")
    for row in final_conn.execute("SELECT profile_id, ticker, entry_price, exit_price, return_percentage, reason_for_exit FROM trade_logs"): print(dict(row))
    final_conn.close()
    print("\n--- SCANNER MAIN: Test Run Complete ---")
