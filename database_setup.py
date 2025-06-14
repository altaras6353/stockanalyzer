import sqlite3

DB_NAME = 'investor_profiles.db'

def connect_db(db_name=DB_NAME):
    conn = sqlite3.connect(db_name)
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()
    return conn, cursor

def add_column_if_not_exists(cursor, table_name, column_name, column_type):
    """Adds a column to a table if it doesn't already exist."""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    if column_name not in columns:
        try:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
            print(f"Column '{column_name}' added to table '{table_name}'.")
        except sqlite3.OperationalError as e:
            # This might happen if trying to add a NOT NULL column without a DEFAULT to an existing table with data
            # Or other schema modification issues. For this project, simple ADD COLUMN should be fine.
            print(f"Warning: Could not add column '{column_name}' to '{table_name}': {e}. It might require a default value or manual migration if table has data.")
    else:
        print(f"Column '{column_name}' already exists in table '{table_name}'.")


def create_tables(cursor):
    """Creates or updates the database tables."""
    # Investor Profiles Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS investor_profiles (
        profile_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        description TEXT,
        is_active INTEGER DEFAULT 1,
        profile_type TEXT -- Added in Subtask 16
    )
    ''') # profile_type added here at creation if table is new
    add_column_if_not_exists(cursor, "investor_profiles", "profile_type", "TEXT")
    print("Table 'investor_profiles' schema checked/updated.")

    # Stock Holdings Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS stock_holdings (
        holding_id INTEGER PRIMARY KEY AUTOINCREMENT,
        profile_id INTEGER NOT NULL,
        ticker TEXT NOT NULL,
        company_name TEXT,
        entry_timestamp TEXT NOT NULL,
        entry_zacks_rank TEXT,
        entry_style_value TEXT,
        entry_style_growth TEXT,
        entry_style_momentum TEXT,
        entry_style_vgm TEXT,
        last_checked_timestamp TEXT,
        current_zacks_rank TEXT,
        current_style_value TEXT,
        current_style_growth TEXT,
        current_style_momentum TEXT,
        current_style_vgm TEXT,
        notes TEXT,
        entry_price REAL, -- Added in Subtask 16
        FOREIGN KEY (profile_id) REFERENCES investor_profiles (profile_id) ON DELETE CASCADE,
        UNIQUE (profile_id, ticker)
    )
    ''')
    add_column_if_not_exists(cursor, "stock_holdings", "entry_price", "REAL")
    print("Table 'stock_holdings' schema checked/updated.")

    # Trade Logs Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS trade_logs (
        trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
        profile_id INTEGER NOT NULL,
        ticker TEXT NOT NULL,
        company_name TEXT,
        entry_timestamp TEXT NOT NULL,
        entry_zacks_rank TEXT,
        entry_style_value TEXT,
        entry_style_growth TEXT,
        entry_style_momentum TEXT,
        entry_style_vgm TEXT,
        exit_timestamp TEXT NOT NULL,
        exit_zacks_rank TEXT,
        exit_style_value TEXT,
        exit_style_growth TEXT,
        exit_style_momentum TEXT,
        exit_style_vgm TEXT,
        return_percentage REAL, -- This is a placeholder, actual calculation needs prices
        reason_for_exit TEXT,
        entry_price REAL, -- Added in Subtask 16
        exit_price REAL,  -- Added in Subtask 16
        FOREIGN KEY (profile_id) REFERENCES investor_profiles (profile_id) ON DELETE CASCADE
    )
    ''')
    add_column_if_not_exists(cursor, "trade_logs", "entry_price", "REAL")
    add_column_if_not_exists(cursor, "trade_logs", "exit_price", "REAL")
    print("Table 'trade_logs' schema checked/updated.")

    # Profile Rules Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS profile_rules (
        rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
        profile_id INTEGER NOT NULL,
        category TEXT NOT NULL,
        condition TEXT NOT NULL,
        value1 TEXT,
        value2 TEXT,
        FOREIGN KEY (profile_id) REFERENCES investor_profiles (profile_id) ON DELETE CASCADE
    )
    ''')
    print("Table 'profile_rules' schema checked/updated.")


