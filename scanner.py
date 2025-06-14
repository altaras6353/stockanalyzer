import sqlite3
import datetime
import requests

from profile_logic import check_buy_conditions, check_sell_conditions
import database_setup as db_setup
# Dynamic imports for parse_main_page, parse_stock_page in scan_and_update_all_active_profiles

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

# Module-level global variable to store results of the last raw scan
last_raw_scan_results = []

def get_db_connection(db_name=db_setup.DB_NAME):
    conn = sqlite3.connect(db_name)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def scan_and_update_all_active_profiles():
    global last_raw_scan_results # To update the global list
    print(f"\n--- Starting scan for ALL ACTIVE PROFILES (using structured DB rules) ---")

    # Moved dynamic imports to the top of the function for clarity if they are always needed
    from parse_main_page import extract_top_vgm_stocks
    from parse_stock_page import extract_stock_ratings

    db_conn = get_db_connection()
    cursor = db_conn.cursor()
    now_iso_timestamp = datetime.datetime.now().isoformat()

    cursor.execute("SELECT profile_id, name FROM investor_profiles WHERE is_active=1")
    active_profiles = cursor.fetchall()

    if not active_profiles:
        print("No active profiles found to scan."); db_conn.close(); return
    print(f"Found {len(active_profiles)} active profile(s) to process.")

    main_page_html_content = None
    try:
        response = requests.get('https://www.zacks.com/', headers=HEADERS, timeout=10)
        response.raise_for_status(); main_page_html_content = response.text
        print("Successfully fetched main page live.")
    except Exception as e:
        print(f"Failed to fetch main page live: {e}. Falling back to local main_page.html.")
        try:
            with open("main_page.html", "r", encoding="utf-8") as f: main_page_html_content = f.read()
            print("Loaded main page from local main_page.html.")
        except FileNotFoundError:
            print("CRITICAL Error: main_page.html not found for fallback."); db_conn.close(); return

    candidate_stocks_summary = extract_top_vgm_stocks(main_page_html_content) # List of dicts with Name, Ticker, URL
    print(f"Found {len(candidate_stocks_summary)} candidate summaries from main page.")

    # --- Pre-fetch details for all candidates ---
    detailed_candidate_stocks = []
    print(f"\n--- Pre-fetching details for {len(candidate_stocks_summary)} candidates ---")
    for candidate_summary in candidate_stocks_summary:
        ticker = candidate_summary.get('Ticker Symbol')
        company_name = candidate_summary.get('Company Name')
        url = candidate_summary.get('Stock Page URL')

        if not ticker or not url:
            print(f"Skipping candidate due to missing ticker or URL: {candidate_summary}")
            continue

        print(f"  Fetching details for {ticker}...")
        individual_page_html_content = None
        try:
            response_stock = requests.get(url, headers=HEADERS, timeout=10)
            response_stock.raise_for_status()
            individual_page_html_content = response_stock.text
            # print(f"    Successfully fetched page for {ticker} live.")
        except Exception as e_stock:
            print(f"    Failed live fetch for {ticker}: {e_stock}. Using fallback HTML.")
            try:
                with open("individual_stock_page.html", "r", encoding="utf-8") as f:
                    individual_page_html_content = f.read()
                # print(f"    Loaded ratings for {ticker} from local individual_stock_page.html (fallback).")
            except FileNotFoundError:
                print(f"    CRITICAL: Fallback HTML (individual_stock_page.html) not found for {ticker}. Skipping candidate.")
                continue # Skip this candidate if no HTML can be obtained

        ratings_data = extract_stock_ratings(individual_page_html_content)

        detailed_candidate = {
            'Company Name': company_name,
            'Ticker Symbol': ticker,
            'Stock Page URL': url,
            'Zacks Rank': ratings_data.get('Zacks Rank'),
            'Value Score': ratings_data.get('Value'),
            'Growth Score': ratings_data.get('Growth'),
            'Momentum Score': ratings_data.get('Momentum'),
            'VGM Score': ratings_data.get('VGM')
        }
        detailed_candidate_stocks.append(detailed_candidate)
        # print(f"    Details for {ticker}: Rank={detailed_candidate['Zacks Rank']}, V={detailed_candidate['Value Score']}")

    last_raw_scan_results = detailed_candidate_stocks # Update global variable
    print(f"--- Pre-fetching complete. {len(last_raw_scan_results)} candidates have detailed data. ---")
    if not last_raw_scan_results:
        print("No detailed candidate data to process for profiles.")


    # --- Loop through each active profile using pre-fetched detailed_candidate_stocks ---
    for profile_row in active_profiles:
        profile_id = profile_row['profile_id']
        profile_name = profile_row['name']

        print(f"\n=== Processing Profile ID: {profile_id} ({profile_name}) using pre-fetched DB rules & candidate details ===")

        new_buys_count = 0
        # Now iterate over detailed_candidate_stocks
        for detailed_candidate in last_raw_scan_results:
            ticker = detailed_candidate['Ticker Symbol'] # Already fetched
            company_name = detailed_candidate['Company Name']
            # url = detailed_candidate['Stock Page URL'] # Not needed for re-fetch here

            # print(f"\n  Considering candidate for Profile {profile_id}: {ticker}")
            current_zacks_rank_str = detailed_candidate['Zacks Rank']
            current_style_scores_dict = {
                'Value': detailed_candidate['Value Score'],
                'Growth': detailed_candidate['Growth Score'],
                'Momentum': detailed_candidate['Momentum Score'],
                'VGM': detailed_candidate['VGM Score']
            }

            if check_buy_conditions(db_conn, profile_id, current_zacks_rank_str, current_style_scores_dict):
                print(f"  BUY condition MET for {ticker} for Profile {profile_id}.")
                cursor.execute("SELECT holding_id FROM stock_holdings WHERE profile_id=? AND ticker=?", (profile_id, ticker))
                if cursor.fetchone() is None:
                    print(f"    Adding {ticker} to holdings for Profile {profile_id}...")
                    entry_values = (profile_id, ticker, company_name, now_iso_timestamp, current_zacks_rank_str,
                                    current_style_scores_dict.get('Value'), current_style_scores_dict.get('Growth'),
                                    current_style_scores_dict.get('Momentum'), current_style_scores_dict.get('VGM'),
                                    now_iso_timestamp, current_zacks_rank_str, current_style_scores_dict.get('Value'),
                                    current_style_scores_dict.get('Growth'), current_style_scores_dict.get('Momentum'),
                                    current_style_scores_dict.get('VGM'), f"Initial scan buy for profile {profile_id}")
                    cursor.execute("INSERT INTO stock_holdings (profile_id, ticker, company_name, entry_timestamp, entry_zacks_rank, entry_style_value, entry_style_growth, entry_style_momentum, entry_style_vgm, last_checked_timestamp, current_zacks_rank, current_style_value, current_style_growth, current_style_momentum, current_style_vgm, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", entry_values)
                    new_buys_count += 1
        db_conn.commit()

        # --- Re-checking tracked stocks (logic remains largely the same, uses live data for re-check) ---
        print(f"\n  --- Re-checking tracked stocks for Profile ID: {profile_id} ---")
        cursor.execute("SELECT holding_id, ticker, company_name, entry_timestamp, entry_zacks_rank, entry_style_value, entry_style_growth, entry_style_momentum, entry_style_vgm FROM stock_holdings WHERE profile_id=?", (profile_id,))
        tracked_stocks_for_profile = cursor.fetchall()

        sold_count_profile = 0; updated_count_profile = 0
        for stock_row in tracked_stocks_for_profile:
            holding_id, ticker, company_name, entry_ts, ezr, esv, esg, esm, esvgm = stock_row
            stock_page_url = f"https://www.zacks.com/stock/quote/{ticker}" # URL for re-fetch
            individual_page_html_content_recheck = None
            try: # Re-fetch live data for currently held stocks
                response_recheck = requests.get(stock_page_url, headers=HEADERS, timeout=10); response_recheck.raise_for_status()
                individual_page_html_content_recheck = response_recheck.text
            except Exception as e_recheck:
                print(f"    Failed live fetch for re-checking {ticker}: {e_recheck}. Using fallback HTML.")
                try:
                    with open("individual_stock_page.html", "r", encoding="utf-8") as f: individual_page_html_content_recheck = f.read()
                except FileNotFoundError: print(f"      CRITICAL: Fallback HTML not found for {ticker} re-check. Skipping."); continue

            ratings_data_recheck = extract_stock_ratings(individual_page_html_content_recheck)
            new_zacks_rank_str = ratings_data_recheck.get('Zacks Rank')
            new_style_scores_dict = {k: ratings_data_recheck.get(k) for k in ['Value', 'Growth', 'Momentum', 'VGM']}

            update_values = (now_iso_timestamp, new_zacks_rank_str, new_style_scores_dict.get('Value'), new_style_scores_dict.get('Growth'), new_style_scores_dict.get('Momentum'), new_style_scores_dict.get('VGM'), f"Re-checked at {now_iso_timestamp}", holding_id)
            cursor.execute("UPDATE stock_holdings SET last_checked_timestamp=?, current_zacks_rank=?, current_style_value=?, current_style_growth=?, current_style_momentum=?, current_style_vgm=?, notes=? WHERE holding_id=?", update_values)
            updated_count_profile +=1

            if check_sell_conditions(db_conn, profile_id, new_zacks_rank_str, new_style_scores_dict):
                print(f"    SELL condition MET for {ticker} for Profile {profile_id}. Logging and removing.")
                trade_log_values = (profile_id, ticker, company_name, entry_ts, ezr, esv, esg, esm, esvgm, now_iso_timestamp, new_zacks_rank_str, new_style_scores_dict.get('Value'), new_style_scores_dict.get('Growth'), new_style_scores_dict.get('Momentum'), new_style_scores_dict.get('VGM'), 0.0, "Criteria no longer met by profile rules.")
                cursor.execute("INSERT INTO trade_logs (profile_id, ticker, company_name, entry_timestamp, entry_zacks_rank, entry_style_value, entry_style_growth, entry_style_momentum, entry_style_vgm, exit_timestamp, exit_zacks_rank, exit_style_value, exit_style_growth, exit_style_momentum, exit_style_vgm, return_percentage, reason_for_exit) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", trade_log_values)
                cursor.execute("DELETE FROM stock_holdings WHERE holding_id=?", (holding_id,))
                sold_count_profile += 1
        db_conn.commit()
        print(f"  Profile {profile_id} re-check complete. Updated: {updated_count_profile}, Sold: {sold_count_profile}")
        print(f"=== Profile ID: {profile_id} ({profile_name}) processing complete. ===")

    db_conn.close()
    print("\n--- Scan for ALL ACTIVE PROFILES (using structured DB rules & pre-fetched candidates) complete. ---")

