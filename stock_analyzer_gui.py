import tkinter as tk
from tkinter import ttk
from tkinter import simpledialog, messagebox
import datetime
import threading
import time
import sqlite3

import scanner
from database_setup import connect_db, create_tables, add_initial_profile, DB_NAME

# --- Global Variables ---
root_window = None
# For "Selected Profile View" tab
holdings_tree = None
tradelog_tree = None
total_return_label_var = None
total_trades_label_var = None
# For Profile Management
profiles_listbox = None
selected_profile_id = None
profile_id_map = {}
# For "Profile Comparison" tab
comparison_tree = None
# For Notebook
notebook = None

scanner_active = True

# --- Profile Management Functions ---
def load_profiles_into_listbox():
    global profiles_listbox, profile_id_map
    if not profiles_listbox: return
    print("GUI: Loading profiles into listbox...")
    profiles_listbox.delete(0, tk.END); profile_id_map.clear()
    conn, cursor = None, None
    try:
        conn, cursor = connect_db()
        cursor.execute("SELECT profile_id, name, is_active FROM investor_profiles ORDER BY name ASC")
        for index, (pid, name, is_active_val) in enumerate(cursor.fetchall()):
            profiles_listbox.insert(tk.END, f"{name} {'(Active)' if is_active_val else '(Inactive)'}")
            profile_id_map[index] = pid
        print(f"GUI: Loaded {len(profile_id_map)} profiles.")
        # After profile list changes, update comparison view as well
        if root_window: root_window.after(0, populate_profile_comparison_view)
    except Exception as e: messagebox.showerror("DB Error", f"Failed to load profiles: {e}")
    finally:
        if conn: conn.close()

def on_profile_select(event):
    global selected_profile_id, profiles_listbox, profile_id_map
    if not profiles_listbox or not profiles_listbox.curselection():
        selected_profile_id = None; print("GUI: No profile selected via event.")
        refresh_selected_profile_data_display(); return
    selected_profile_id = profile_id_map.get(profiles_listbox.curselection()[0])
    print(f"GUI: Profile selected via event. ID: {selected_profile_id}")
    refresh_selected_profile_data_display()

def get_profile_data_from_db(profile_id_to_fetch): # Renamed for clarity
    if profile_id_to_fetch is None: return None
    conn, cursor = None, None
    try:
        conn, cursor = connect_db()
        cursor.execute("SELECT profile_id, name, description, is_active FROM investor_profiles WHERE profile_id = ?", (profile_id_to_fetch,))
        return cursor.fetchone()
    except Exception as e: messagebox.showerror("DB Error", f"Failed to fetch profile data: {e}"); return None
    finally:
        if conn: conn.close()

def open_profile_editor_window(profile_id_to_edit=None):
    global root_window
    existing_data = get_profile_data_from_db(profile_id_to_edit) if profile_id_to_edit else None
    if profile_id_to_edit and not existing_data: messagebox.showerror("Error", "Could not load profile data."); return

    editor_win = tk.Toplevel(root_window); editor_win.title("Edit Profile" if existing_data else "Add New Profile")
    editor_win.geometry("500x400"); editor_win.transient(root_window); editor_win.grab_set()
    # ... (Editor window layout as before) ...
    ttk.Label(editor_win, text="Profile Name:").pack(pady=(10,0))
    name_var = tk.StringVar(value=existing_data[1] if existing_data else "")
    name_entry = ttk.Entry(editor_win, textvariable=name_var, width=60); name_entry.pack(pady=5, padx=10, fill=tk.X)
    ttk.Label(editor_win, text="Description (e.g., Zacks Rank: 1. Style Scores: Max 1 B.):").pack(pady=(10,0))
    desc_text = tk.Text(editor_win, height=10, width=60, wrap=tk.WORD); desc_text.pack(pady=5, padx=10, expand=True, fill=tk.BOTH)
    if existing_data and existing_data[2]: desc_text.insert(tk.END, existing_data[2])
    is_active_var = tk.BooleanVar(value=bool(existing_data[3]) if existing_data else True)
    ttk.Checkbutton(editor_win, text="Is Active", variable=is_active_var).pack(pady=5)
    def save_profile():
        name = name_var.get().strip(); description = desc_text.get("1.0", tk.END).strip(); is_active = 1 if is_active_var.get() else 0
        if not name: messagebox.showerror("Validation Error", "Profile Name cannot be empty.", parent=editor_win); return
        conn, cursor = None, None
        try:
            conn, cursor = connect_db()
            if profile_id_to_edit is None: cursor.execute("INSERT INTO investor_profiles (name, description, is_active) VALUES (?, ?, ?)", (name, description, is_active))
            else: cursor.execute("UPDATE investor_profiles SET name=?, description=?, is_active=? WHERE profile_id=?", (name, description, is_active, profile_id_to_edit))
            conn.commit(); messagebox.showinfo("Success", "Profile saved.", parent=editor_win)
            load_profiles_into_listbox(); editor_win.destroy() # load_profiles will also update comparison view
        except sqlite3.IntegrityError: messagebox.showerror("DB Error", f"Profile name '{name}' already exists.", parent=editor_win)
        except Exception as e: messagebox.showerror("DB Error", f"Failed to save profile: {e}", parent=editor_win)
        finally:
            if conn: conn.close()
    btn_frame = ttk.Frame(editor_win); btn_frame.pack(pady=10, fill=tk.X, side=tk.BOTTOM)
    ttk.Button(btn_frame, text="Save", command=save_profile).pack(side=tk.RIGHT, padx=10)
    ttk.Button(btn_frame, text="Cancel", command=editor_win.destroy).pack(side=tk.RIGHT)
    name_entry.focus_set()

