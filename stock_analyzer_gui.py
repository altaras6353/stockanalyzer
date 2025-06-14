import tkinter as tk
from tkinter import ttk
from tkinter import simpledialog, messagebox
import datetime
import threading
import time
import sqlite3

import scanner
from database_setup import connect_db, create_tables, add_predefined_profiles, DB_NAME

# --- Global Variables ---
root_window = None
holdings_tree = None
tradelog_tree = None
total_return_label_var = None
total_trades_label_var = None
winning_trades_label_var = None
losing_trades_label_var = None
buy_rule_text_var = None
sell_rule_text_var = None
profiles_listbox = None
selected_profile_id = None
profile_id_map = {}
comparison_tree = None
all_scanned_stocks_tree = None
notebook = None
scanner_active = True

# --- Helper Function for Profile Rule Display Text ---
def get_profile_rules_display_text(profile_type: str | None) -> dict:
    buy_rule = "Entry: Zacks Rank '1' AND (Style Scores: All 'A' OR Max 1 'B')."
    sell_rule = "N/A"
    if profile_type == "Cautious": sell_rule = "Exit: Rank is not '1' or '2' (i.e., >2) OR Calculated Score > 4."
    elif profile_type == "Hesitant": sell_rule = "Exit: Rank is not '1' OR Calculated Score > 5."
    elif profile_type == "Brave": sell_rule = "Exit: Rank is not '1', '2', or '3' (i.e., >3) OR Calculated Score > 6."
    elif profile_type == "Reckless": sell_rule = "Exit: Rank is '5' (i.e., >4) OR Score is invalid (penalty)."
    elif profile_type == "Greedy2Pct": sell_rule = "Exit: (Rank is not '1' OR Calculated Score > 4) OR Profit > 2%."
    elif profile_type == "Greedy3Pct": sell_rule = "Exit: (Rank is not '1' OR Calculated Score > 4) OR Profit > 3%."
    elif profile_type == "Greedy4Pct": sell_rule = "Exit: (Rank is not '1' OR Calculated Score > 4) OR Profit > 4%."
    elif profile_type is None or profile_type == "N/A (Custom)":
        buy_rule = "Entry: Rules not hardcoded; relies on structured rules if defined (feature currently for predefined only)."
        sell_rule = "Exit: Rules not hardcoded; relies on structured rules if defined (feature currently for predefined only)."
    return {'buy': buy_rule, 'sell': sell_rule}

# --- Profile Management Functions ---
def load_profiles_into_listbox():
    global profiles_listbox, profile_id_map, root_window
    if not profiles_listbox: return
    profiles_listbox.delete(0, tk.END); profile_id_map.clear()
    conn, cursor = None, None
    try:
        conn, cursor = connect_db()
        cursor.execute("SELECT profile_id, name, is_active FROM investor_profiles ORDER BY name ASC")
        fetched_profiles = cursor.fetchall()
        for index, profile_row in enumerate(fetched_profiles):
            profiles_listbox.insert(tk.END, f"{profile_row['name']} {'(Active)' if profile_row['is_active'] else '(Inactive)'}")
            profile_id_map[index] = profile_row['profile_id']
        if root_window: root_window.after(0, refresh_all_gui_data)
    except Exception as e: messagebox.showerror("DB Error", f"Failed to load profiles: {e}")
    finally:
        if conn: conn.close()

def on_profile_select(event):
    global selected_profile_id, profiles_listbox, profile_id_map
    if not profiles_listbox or not profiles_listbox.curselection():
        selected_profile_id = None; refresh_selected_profile_data_display(); return
    selected_profile_id = profile_id_map.get(profiles_listbox.curselection()[0])
    refresh_selected_profile_data_display()

def get_profile_data_for_display(profile_id_to_fetch):
    if profile_id_to_fetch is None: return None
    conn, cursor = None, None
    try:
        conn, cursor = connect_db()
        cursor.execute("SELECT profile_id, name, description, is_active, profile_type FROM investor_profiles WHERE profile_id = ?", (profile_id_to_fetch,))
        return cursor.fetchone()
    except Exception as e: messagebox.showerror("DB Error", f"Failed to fetch profile data: {e}"); return None
    finally:
        if conn: conn.close()