def add_predefined_profiles(conn, cursor):
    """Adds or updates 7 predefined investor profiles."""
    profiles_to_define = [
        {"name": "The Cautious Investor", "profile_type": "Cautious",
         "description": "Exits early to avoid risk. Prioritizes capital preservation. Buys Rank 1, Style Max 1B. Sells if Rank > 2 or Style > C.", "is_active": 1},
        {"name": "The Hesitant Investor", "profile_type": "Hesitant",
         "description": "Needs strong signals to invest. Buys Rank 1, Style All A. Sells if Rank > 1 or Style > B.", "is_active": 1},
        {"name": "The Brave Investor", "profile_type": "Brave",
         "description": "Comfortable with some risk for higher returns. Buys Rank 1 or 2, Style Max 1B. Sells if Rank > 3 or Style > C.", "is_active": 1},
        {"name": "The Reckless Investor", "profile_type": "Reckless",
         "description": "High risk, high reward. Buys Rank 1, 2 or 3, Style Max 1C (if rank is 1 or 2) or Max 1B (if rank 3). Sells if Rank > 4.", "is_active": 1},
        {"name": "The Greedy 2% Investor", "profile_type": "Greedy2Pct",
         "description": "Aims for quick 2% gains. (Note: Actual % gain not implemented, uses general buy/sell logic for now). Buys Rank 1, Style All A. Sells if Rank > 1 or Style > B.", "is_active": 1},
        {"name": "The Greedy 3% Investor", "profile_type": "Greedy3Pct",
         "description": "Aims for quick 3% gains. (Note: Actual % gain not implemented, uses general buy/sell logic for now). Buys Rank 1, Style All A. Sells if Rank > 1 or Style > B.", "is_active": 1},
        {"name": "The Greedy 4% Investor", "profile_type": "Greedy4Pct",
         "description": "Aims for quick 4% gains. (Note: Actual % gain not implemented, uses general buy/sell logic for now). Buys Rank 1, Style All A. Sells if Rank > 1 or Style > B.", "is_active": 1}
    ]

    # Deactivate old "Profile 1 - Strong Buy, Max 1 B Style" if it exists and is not one of the new names
    old_profile_name = "Profile 1 - Strong Buy, Max 1 B Style"
    is_old_profile_one_of_new = any(p['name'] == old_profile_name for p in profiles_to_define)

    if not is_old_profile_one_of_new:
        cursor.execute("SELECT profile_id FROM investor_profiles WHERE name = ?", (old_profile_name,))
        old_profile_row = cursor.fetchone()
        if old_profile_row:
            print(f"Deactivating old profile: '{old_profile_name}' (ID: {old_profile_row[0]}) as it's replaced by predefined set.")
            cursor.execute("UPDATE investor_profiles SET is_active = 0 WHERE profile_id = ?", (old_profile_row[0],))
            conn.commit() # Commit deactivation

    for profile_data in profiles_to_define:
        cursor.execute("SELECT profile_id FROM investor_profiles WHERE name = ?", (profile_data['name'],))
        existing_profile = cursor.fetchone()

        if existing_profile is None:
            cursor.execute('''
            INSERT INTO investor_profiles (name, profile_type, description, is_active)
            VALUES (?, ?, ?, ?)
            ''', (profile_data['name'], profile_data['profile_type'], profile_data['description'], profile_data['is_active']))
            profile_id = cursor.lastrowid
            print(f"Profile '{profile_data['name']}' added with type '{profile_data['profile_type']}'.")
            # Note: No structured rules are added here yet. That's for the GUI or next step.
        else:
            profile_id = existing_profile[0]
            # Update existing profile to match predefined values (especially description and type, and ensure active)
            cursor.execute('''
            UPDATE investor_profiles
            SET profile_type = ?, description = ?, is_active = ?
            WHERE profile_id = ?
            ''', (profile_data['profile_type'], profile_data['description'], profile_data['is_active'], profile_id))
            print(f"Profile '{profile_data['name']}' (ID: {profile_id}) updated to predefined values.")
    conn.commit()


def main():
    """Main function to set up the database."""
    print(f"Setting up database '{DB_NAME}' with schema updates and predefined profiles...")
    conn, cursor = connect_db()

    create_tables(cursor) # This now handles adding columns if they don't exist
    conn.commit()

    add_predefined_profiles(conn, cursor) # Adds/updates the 7 profiles

    conn.close()
    print("Database setup complete.")

if __name__ == "__main__":
    main()