def delete_selected_profile():
    global selected_profile_id
    if selected_profile_id is None: messagebox.showwarning("Selection Error", "No profile selected."); return
    profile_data = get_profile_data_from_db(selected_profile_id)
    if not profile_data or not messagebox.askyesno("Confirm Delete", f"Delete profile '{profile_data[1]}'?\nThis will also delete associated holdings and trade logs."): return
    conn, cursor = None, None
    try:
        conn, cursor = connect_db()
        cursor.execute("DELETE FROM stock_holdings WHERE profile_id = ?", (selected_profile_id,))
        cursor.execute("DELETE FROM trade_logs WHERE profile_id = ?", (selected_profile_id,))
        cursor.execute("DELETE FROM investor_profiles WHERE profile_id = ?", (selected_profile_id,))
        conn.commit(); messagebox.showinfo("Success", f"Profile '{profile_data[1]}' and its data deleted.")
        load_profiles_into_listbox(); selected_profile_id = None; refresh_selected_profile_data_display() # load_profiles also updates comparison
    except Exception as e: messagebox.showerror("DB Error", f"Failed to delete profile: {e}")
    finally:
        if conn: conn.close()

# --- Refresh Data Display Functions ---
def refresh_selected_profile_data_display(): # Renamed from refresh_profile_data_display
    global holdings_tree, tradelog_tree, total_return_label_var, total_trades_label_var, selected_profile_id, root_window
    print(f"GUI: Refreshing data display for Selected Profile ID: {selected_profile_id}")
    current_profile_name = "None Selected"
    if selected_profile_id:
        temp_profile_data = get_profile_data_from_db(selected_profile_id)
        if temp_profile_data: current_profile_name = temp_profile_data[1]
    if root_window: root_window.title(f"Zacks Stock Analyzer - Profile: {current_profile_name}")

    if not holdings_tree or not tradelog_tree: print("GUI Error: Treeviews not ready for refresh."); return
    for i in holdings_tree.get_children(): holdings_tree.delete(i)
    for i in tradelog_tree.get_children(): tradelog_tree.delete(i)
    if total_trades_label_var: total_trades_label_var.set("Total Trades: N/A")
    if total_return_label_var: total_return_label_var.set("Sum of Return % (Placeholder): N/A")

    if selected_profile_id is None: print("GUI: No profile selected, displays cleared."); return
    conn, cursor = None, None
    try:
        conn, cursor = connect_db()
        h_query = "SELECT ticker, company_name, entry_timestamp, entry_zacks_rank, entry_style_value, entry_style_growth, entry_style_momentum, entry_style_vgm, last_checked_timestamp, current_zacks_rank, current_style_value, current_style_growth, current_style_momentum, current_style_vgm FROM stock_holdings WHERE profile_id=? ORDER BY entry_timestamp DESC"
        cursor.execute(h_query, (selected_profile_id,));
        for row in cursor.fetchall(): holdings_tree.insert('', tk.END, values=row)
        tl_query = "SELECT ticker, company_name, entry_timestamp, exit_timestamp, entry_zacks_rank, exit_zacks_rank, entry_style_vgm, exit_style_vgm, return_percentage, reason_for_exit FROM trade_logs WHERE profile_id=? ORDER BY exit_timestamp DESC"
        cursor.execute(tl_query, (selected_profile_id,));
        for row in cursor.fetchall(): tradelog_tree.insert('', tk.END, values=row)
        cursor.execute("SELECT COUNT(*), SUM(return_percentage) FROM trade_logs WHERE profile_id=?", (selected_profile_id,))
        stats = cursor.fetchone()
        total_trades = stats[0] if stats and stats[0] is not None else 0
        total_return = stats[1] if stats and stats[1] is not None else 0.0
        if total_trades_label_var: total_trades_label_var.set(f"Total Trades: {total_trades}")
        if total_return_label_var: total_return_label_var.set(f"Sum of Return % (Placeholder): {total_return:.2f}%")
    except Exception as e: print(f"GUI Error: DB error during refresh: {e}"); messagebox.showerror("DB Error", f"Failed to refresh profile data: {e}")
    finally:
        if conn: conn.close()