def open_profile_editor_window(profile_id_to_edit=None):
    global root_window
    existing_profile_row = get_profile_data_for_display(profile_id_to_edit) if profile_id_to_edit else None
    if profile_id_to_edit and not existing_profile_row: messagebox.showerror("Error", "Could not load profile data."); return
    editor_win = tk.Toplevel(root_window); editor_win.title("Edit Profile Notes/Status")
    editor_win.geometry("500x350"); editor_win.transient(root_window); editor_win.grab_set()
    main_info_frame = ttk.LabelFrame(editor_win, text="Profile Details", padding="10"); main_info_frame.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)
    ttk.Label(main_info_frame, text="Profile Name:").grid(row=0, column=0, sticky=tk.W, pady=2)
    name_var = tk.StringVar(value=existing_profile_row['name'] if existing_profile_row else ""); name_entry = ttk.Entry(main_info_frame, textvariable=name_var, width=50); name_entry.grid(row=0, column=1, sticky=tk.EW, pady=2)
    profile_type_text = existing_profile_row['profile_type'] if existing_profile_row and existing_profile_row['profile_type'] else "N/A (Custom)"
    ttk.Label(main_info_frame, text="Profile Type:").grid(row=1, column=0, sticky=tk.W, pady=2); ttk.Label(main_info_frame, text=profile_type_text).grid(row=1, column=1, sticky=tk.W, pady=2)
    is_active_var = tk.BooleanVar(value=bool(existing_profile_row['is_active']) if existing_profile_row else True); active_check = ttk.Checkbutton(main_info_frame, text="Is Active Profile", variable=is_active_var); active_check.grid(row=0, column=2, rowspan=2, sticky=tk.W, padx=10, pady=2); main_info_frame.columnconfigure(1, weight=1)
    ttk.Label(main_info_frame, text="Notes/Summary:").grid(row=2, column=0, sticky=tk.NW, pady=(10,2)); desc_text_notes = tk.Text(main_info_frame, height=5, width=60, wrap=tk.WORD); desc_text_notes.grid(row=3, column=0, columnspan=3, sticky=tk.EW, pady=2)
    if existing_profile_row and existing_profile_row['description']: desc_text_notes.insert(tk.END, existing_profile_row['description'])
    def save_profile_changes():
        name = name_var.get().strip(); notes_content = desc_text_notes.get("1.0", tk.END).strip(); is_active_val = 1 if is_active_var.get() else 0
        if not name: messagebox.showerror("Validation Error", "Profile Name cannot be empty.", parent=editor_win); return
        conn, cursor = None, None
        try:
            conn, cursor = connect_db(); current_profile_id = profile_id_to_edit
            if current_profile_id is None: messagebox.showerror("Error", "Adding new custom profiles is disabled.", parent=editor_win); return
            else: cursor.execute("UPDATE investor_profiles SET name=?, description=?, is_active=? WHERE profile_id=?",(name, notes_content, is_active_val, current_profile_id))
            conn.commit(); messagebox.showinfo("Success", "Profile changes saved.", parent=editor_win); load_profiles_into_listbox(); refresh_selected_profile_data_display(); editor_win.destroy()
        except sqlite3.IntegrityError: messagebox.showerror("DB Error", f"Profile name '{name}' already exists.", parent=editor_win)
        except Exception as e: messagebox.showerror("DB Error", f"Save failed: {e}", parent=editor_win)
        finally:
            if conn:conn.close()
    btn_frame_editor = ttk.Frame(editor_win); btn_frame_editor.pack(pady=10, fill=tk.X, side=tk.BOTTOM); ttk.Button(btn_frame_editor, text="Save Changes", command=save_profile_changes).pack(side=tk.RIGHT, padx=10); ttk.Button(btn_frame_editor, text="Cancel", command=editor_win.destroy).pack(side=tk.RIGHT); name_entry.focus_set()

