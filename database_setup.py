import sqlite3

DB_NAME = 'investor_profiles.db'

def connect_db(db_name=DB_NAME):
    """Connects to the SQLite database and returns the connection and cursor."""
    conn = sqlite3.connect(db_name)
    # Enable foreign key support if not enabled by default (good practice for SQLite)
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()
    return conn, cursor

def create_tables(cursor):
    """Creates the database tables."""
    # Investor Profiles Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS investor_profiles (
        profile_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        description TEXT, -- Will store rules like "Zacks Rank: 1. Style Scores: Max 1 B."
        is_active INTEGER DEFAULT 1
    )
    ''')
    print("Table 'investor_profiles' created or already exists.")

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
        FOREIGN KEY (profile_id) REFERENCES investor_profiles (profile_id) ON DELETE CASCADE,
        UNIQUE (profile_id, ticker)
    )
    ''')
    print("Table 'stock_holdings' created or already exists.")

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
        return_percentage REAL,
        reason_for_exit TEXT,
        FOREIGN KEY (profile_id) REFERENCES investor_profiles (profile_id) ON DELETE CASCADE
    )
    ''')
    print("Table 'trade_logs' created or already exists.")

    # Profile Rules Table (New)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS profile_rules (
        rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
        profile_id INTEGER NOT NULL,
        category TEXT NOT NULL, -- e.g., 'ZACKS_RANK', 'STYLE_SCORE_VALUE', 'STYLE_SCORE_PATTERN'
        condition TEXT NOT NULL, -- e.g., 'IN_LIST', 'EQUALS', 'MATCHES_PATTERN', 'MIN_GRADE', 'MAX_B_COUNT'
        value1 TEXT,             -- e.g., '1,2' for ranks; 'A' for a style score; 'AAAB' for pattern; 'B' for max_b_count
        value2 TEXT,             -- Optional, for future use (e.g., ranges)
        FOREIGN KEY (profile_id) REFERENCES investor_profiles (profile_id) ON DELETE CASCADE
    )
    ''')
    print("Table 'profile_rules' created or already exists.")


def add_initial_profile(conn, cursor):
    """Adds an initial investor profile if it doesn't already exist."""
    profile_name = "Profile 1 - Strong Buy, Max 1 B Style"
    # Description is now more for human readability; rules will be in profile_rules
    description = "Zacks Rank: 1. Style Scores: Max 1 B (Value,Growth,Momentum,VGM)."

    cursor.execute("SELECT profile_id FROM investor_profiles WHERE name = ?", (profile_name,))
    existing_profile_row = cursor.fetchone()

    if existing_profile_row is None:
        cursor.execute('''
        INSERT INTO investor_profiles (name, description, is_active)
        VALUES (?, ?, ?)
        ''', (profile_name, description, 1))
        conn.commit() # Commit after insert
        print(f"Profile '{profile_name}' added with description: '{description}'")
        # Note: No structured rules are added to 'profile_rules' for this profile here.
        # That will be handled by the GUI or a separate migration step.
    else:
        # Optionally, update the description if it has changed, though it's less critical now
        profile_id = existing_profile_row[0]
        cursor.execute("SELECT description FROM investor_profiles WHERE profile_id = ?", (profile_id,))
        current_desc = cursor.fetchone()[0]
        if current_desc != description:
            cursor.execute("UPDATE investor_profiles SET description = ? WHERE profile_id = ?", (description, profile_id))
            conn.commit()
            print(f"Profile '{profile_name}' already exists. Description updated to: '{description}'")
        else:
            print(f"Profile '{profile_name}' already exists with the correct description.")

def main():
    """Main function to set up the database."""
    print(f"Setting up database '{DB_NAME}'...")
    conn, cursor = connect_db()

    create_tables(cursor)
    conn.commit() # Commit after all table creations.

    add_initial_profile(conn, cursor) # This function handles its own commit for the insert/update.

    conn.close()
    print("Database setup complete. 'profile_rules' table added/verified.")

if __name__ == "__main__":
    main()