def populate_profile_comparison_view():
    global comparison_tree
    if not comparison_tree: print("GUI Error: Comparison Treeview not initialized."); return
    print("GUI: Populating profile comparison view...")
    for i in comparison_tree.get_children(): comparison_tree.delete(i)
    conn, cursor = None, None
    try:
        conn, cursor = connect_db()
        cursor.execute("SELECT profile_id, name FROM investor_profiles ORDER BY name ASC")
        profiles = cursor.fetchall()
        for pid, name in profiles:
            cursor.execute("SELECT COUNT(*), SUM(return_percentage) FROM trade_logs WHERE profile_id=?", (pid,))
            stats = cursor.fetchone()
            total_trades = stats[0] if stats and stats[0] is not None else 0
            total_return = stats[1] if stats and stats[1] is not None else 0.0
            # "Winning Trades", "Losing Trades" are N/A
            comparison_tree.insert('', tk.END, values=(name, total_trades, "N/A", "N/A", f"{total_return:.2f}%"))
        print(f"GUI: Comparison view populated with {len(profiles)} profiles.")
    except Exception as e: print(f"GUI Error: DB error during comparison populate: {e}"); messagebox.showerror("DB Error", f"Failed to populate comparison: {e}")
    finally:
        if conn: conn.close()

def refresh_all_gui_data(): # New function to refresh both selected profile and comparison
    print("GUI: Refreshing all GUI data (selected profile and comparison)...")
    refresh_selected_profile_data_display()
    populate_profile_comparison_view()

# --- Manual Scan & Background Scanner (Calls generalized scanner) ---
def trigger_manual_scan_all_active():
    print("GUI: Manual scan for ALL ACTIVE profiles triggered...")
    def scan_task_all_active():
        try:
            scanner.scan_and_update_all_active_profiles()
            if root_window: root_window.after(0, refresh_all_gui_data)
        except Exception as e:
            if root_window: root_window.after(0, lambda: messagebox.showerror("Scan Error", f"Error - all active profiles scan: {e}"))
    threading.Thread(target=scan_task_all_active, daemon=True).start()
    messagebox.showinfo("Scan Started", "Manual scan for ALL active profiles initiated. Display will refresh on completion.")