def delete_selected_profile():
    global selected_profile_id
    if selected_profile_id is None: messagebox.showwarning("No Profile", "No profile selected."); return
    profile_data_row = get_profile_data_for_display(selected_profile_id)
    if not profile_data_row or not messagebox.askyesno("Confirm Delete",f"Delete '{profile_data_row['name']}'?\nAll associated data will be removed."): return
    conn,cursor=None,None
    try:
        conn,cursor=connect_db(); cursor.execute("DELETE FROM investor_profiles WHERE profile_id=?",(selected_profile_id,)); conn.commit()
        messagebox.showinfo("Success",f"Profile '{profile_data_row['name']}' deleted.")
        load_profiles_into_listbox();selected_profile_id=None;refresh_selected_profile_data_display()
    except Exception as e: messagebox.showerror("DB Error",f"Delete failed: {e}")
    finally:
        if conn:conn.close()

# --- Refresh Data Display Functions ---
def refresh_selected_profile_data_display():
    global holdings_tree,tradelog_tree,total_return_label_var,total_trades_label_var,selected_profile_id,root_window
    global winning_trades_label_var, losing_trades_label_var, buy_rule_text_var, sell_rule_text_var

    profile_name="None Selected"; profile_type_for_rules = None
    if selected_profile_id:
        profile_data_row = get_profile_data_for_display(selected_profile_id)
        if profile_data_row: profile_name = profile_data_row['name']; profile_type_for_rules = profile_data_row['profile_type']
    if root_window:root_window.title(f"Zacks Stock Analyzer - Profile: {profile_name}")
    rules_text = get_profile_rules_display_text(profile_type_for_rules)
    if buy_rule_text_var: buy_rule_text_var.set(rules_text.get('buy', 'N/A'))
    if sell_rule_text_var: sell_rule_text_var.set(rules_text.get('sell', 'N/A'))
    if not holdings_tree or not tradelog_tree: return
    for i in holdings_tree.get_children(): holdings_tree.delete(i)
    for i in tradelog_tree.get_children(): tradelog_tree.delete(i)
    if total_trades_label_var: total_trades_label_var.set("Total Trades: N/A")
    if total_return_label_var: total_return_label_var.set("Sum of Returns: N/A")
    if winning_trades_label_var: winning_trades_label_var.set("Winning Trades: N/A")
    if losing_trades_label_var: losing_trades_label_var.set("Losing Trades: N/A")
    if selected_profile_id is None : return
    conn,cursor=None,None
    try:
        conn,cursor=connect_db()
        h_q="SELECT ticker, company_name, entry_timestamp, entry_zacks_rank, entry_style_value, entry_style_growth, entry_style_momentum, entry_style_vgm, entry_price, last_checked_timestamp, current_zacks_rank, current_style_value, current_style_growth, current_style_momentum, current_style_vgm FROM stock_holdings WHERE profile_id=? ORDER BY entry_timestamp DESC"
        fetched_holdings = cursor.execute(h_q,(selected_profile_id,)).fetchall()
        for row_data in fetched_holdings:
            def get_val(r, key, default="N/A"):
                try: val = r[key]; return val if val is not None else default
                except (IndexError, KeyError): return default
            entry_price_val = f"{get_val(row_data, 'entry_price', 0.0):.2f}" if isinstance(get_val(row_data, 'entry_price', None), (int, float)) else "N/A"
            values_tuple = (
                str(get_val(row_data, 'ticker')), str(get_val(row_data, 'company_name')),
                str(get_val(row_data, 'entry_timestamp')), str(get_val(row_data, 'entry_zacks_rank')),
                entry_price_val, str(get_val(row_data, 'entry_style_value')),
                str(get_val(row_data, 'entry_style_growth')), str(get_val(row_data, 'entry_style_momentum')),
                str(get_val(row_data, 'entry_style_vgm')), str(get_val(row_data, 'last_checked_timestamp')),
                str(get_val(row_data, 'current_zacks_rank')), str(get_val(row_data, 'current_style_value')),
                str(get_val(row_data, 'current_style_growth')), str(get_val(row_data, 'current_style_momentum')),
                str(get_val(row_data, 'current_style_vgm'))
            )
            holdings_tree.insert('', tk.END, values=values_tuple)

        tl_q="SELECT ticker, company_name, entry_timestamp, exit_timestamp, entry_zacks_rank, exit_zacks_rank, entry_style_vgm, exit_style_vgm, entry_price, exit_price, return_percentage, reason_for_exit FROM trade_logs WHERE profile_id=? ORDER BY exit_timestamp DESC"
        fetched_tradelogs = cursor.execute(tl_q,(selected_profile_id,)).fetchall()
        for row_data in fetched_tradelogs:
            def get_val_tl(r, key, default="N/A"):
                try: val = r[key]; return val if val is not None else default
                except (IndexError, KeyError): return default
            entry_price_tl = f"{get_val_tl(row_data, 'entry_price', 0.0):.2f}" if isinstance(get_val_tl(row_data, 'entry_price', None), (int, float)) else "N/A"
            exit_price_tl = f"{get_val_tl(row_data, 'exit_price', 0.0):.2f}" if isinstance(get_val_tl(row_data, 'exit_price', None), (int, float)) else "N/A"
            return_pct_tl = f"{get_val_tl(row_data, 'return_percentage', 0.0):.2f}%" if isinstance(get_val_tl(row_data, 'return_percentage', None), (int, float)) else "N/A"
            values_tuple_tl = (
                str(get_val_tl(row_data, 'ticker')), str(get_val_tl(row_data, 'company_name')),
                str(get_val_tl(row_data, 'entry_timestamp')), str(get_val_tl(row_data, 'exit_timestamp')),
                str(get_val_tl(row_data, 'entry_zacks_rank')), str(get_val_tl(row_data, 'exit_zacks_rank')),
                str(get_val_tl(row_data, 'entry_style_vgm')), str(get_val_tl(row_data, 'exit_style_vgm')),
                entry_price_tl, exit_price_tl, return_pct_tl, str(get_val_tl(row_data, 'reason_for_exit'))
            )
            tradelog_tree.insert('', tk.END, values=values_tuple_tl)

        cursor.execute("SELECT COUNT(*),SUM(return_percentage) FROM trade_logs WHERE profile_id=?",(selected_profile_id,));stats=cursor.fetchone()
        total_trades=stats['COUNT(*)'] if stats and stats['COUNT(*)'] is not None else 0
        total_return=stats['SUM(return_percentage)'] if stats and stats['SUM(return_percentage)'] is not None else 0.0
        cursor.execute("SELECT COUNT(*) FROM trade_logs WHERE profile_id=? AND return_percentage > 0",(selected_profile_id,));win_trades_row=cursor.fetchone();winning_trades=win_trades_row['COUNT(*)'] if win_trades_row else 0
        cursor.execute("SELECT COUNT(*) FROM trade_logs WHERE profile_id=? AND return_percentage <= 0",(selected_profile_id,));lose_trades_row=cursor.fetchone();losing_trades=lose_trades_row['COUNT(*)'] if lose_trades_row else 0
        if total_trades_label_var:total_trades_label_var.set(f"Total Trades: {total_trades}")
        if total_return_label_var:total_return_label_var.set(f"Sum of Returns: {total_return:.2f}%")
        if winning_trades_label_var: winning_trades_label_var.set(f"Winning Trades: {winning_trades}")
        if losing_trades_label_var: losing_trades_label_var.set(f"Losing Trades: {losing_trades}")
    except Exception as e: messagebox.showerror("DB Error",f"Refresh failed: {e}")
    finally:
        if conn:conn.close()

