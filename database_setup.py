import sqlite3

DB_NAME = 'investor_profiles.db'

def connect_db(db_name=DB_NAME):
    conn = sqlite3.connect(db_name)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()
    return conn, cursor

def add_column_if_not_exists(cursor, table_name, column_name, column_type):
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row['name'] for row in cursor.fetchall()]
    if column_name not in columns:
        try:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
            print(f"Column '{column_name}' added to table '{table_name}'.")
        except sqlite3.OperationalError as e:
            print(f"Warning: Could not add column '{column_name}' to '{table_name}': {e}.")
    # else: # Less verbose
        # print(f"Column '{column_name}' already exists in table '{table_name}'.")

def create_tables(cursor):
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS investor_profiles (
        profile_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
        description TEXT, is_active INTEGER DEFAULT 1, profile_type TEXT )''')
    add_column_if_not_exists(cursor, "investor_profiles", "profile_type", "TEXT")
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS stock_holdings (
        holding_id INTEGER PRIMARY KEY AUTOINCREMENT, profile_id INTEGER NOT NULL,
        ticker TEXT NOT NULL, company_name TEXT, entry_timestamp TEXT NOT NULL,
        entry_zacks_rank TEXT, entry_style_value TEXT, entry_style_growth TEXT,
        entry_style_momentum TEXT, entry_style_vgm TEXT, last_checked_timestamp TEXT,
        current_zacks_rank TEXT, current_style_value TEXT, current_style_growth TEXT,
        current_style_momentum TEXT, current_style_vgm TEXT, notes TEXT, entry_price REAL,
        FOREIGN KEY (profile_id) REFERENCES investor_profiles (profile_id) ON DELETE CASCADE,
        UNIQUE (profile_id, ticker))''')
    add_column_if_not_exists(cursor, "stock_holdings", "entry_price", "REAL")
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS trade_logs (
        trade_id INTEGER PRIMARY KEY AUTOINCREMENT, profile_id INTEGER NOT NULL,
        ticker TEXT NOT NULL, company_name TEXT, entry_timestamp TEXT NOT NULL,
        entry_zacks_rank TEXT, entry_style_value TEXT, entry_style_growth TEXT,
        entry_style_momentum TEXT, entry_style_vgm TEXT, exit_timestamp TEXT NOT NULL,
        exit_zacks_rank TEXT, exit_style_value TEXT, exit_style_growth TEXT,
        exit_style_momentum TEXT, exit_style_vgm TEXT, return_percentage REAL,
        reason_for_exit TEXT, entry_price REAL, exit_price REAL,
        FOREIGN KEY (profile_id) REFERENCES investor_profiles (profile_id) ON DELETE CASCADE)''')
    add_column_if_not_exists(cursor, "trade_logs", "entry_price", "REAL")
    add_column_if_not_exists(cursor, "trade_logs", "exit_price", "REAL")
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS profile_rules (
        rule_id INTEGER PRIMARY KEY AUTOINCREMENT, profile_id INTEGER NOT NULL,
        category TEXT NOT NULL, condition TEXT NOT NULL, value1 TEXT, value2 TEXT,
        FOREIGN KEY (profile_id) REFERENCES investor_profiles (profile_id) ON DELETE CASCADE)''')
    print("All table schemas checked/updated.")

# Updated descriptions for the 7 predefined profiles
profiles_to_define_list = [
    {"name": "The Cautious Investor", "profile_type": "Cautious",
     "description": "Exits if Zacks Rank is no longer '1' OR Calculated Score > 4 OR Score is invalid. Standard entry.", "is_active": 1},
    {"name": "The Hesitant Investor", "profile_type": "Hesitant",
     "description": "Exits if Zacks Rank is no longer '1' OR Calculated Score > 5 OR Score is invalid. Standard entry.", "is_active": 1},
    {"name": "The Brave Investor", "profile_type": "Brave",
     "description": "Exits if Zacks Rank is no longer '1' OR Calculated Score > 6 OR Score is invalid. Standard entry.", "is_active": 1},
    {"name": "The Reckless Investor", "profile_type": "Reckless",
     "description": "Exits if Zacks Rank is no longer '1' OR Calculated Score > 7 OR Score is invalid. Standard entry.", "is_active": 1},
    {"name": "The Greedy 2% Investor", "profile_type": "Greedy2Pct",
     "description": "Exits if (Zacks Rank is no longer '1' OR Calculated Score > 4 OR Score is invalid) OR Profit >= 2%. Standard entry.", "is_active": 1},
    {"name": "The Greedy 3% Investor", "profile_type": "Greedy3Pct",
     "description": "Exits if (Zacks Rank is no longer '1' OR Calculated Score > 4 OR Score is invalid) OR Profit >= 3%. Standard entry.", "is_active": 1},
    {"name": "The Greedy 4% Investor", "profile_type": "Greedy4Pct",
     "description": "Exits if (Zacks Rank is no longer '1' OR Calculated Score > 5 OR Score is invalid) OR Profit >= 4%. Standard entry.", "is_active": 1}
]

def add_predefined_profiles(conn, cursor):
    old_profile_name = "Profile 1 - Strong Buy, Max 1 B Style"
    is_old_profile_one_of_new = any(p['name'] == old_profile_name for p in profiles_to_define_list)

    if not is_old_profile_one_of_new:
        cursor.execute("SELECT profile_id FROM investor_profiles WHERE name = ?", (old_profile_name,))
        old_profile_row = cursor.fetchone()
        if old_profile_row:
            print(f"Deactivating old profile: '{old_profile_name}' (ID: {old_profile_row['profile_id']})")
            cursor.execute("UPDATE investor_profiles SET is_active = 0 WHERE profile_id = ?", (old_profile_row['profile_id'],))
            # No commit here, will be done after all profile operations

    for profile_data in profiles_to_define_list:
        cursor.execute("SELECT profile_id, description, profile_type, is_active FROM investor_profiles WHERE name = ?", (profile_data['name'],))
        existing_profile = cursor.fetchone()

        if existing_profile is None:
            cursor.execute("INSERT INTO investor_profiles (name, profile_type, description, is_active) VALUES (?, ?, ?, ?)",
                           (profile_data['name'], profile_data['profile_type'], profile_data['description'], profile_data['is_active']))
            print(f"Profile '{profile_data['name']}' added.")
        else: # Profile exists, check if update needed
            profile_id = existing_profile['profile_id']
            if (existing_profile['description'] != profile_data['description'] or
                existing_profile['profile_type'] != profile_data['profile_type'] or
                existing_profile['is_active'] != profile_data['is_active']):
                cursor.execute("UPDATE investor_profiles SET profile_type = ?, description = ?, is_active = ? WHERE profile_id = ?",
                               (profile_data['profile_type'], profile_data['description'], profile_data['is_active'], profile_id))
                print(f"Profile '{profile_data['name']}' (ID: {profile_id}) updated.")
    conn.commit() # Commit all profile changes together
    print(f"{len(profiles_to_define_list)} predefined profiles checked/updated.")

def main():
    print(f"Setting up database '{DB_NAME}'...")
    conn, cursor = connect_db()
    create_tables(cursor); conn.commit()
    add_predefined_profiles(conn, cursor)
    conn.close()
    print("Database setup complete.")

if __name__ == "__main__":
    main()