def hourly_scan_worker():
    global scanner_active, root_window
    try:
        conn_init, cursor_init = connect_db(); create_tables(cursor_init); conn_init.commit(); add_initial_profile(conn_init, cursor_init); conn_init.close()
    except Exception as e: print(f"BG Scanner: DB setup error: {e}. Thread stopping."); return
    print("BG Scanner: Thread started (scans ALL active profiles).")
    while scanner_active:
        try:
            scanner.scan_and_update_all_active_profiles()
            if root_window and scanner_active: root_window.after(0, refresh_all_gui_data)
        except Exception as e: print(f"[{datetime.datetime.now()}] BG Scanner: Error (ALL active): {e}")
        sleep_duration = 15 # TEST
        print(f"[{datetime.datetime.now()}] BG Scanner: Next scan (ALL active) in {sleep_duration}s.")
        for i in range(max(1, sleep_duration // 5)):
            if not scanner_active: break
            time.sleep(min(5, sleep_duration - (i * 5)))
    print("BG Scanner: Thread stopped.")

# --- GUI Closing Handler & Main Window Creation ---
def on_closing():
    global scanner_active, root_window; print("GUI: Closing application..."); scanner_active = False
    if root_window: root_window.destroy()

def create_main_window():
    global root_window, holdings_tree, tradelog_tree, profiles_listbox, notebook, comparison_tree
    global total_return_label_var, total_trades_label_var
    root = tk.Tk(); root_window = root
    root.title("Zacks Stock Analyzer"); root.geometry("1300x900"); root.protocol("WM_DELETE_WINDOW", on_closing)

    # --- Top Controls (Profile Management & Global Actions) ---
    top_controls_frame = ttk.Frame(root, padding="5")
    top_controls_frame.pack(side=tk.TOP, fill=tk.X, pady=(5,0))

    # Profile Management (Left side of top_controls_frame)
    profiles_frame_cont = ttk.LabelFrame(top_controls_frame, text="Investor Profiles", padding="10")
    profiles_frame_cont.pack(side=tk.LEFT, padx=5, expand=False, fill=tk.Y) # Don't expand this frame, fixed width

    prof_list_sb_frame = ttk.Frame(profiles_frame_cont)
    prof_list_sb_frame.pack(pady=5, expand=True, fill=tk.BOTH)
    profiles_listbox = tk.Listbox(prof_list_sb_frame, exportselection=False, height=10, width=35) # Set width
    prof_list_sb = ttk.Scrollbar(prof_list_sb_frame, orient=tk.VERTICAL, command=profiles_listbox.yview)
    profiles_listbox.configure(yscrollcommand=prof_list_sb.set)
    profiles_listbox.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)
    prof_list_sb.pack(side=tk.RIGHT, fill=tk.Y)
    profiles_listbox.bind("<<ListboxSelect>>", on_profile_select)

    prof_btn_frm = ttk.Frame(profiles_frame_cont); prof_btn_frm.pack(fill=tk.X, pady=5, side=tk.BOTTOM)
    ttk.Button(prof_btn_frm, text="Add", command=lambda: open_profile_editor_window()).pack(side=tk.LEFT, expand=True, fill=tk.X)
    ttk.Button(prof_btn_frm, text="Edit", command=lambda: open_profile_editor_window(selected_profile_id) if selected_profile_id is not None else messagebox.showinfo("Info","Select profile to edit.")).pack(side=tk.LEFT, expand=True, fill=tk.X)
    ttk.Button(prof_btn_frm, text="Del", command=delete_selected_profile).pack(side=tk.LEFT, expand=True, fill=tk.X)

    # Global Actions (Right side of top_controls_frame or below profiles)
    global_actions_frame = ttk.Frame(top_controls_frame, padding="10")
    global_actions_frame.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X, anchor='n')
    ttk.Button(global_actions_frame, text="Refresh All Displayed Data", command=refresh_all_gui_data).pack(pady=5, fill=tk.X)
    ttk.Button(global_actions_frame, text="Manual Scan ALL Active Profiles", command=trigger_manual_scan_all_active).pack(pady=5, fill=tk.X)

    # --- Notebook for Profile Details and Comparison ---
    notebook = ttk.Notebook(root)
    notebook.pack(expand=True, fill="both", padx=10, pady=10)

    # Tab 1: Selected Profile Details
    profile_details_tab = ttk.Frame(notebook)
    notebook.add(profile_details_tab, text="Selected Profile View")

    hold_frm = ttk.LabelFrame(profile_details_tab, text="Current Holdings", padding="5"); hold_frm.pack(expand=True, fill=tk.BOTH, pady=5, padx=5)
    hold_cols = ("Ticker", "Company", "Entry Time", "Entry Rank", "EVal", "EGro", "EMom", "EVGM", "Last Check", "Curr Rank", "CVal", "CGro", "CMom", "CVGM")
    holdings_tree = ttk.Treeview(hold_frm, columns=hold_cols, show="headings")
    # ... (Holdings tree setup as before) ...
    for col in hold_cols:
        w = 150 if "Time" in col or "Check" in col else (200 if "Company" in col else 70)
        a = tk.W if "Company" in col or "Time" in col else tk.CENTER
        t = col.replace("EVal","E:V").replace("EGro","E:G").replace("EMom","E:M").replace("EVGM","E:VGM").replace("CVal","C:V").replace("CGro","C:G").replace("CMom","C:M").replace("CVGM","C:VGM")
        holdings_tree.heading(col,text=t); holdings_tree.column(col,width=w,anchor=a,stretch=tk.YES if "Co" in col else tk.NO)
    h_vsb=ttk.Scrollbar(hold_frm,orient="vertical",command=holdings_tree.yview); h_hsb=ttk.Scrollbar(hold_frm,orient="horizontal",command=holdings_tree.xview)
    holdings_tree.configure(yscrollcommand=h_vsb.set,xscrollcommand=h_hsb.set); h_vsb.pack(side=tk.RIGHT,fill=tk.Y); h_hsb.pack(side=tk.BOTTOM,fill=tk.X); holdings_tree.pack(expand=True,fill=tk.BOTH)


    bot_det_pane = ttk.PanedWindow(profile_details_tab, orient=tk.HORIZONTAL); bot_det_pane.pack(expand=True, fill=tk.BOTH, pady=5, padx=5)
    trade_frm = ttk.LabelFrame(bot_det_pane, text="Trade Log", padding="5"); bot_det_pane.add(trade_frm, weight=3)
    trade_cols = ("Ticker","Co","Entry Time","Exit Time","E Rank","X Rank","E VGM","X VGM","Return %","Reason")
    tradelog_tree = ttk.Treeview(trade_frm, columns=trade_cols, show="headings")
    # ... (Trade log tree setup as before) ...
    for col in trade_cols:
        w=140 if "Time" in col else (180 if "Co" == col else (100 if "Reason" == col else 70)); a=tk.W if "Co" == col or "Time" in col or "Reason" == col else tk.CENTER
        tradelog_tree.heading(col,text=col); tradelog_tree.column(col,width=w,anchor=a,stretch=tk.YES if "Co"==col or "Reason"==col else tk.NO)
    tl_vsb=ttk.Scrollbar(trade_frm,orient="vertical",command=tradelog_tree.yview); tl_hsb=ttk.Scrollbar(trade_frm,orient="horizontal",command=tradelog_tree.xview)
    tradelog_tree.configure(yscrollcommand=tl_vsb.set,xscrollcommand=tl_hsb.set); tl_vsb.pack(side=tk.RIGHT,fill=tk.Y); tl_hsb.pack(side=tk.BOTTOM,fill=tk.X); tradelog_tree.pack(expand=True,fill=tk.BOTH)

    stats_frm = ttk.LabelFrame(bot_det_pane, text="Statistics", padding="5"); bot_det_pane.add(stats_frm, weight=1)
    total_return_label_var = tk.StringVar(value="Sum Return % (Placeholder): N/A"); total_trades_label_var = tk.StringVar(value="Total Trades: 0")
    ttk.Label(stats_frm, textvariable=total_return_label_var).pack(pady=5,anchor=tk.W); ttk.Label(stats_frm, textvariable=total_trades_label_var).pack(pady=5,anchor=tk.W)
    ttk.Label(stats_frm, text="Note: Return % is a placeholder.", font=('Helvetica', 8, 'italic')).pack(pady=(0,5), anchor=tk.W)

    # Tab 2: Profile Comparison
    comparison_tab = ttk.Frame(notebook)
    notebook.add(comparison_tab, text="Profile Comparison")

    comp_frm = ttk.LabelFrame(comparison_tab, text="Overall Profile Performance Comparison", padding="10")
    comp_frm.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)

    comp_cols = ("Profile Name", "Total Trades", "Winning Trades", "Losing Trades", "Total Return % (Placeholder)")
    comparison_tree = ttk.Treeview(comp_frm, columns=comp_cols, show="headings")
    for col in comp_cols:
        w = 250 if "Name" in col else 150
        comparison_tree.heading(col, text=col)
        comparison_tree.column(col, width=w, anchor=tk.W if "Name" in col else tk.CENTER, stretch=tk.YES if "Name" in col else tk.NO)

    comp_vsb = ttk.Scrollbar(comp_frm, orient="vertical", command=comparison_tree.yview)
    comp_hsb = ttk.Scrollbar(comp_frm, orient="horizontal", command=comparison_tree.xview)
    comparison_tree.configure(yscrollcommand=comp_vsb.set, xscrollcommand=comp_hsb.set)
    comp_vsb.pack(side=tk.RIGHT, fill=tk.Y); comp_hsb.pack(side=tk.BOTTOM, fill=tk.X)
    comparison_tree.pack(expand=True, fill=tk.BOTH)

    # Initial data loads
    load_profiles_into_listbox() # This will now also trigger comparison view update
    refresh_selected_profile_data_display() # Will show empty for selected profile initially
    # populate_profile_comparison_view() # Called by load_profiles_into_listbox

    root.mainloop()

if __name__ == "__main__":
    print("Main: Init app & scanner thread...")
    scan_thread = threading.Thread(target=hourly_scan_worker, daemon=True); scan_thread.start()
    create_main_window()
    print("Main: GUI closed."); scanner_active = False; print("Main: Exiting.")