def populate_profile_comparison_view():
    global comparison_tree
    if not comparison_tree: return
    for i in comparison_tree.get_children(): comparison_tree.delete(i)
    conn,cursor=None,None
    try:
        conn,cursor=connect_db();cursor.execute("SELECT profile_id,name FROM investor_profiles WHERE is_active=1 ORDER BY name ASC")
        fetched_profiles = cursor.fetchall()
        for profile_row in fetched_profiles:
            pid = profile_row['profile_id']; name = profile_row['name']
            cursor.execute("SELECT COUNT(*),SUM(return_percentage) FROM trade_logs WHERE profile_id=?",(pid,))
            stats=cursor.fetchone();trades=stats['COUNT(*)'] if stats and stats['COUNT(*)'] is not None else 0;ret=stats['SUM(return_percentage)'] if stats and stats['SUM(return_percentage)'] is not None else 0.0
            cursor.execute("SELECT COUNT(*) FROM trade_logs WHERE profile_id=? AND return_percentage > 0",(pid,));win_row=cursor.fetchone();wt=win_row['COUNT(*)'] if win_row else 0
            cursor.execute("SELECT COUNT(*) FROM trade_logs WHERE profile_id=? AND return_percentage <= 0",(pid,));lose_row=cursor.fetchone();lt=lose_row['COUNT(*)'] if lose_row else 0
            comparison_tree.insert('',tk.END,values=(name,trades,wt,lt,f"{ret:.2f}%"))
    except Exception as e: messagebox.showerror("DB Error",f"Comparison populate failed: {e}")
    finally:
        if conn:conn.close()