if __name__ == "__main__":
    print("--- Running Scanner Test (Pre-fetching Candidate Details) ---")
    conn = get_db_connection()
    cursor = conn.cursor()
    print("Ensuring database tables and initial profile exist via database_setup.py...")
    db_setup.create_tables(cursor); conn.commit()
    db_setup.add_initial_profile(conn, cursor)
    profile_1_id = 1
    print(f"Updating/Ensuring structured rules for Profile ID {profile_1_id}...")
    cursor.execute("DELETE FROM profile_rules WHERE profile_id = ?", (profile_1_id,))
    cursor.execute("INSERT INTO profile_rules (profile_id, category, condition, value1) VALUES (?, 'ZACKS_RANK', 'IN_LIST', '1')", (profile_1_id,))
    cursor.execute("INSERT INTO profile_rules (profile_id, category, condition, value1) VALUES (?, 'STYLE_SCORE_PATTERN', 'MATCHES_PATTERN', 'AAAB')", (profile_1_id,))
    conn.commit(); print(f"Structured rules for Profile ID {profile_1_id} set.")
    profile2_name = "Profile 2 - Rank 1or2, All A (Structured Test)" # Slightly different name for clarity
    profile2_desc_text = "Zacks Rank: 1 or 2. Style Scores: All A."
    cursor.execute("DELETE FROM investor_profiles WHERE name = ?", (profile2_name,)) # Ensure clean insert for this test name
    conn.commit() # Commit delete before trying to re-add or select
    cursor.execute("INSERT INTO investor_profiles (name, description, is_active) VALUES (?, ?, ?)", (profile2_name, profile2_desc_text, 1))
    profile_2_id_to_use = cursor.lastrowid
    print(f"Added '{profile2_name}' with auto-incremented ID {profile_2_id_to_use}.")
    cursor.execute("DELETE FROM profile_rules WHERE profile_id = ?", (profile_2_id_to_use,))
    cursor.execute("INSERT INTO profile_rules (profile_id, category, condition, value1) VALUES (?, 'ZACKS_RANK', 'IN_LIST', '1,2')", (profile_2_id_to_use,))
    cursor.execute("INSERT INTO profile_rules (profile_id, category, condition, value1) VALUES (?, 'STYLE_SCORE_PATTERN', 'MATCHES_PATTERN', 'AAAA')", (profile_2_id_to_use,))
    print(f"Structured rules for Profile ID {profile_2_id_to_use} set.")
    conn.commit(); conn.close()

    scan_and_update_all_active_profiles()

    print("\n--- Verifying Last Raw Scan Results (from scanner.py global) ---")
    if last_raw_scan_results:
        print(f"Total raw candidates scanned: {len(last_raw_scan_results)}")
        for i, item in enumerate(last_raw_scan_results[:2]): # Print first 2 for brevity
            print(f"  Raw item {i}: Ticker={item.get('Ticker Symbol')}, Rank={item.get('Zacks Rank')}, V={item.get('Value Score')}")
    else:
        print("  No raw scan results were stored.")

    print("\n--- Verifying Database Contents Post-Scan ---")
    final_conn = get_db_connection()
    # ... (DB verification prints as before) ...
    print("\nInvestor Profiles:")
    for row in final_conn.execute("SELECT profile_id, name, is_active FROM investor_profiles"): print(dict(row))
    print("\nStock Holdings:")
    for row in final_conn.execute("SELECT profile_id, ticker, company_name FROM stock_holdings"): print(dict(row))
    final_conn.close()
    print("\n--- Scanner Test with Pre-fetching Complete ---")