def populate_all_scanned_stocks_view():
    global all_scanned_stocks_tree
    if not all_scanned_stocks_tree: return
    for i in all_scanned_stocks_tree.get_children(): all_scanned_stocks_tree.delete(i)
    if hasattr(scanner,'last_raw_scan_results') and scanner.last_raw_scan_results:
        for stock_data in scanner.last_raw_scan_results:
            all_scanned_stocks_tree.insert('',tk.END,values=(stock_data.get('Company Name','N/A'),stock_data.get('Ticker Symbol','N/A'),stock_data.get('Zacks Rank','N/A'),stock_data.get('Value Score','N/A'),stock_data.get('Growth Score','N/A'),stock_data.get('Momentum Score','N/A'),stock_data.get('VGM Score','N/A'),stock_data.get('Stock Page URL','N/A')))

def refresh_all_gui_data():
    refresh_selected_profile_data_display()
    populate_profile_comparison_view()
    populate_all_scanned_stocks_view()

def trigger_manual_scan_all_active():
    threading.Thread(target=lambda: (scanner.scan_and_update_all_active_profiles(), root_window.after(0, refresh_all_gui_data) if root_window else None), daemon=True).start()
    messagebox.showinfo("Scan Started", "Manual scan for ALL active profiles initiated.")

# --- Background Scanner Worker ---
def hourly_scan_worker():
    global scanner_active, root_window
    try:
        print("BG Scanner: Initializing DB for worker thread...")
        conn_init,cursor_init=connect_db()
        create_tables(cursor_init);conn_init.commit()
        add_predefined_profiles(conn_init,cursor_init)
        conn_init.close(); print("BG Scanner: DB setup confirmed for worker thread.")
    except Exception as e: print(f"BG Scanner: DB setup error: {e}. Thread stopping."); return

    print("BG Scanner: Thread started (scans ALL active profiles).")
    while scanner_active:
        print(f"\n[{datetime.datetime.now()}] BG Scanner: Starting scheduled scan (ALL active)...")
        try:
            scanner.scan_and_update_all_active_profiles()
            print(f"[{datetime.datetime.now()}] BG Scanner: Hourly scan complete.")
            if root_window and scanner_active: root_window.after(0, refresh_all_gui_data)
        except Exception as e: print(f"[{datetime.datetime.now()}] BG Scanner: Error during scan (ALL active): {e}")

        sleep_duration = 3600 # FINAL: 1 hour (3600 seconds)

        print(f"[{datetime.datetime.now()}] BG Scanner: Next scan in {sleep_duration // 3600} hour(s).")

        # Simplified sleep logic
        if scanner_active:
            print(f"[{datetime.datetime.now()}] BG Scanner: Entering sleep for {sleep_duration} seconds...")
            time.sleep(sleep_duration)
            if scanner_active: # Check again after sleep, in case app closed during sleep
                 print(f"[{datetime.datetime.now()}] BG Scanner: Woke up from sleep.")
            else:
                 print(f"[{datetime.datetime.now()}] BG Scanner: Woke up but scanner no longer active.")

    print("BG Scanner: Thread stopped.")

def on_closing(): global scanner_active,root_window; scanner_active=False; print("GUI: Closing..."); root_window.destroy() if root_window else None

# --- Main Window Creation ---
def create_main_window():
    global root_window, holdings_tree, tradelog_tree, profiles_listbox, notebook, comparison_tree, all_scanned_stocks_tree
    global total_return_label_var, total_trades_label_var, winning_trades_label_var, losing_trades_label_var
    global buy_rule_text_var, sell_rule_text_var

    root = tk.Tk(); root_window = root
    # print("DEBUG GUI: tk.Tk() created.") # This won't be reached in headless

    root.title("Zacks Stock Analyzer"); root.geometry("1400x950"); root.protocol("WM_DELETE_WINDOW", on_closing)
    top_controls_frame=ttk.Frame(root,padding="5"); top_controls_frame.pack(side=tk.TOP,fill=tk.X,pady=(5,0))
    profiles_frame_cont=ttk.LabelFrame(top_controls_frame,text="Investor Profiles",padding="10"); profiles_frame_cont.pack(side=tk.LEFT,padx=5,fill=tk.Y)
    prof_list_sb_frame=ttk.Frame(profiles_frame_cont); prof_list_sb_frame.pack(pady=5,expand=True,fill=tk.BOTH)
    profiles_listbox=tk.Listbox(prof_list_sb_frame,exportselection=False,height=10,width=35)
    prof_list_sb=ttk.Scrollbar(prof_list_sb_frame,orient=tk.VERTICAL,command=profiles_listbox.yview); profiles_listbox.configure(yscrollcommand=prof_list_sb.set)
    profiles_listbox.pack(side=tk.LEFT,expand=True,fill=tk.BOTH); prof_list_sb.pack(side=tk.RIGHT,fill=tk.Y)
    profiles_listbox.bind("<<ListboxSelect>>",on_profile_select)
    prof_btn_frm=ttk.Frame(profiles_frame_cont); prof_btn_frm.pack(fill=tk.X,pady=5,side=tk.BOTTOM)
    add_btn = ttk.Button(prof_btn_frm,text="Add New",command=lambda:open_profile_editor_window(), state=tk.DISABLED); add_btn.pack(side=tk.LEFT,expand=True,fill=tk.X)
    ttk.Button(prof_btn_frm,text="Edit Notes",command=lambda:open_profile_editor_window(selected_profile_id) if selected_profile_id is not None else messagebox.showinfo("Info","Select profile to edit.")).pack(side=tk.LEFT,expand=True,fill=tk.X)
    ttk.Button(prof_btn_frm,text="Del Profile",command=delete_selected_profile).pack(side=tk.LEFT,expand=True,fill=tk.X)
    global_actions_frame=ttk.Frame(top_controls_frame,padding="10"); global_actions_frame.pack(side=tk.LEFT,padx=5,expand=True,fill=tk.X,anchor='n')
    ttk.Button(global_actions_frame,text="Refresh All Displayed Data",command=refresh_all_gui_data).pack(pady=5,fill=tk.X)
    ttk.Button(global_actions_frame,text="Manual Scan ALL Active Profiles",command=trigger_manual_scan_all_active).pack(pady=5,fill=tk.X)

    notebook=ttk.Notebook(root); notebook.pack(expand=True,fill="both",padx=10,pady=10)
    profile_details_tab=ttk.Frame(notebook); notebook.add(profile_details_tab,text="Selected Profile View")

    hold_frm=ttk.LabelFrame(profile_details_tab,text="Current Holdings",padding="5");hold_frm.pack(expand=True,fill=tk.BOTH,pady=5,padx=5)
    hold_cols=("Ticker","Co","Entry Time","Entry Rank","E:Price","E:V","E:G","E:M","E:VGM","Last Check","C Rank","C:V","C:G","C:M","C:VGM")
    holdings_tree=ttk.Treeview(hold_frm,columns=hold_cols,show="headings")
    for col in hold_cols: w=150 if "Time" in col or "Check" in col else (180 if "Co"==col else (80 if "Price" in col else 65)); holdings_tree.heading(col,text=col); holdings_tree.column(col,width=w,anchor=tk.W if "Co"==col or "Time" in col else tk.CENTER,stretch="Co" in col)
    h_vsb=ttk.Scrollbar(hold_frm,orient="vertical",command=holdings_tree.yview);h_hsb=ttk.Scrollbar(hold_frm,orient="horizontal",command=holdings_tree.xview);holdings_tree.configure(yscrollcommand=h_vsb.set,xscrollcommand=h_hsb.set);h_vsb.pack(side=tk.RIGHT,fill=tk.Y);h_hsb.pack(side=tk.BOTTOM,fill=tk.X);holdings_tree.pack(expand=True,fill=tk.BOTH)

    bot_det_pane=ttk.PanedWindow(profile_details_tab,orient=tk.HORIZONTAL);bot_det_pane.pack(expand=True,fill=tk.BOTH,pady=5,padx=5)
    trade_frm=ttk.LabelFrame(bot_det_pane,text="Trade Log",padding="5");bot_det_pane.add(trade_frm,weight=2)
    trade_cols=("Ticker","Co","Entry Time","Exit Time","E Rank","X Rank","E VGM","X VGM","E Price","X Price","Return %","Reason")
    tradelog_tree=ttk.Treeview(trade_frm,columns=trade_cols,show="headings")
    for col in trade_cols: w=140 if "Time" in col else (180 if "Co"==col else (100 if "Reason"==col else (70))); tradelog_tree.heading(col,text=col);tradelog_tree.column(col,width=w,anchor=tk.W if "Co"==col or "Time" in col or "Reason"==col else tk.CENTER,stretch="Co" in col or "Reason" in col)
    tl_vsb=ttk.Scrollbar(trade_frm,orient="vertical",command=tradelog_tree.yview);tl_hsb=ttk.Scrollbar(trade_frm,orient="horizontal",command=tradelog_tree.xview);tradelog_tree.configure(yscrollcommand=tl_vsb.set,xscrollcommand=tl_hsb.set);tl_vsb.pack(side=tk.RIGHT,fill=tk.Y);tl_hsb.pack(side=tk.BOTTOM,fill=tk.X);tradelog_tree.pack(expand=True,fill=tk.BOTH)

    stats_rules_frame = ttk.Frame(bot_det_pane); bot_det_pane.add(stats_rules_frame, weight=1)
    stats_frm=ttk.LabelFrame(stats_rules_frame,text="Statistics",padding="5");stats_frm.pack(fill=tk.X,padx=5,pady=(0,5),anchor='n')
    total_return_label_var=tk.StringVar(value="Sum of Returns: N/A");total_trades_label_var=tk.StringVar(value="Total Trades: 0");winning_trades_label_var=tk.StringVar(value="Winning Trades: N/A");losing_trades_label_var=tk.StringVar(value="Losing Trades: N/A")
    ttk.Label(stats_frm,textvariable=total_trades_label_var).pack(pady=2,anchor=tk.W);ttk.Label(stats_frm,textvariable=winning_trades_label_var).pack(pady=2,anchor=tk.W);ttk.Label(stats_frm,textvariable=losing_trades_label_var).pack(pady=2,anchor=tk.W);ttk.Label(stats_frm,textvariable=total_return_label_var).pack(pady=2,anchor=tk.W)
    ttk.Label(stats_frm,text="Note: Return % based on available price data.",font=('Helvetica',8,'italic')).pack(pady=(5,0),anchor=tk.W)
    rules_display_frame = ttk.LabelFrame(stats_rules_frame, text="Profile Rules Summary (Predefined)", padding="10");rules_display_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5,anchor='n')
    buy_rule_text_var = tk.StringVar(value="N/A"); sell_rule_text_var = tk.StringVar(value="N/A")
    ttk.Label(rules_display_frame, text="Buy Rules:", font=('Helvetica', 10, 'bold')).pack(anchor=tk.W);ttk.Label(rules_display_frame, textvariable=buy_rule_text_var, wraplength=350, justify=tk.LEFT).pack(fill=tk.X, pady=(0,5))
    ttk.Label(rules_display_frame, text="Sell Rules:", font=('Helvetica', 10, 'bold')).pack(anchor=tk.W);ttk.Label(rules_display_frame, textvariable=sell_rule_text_var, wraplength=350, justify=tk.LEFT).pack(fill=tk.X)

    comparison_tab=ttk.Frame(notebook);notebook.add(comparison_tab,text="Profile Comparison")
    comp_frm=ttk.LabelFrame(comparison_tab,text="Overall Profile Performance Comparison",padding="10");comp_frm.pack(expand=True,fill=tk.BOTH,padx=10,pady=10)
    comp_cols=("Profile Name","Total Trades","Winning Trades","Losing Trades","Total Return %");comparison_tree=ttk.Treeview(comp_frm,columns=comp_cols,show="headings")
    for col in comp_cols:w=250 if "Name" in col else 150;comparison_tree.heading(col,text=col.replace(" (Placeholder)",""));comparison_tree.column(col,width=w,anchor=tk.W if "Name" in col else tk.CENTER,stretch="Name" in col)
    comp_vsb=ttk.Scrollbar(comp_frm,orient="vertical",command=comparison_tree.yview);comp_hsb=ttk.Scrollbar(comp_frm,orient="horizontal",command=comparison_tree.xview);comparison_tree.configure(yscrollcommand=comp_vsb.set,xscrollcommand=comp_hsb.set);comp_vsb.pack(side=tk.RIGHT,fill=tk.Y);comp_hsb.pack(side=tk.BOTTOM,fill=tk.X);comparison_tree.pack(expand=True,fill=tk.BOTH)

    all_scanned_tab_frame = ttk.Frame(notebook); notebook.add(all_scanned_tab_frame, text="All Scanned Stocks")
    scanned_stocks_lf=ttk.LabelFrame(all_scanned_tab_frame,text="Results from Last Market Scan",padding="10");scanned_stocks_lf.pack(expand=True,fill=tk.BOTH,padx=10,pady=10)
    scanned_cols=("Company Name","Ticker","Zacks Rank","Value","Growth","Momentum","VGM","Stock Page URL");all_scanned_stocks_tree=ttk.Treeview(scanned_stocks_lf,columns=scanned_cols,show="headings")
    for col_name in scanned_cols: col_w=250 if "Company" in col_name else(300 if "URL" in col_name else 100);col_a=tk.W if "Company" in col_name or "URL" in col_name else tk.CENTER; all_scanned_stocks_tree.heading(col_name,text=col_name);all_scanned_stocks_tree.column(col_name,width=col_w,anchor=col_a,stretch=tk.YES if "Company" in col_name or "URL" in col_name else tk.NO)
    sc_vsb=ttk.Scrollbar(scanned_stocks_lf,orient="vertical",command=all_scanned_stocks_tree.yview);sc_hsb=ttk.Scrollbar(scanned_stocks_lf,orient="horizontal",command=all_scanned_stocks_tree.xview);all_scanned_stocks_tree.configure(yscrollcommand=sc_vsb.set,xscrollcommand=sc_hsb.set);sc_vsb.pack(side=tk.RIGHT,fill=tk.Y);sc_hsb.pack(side=tk.BOTTOM,fill=tk.X);all_scanned_stocks_tree.pack(expand=True,fill=tk.BOTH)

    load_profiles_into_listbox()
    # Removed the specific debug block from here, load_profiles_into_listbox -> refresh_all_gui_data -> refresh_selected_profile_data_display
    # will run with selected_profile_id = None initially, which should execute the debug prints for empty state.
    # If a profile is auto-selected by some Tkinter default, its data might show.

    root.mainloop()

if __name__ == "__main__":
    print("Main: Init app & scanner thread..."); scan_thread = threading.Thread(target=hourly_scan_worker, daemon=True); scan_thread.start()
    create_main_window()
    print("Main: GUI closed."); scanner_active = False; print("Main: Exiting.")
