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
# For selected profile stats
total_return_label_var = None
total_trades_label_var = None
winning_trades_label_var = None # New
losing_trades_label_var = None  # New
# For Profile Management
profiles_listbox = None
selected_profile_id = None
profile_id_map = {}
# For "Profile Comparison" tab
comparison_tree = None
notebook = None
scanner_active = True

# --- Profile Management Functions ---
def load_profiles_into_listbox(): # Mostly same, calls full refresh
    global profiles_listbox, profile_id_map, root_window
    if not profiles_listbox: return
    profiles_listbox.delete(0, tk.END); profile_id_map.clear()
    conn, cursor = None, None
    try:
        conn, cursor = connect_db()
        cursor.execute("SELECT profile_id, name, is_active FROM investor_profiles ORDER BY name ASC")
        for index, (pid, name, is_active_val) in enumerate(cursor.fetchall()):
            profiles_listbox.insert(tk.END, f"{name} {'(Active)' if is_active_val else '(Inactive)'}")
            profile_id_map[index] = pid
        if root_window: root_window.after(0, refresh_all_gui_data) # Refresh all, including comparison
    except Exception as e: messagebox.showerror("DB Error", f"Failed to load profiles: {e}")
    finally:
        if conn: conn.close()

def on_profile_select(event): # Mostly same
    global selected_profile_id, profiles_listbox, profile_id_map
    if not profiles_listbox or not profiles_listbox.curselection():
        selected_profile_id = None; refresh_selected_profile_data_display(); return
    selected_profile_id = profile_id_map.get(profiles_listbox.curselection()[0])
    refresh_selected_profile_data_display()

def get_profile_data_for_editor(profile_id_to_fetch): # Simplified, no rules from profile_rules needed for editor now
    if profile_id_to_fetch is None: return None
    conn, cursor = None, None
    try:
        conn, cursor = connect_db()
        # Fetch profile_type as well
        cursor.execute("SELECT profile_id, name, description, is_active, profile_type FROM investor_profiles WHERE profile_id = ?", (profile_id_to_fetch,))
        return cursor.fetchone() # Returns a Row object or None
    except Exception as e: messagebox.showerror("DB Error", f"Failed to fetch profile data: {e}"); return None
    finally:
        if conn: conn.close()

def open_profile_editor_window(profile_id_to_edit=None): # Major Changes Here
    global root_window

    existing_profile_row = get_profile_data_for_editor(profile_id_to_edit) if profile_id_to_edit else None

    if profile_id_to_edit and not existing_profile_row:
        messagebox.showerror("Error", "Could not load profile data."); return

    editor_win = tk.Toplevel(root_window)
    editor_win.title("Edit Profile" if existing_profile_row else "Add Profile (Disabled - Use Predefined)")
    editor_win.geometry("500x350") # Adjusted size
    editor_win.transient(root_window); editor_win.grab_set()

    main_info_frame = ttk.LabelFrame(editor_win, text="Profile Details", padding="10")
    main_info_frame.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

    ttk.Label(main_info_frame, text="Profile Name:").grid(row=0, column=0, sticky=tk.W, pady=2)
    name_var = tk.StringVar(value=existing_profile_row['name'] if existing_profile_row else "")
    name_entry = ttk.Entry(main_info_frame, textvariable=name_var, width=50)
    name_entry.grid(row=0, column=1, sticky=tk.EW, pady=2)

    profile_type_text = existing_profile_row['profile_type'] if existing_profile_row and existing_profile_row['profile_type'] else "N/A (Custom)"
    ttk.Label(main_info_frame, text="Profile Type:").grid(row=1, column=0, sticky=tk.W, pady=2)
    ttk.Label(main_info_frame, text=profile_type_text).grid(row=1, column=1, sticky=tk.W, pady=2)

    is_active_var = tk.BooleanVar(value=bool(existing_profile_row['is_active']) if existing_profile_row else True)
    active_check = ttk.Checkbutton(main_info_frame, text="Is Active Profile", variable=is_active_var)
    active_check.grid(row=0, column=2, rowspan=2, sticky=tk.W, padx=10, pady=2) # Moved next to name/type
    main_info_frame.columnconfigure(1, weight=1)

    ttk.Label(main_info_frame, text="Notes/Summary:").grid(row=2, column=0, sticky=tk.NW, pady=(10,2))
    desc_text_notes = tk.Text(main_info_frame, height=5, width=60, wrap=tk.WORD)
    desc_text_notes.grid(row=3, column=0, columnspan=3, sticky=tk.EW, pady=2)
    if existing_profile_row and existing_profile_row['description']:
        desc_text_notes.insert(tk.END, existing_profile_row['description'])

    # Rule editing UI (Zacks, Style, Pattern) is REMOVED for predefined profiles.
    # Description field is now for notes/summary.

    def save_profile_changes(): # Simplified save
        name = name_var.get().strip()
        notes_content = desc_text_notes.get("1.0", tk.END).strip()
        is_active_val = 1 if is_active_var.get() else 0

        if not name: messagebox.showerror("Validation Error", "Profile Name cannot be empty.", parent=editor_win); return

        conn, cursor = None, None
        try:
            conn, cursor = connect_db()
            current_profile_id = profile_id_to_edit

            if current_profile_id is None: # Adding new - this path should be disabled now
                messagebox.showerror("Error", "Adding new custom profiles is disabled for this version.", parent=editor_win)
                return
            else: # Editing existing profile
                # Only name, description (notes), and is_active can be changed for predefined profiles.
                # profile_type is fixed. Structured rules are not edited here.
                cursor.execute("UPDATE investor_profiles SET name=?, description=?, is_active=? WHERE profile_id=?",
                               (name, notes_content, is_active_val, current_profile_id))
                print(f"GUI: Updated profile ID: {current_profile_id} (Name, Notes, Active status only)")

            conn.commit()
            messagebox.showinfo("Success", "Profile changes saved.", parent=editor_win)
            load_profiles_into_listbox() # This also refreshes comparison view
            refresh_selected_profile_data_display() # Refresh details if this was the selected one
            editor_win.destroy()
        except sqlite3.IntegrityError: messagebox.showerror("DB Error", f"A profile with the name '{name}' already exists.", parent=editor_win)
        except Exception as e: print(f"GUI Error: Error saving profile: {e}"); messagebox.showerror("DB Error", f"Failed to save profile: {e}", parent=editor_win)
        finally:
            if conn: conn.close()

    btn_frame_editor = ttk.Frame(editor_win); btn_frame_editor.pack(pady=10, fill=tk.X, side=tk.BOTTOM)
    ttk.Button(btn_frame_editor, text="Save Changes", command=save_profile_changes).pack(side=tk.RIGHT, padx=10)
    ttk.Button(btn_frame_editor, text="Cancel", command=editor_win.destroy).pack(side=tk.RIGHT)
    name_entry.focus_set()

def delete_selected_profile(): # Same as before, ON DELETE CASCADE handles rules
    global selected_profile_id
    if selected_profile_id is None: messagebox.showwarning("No Profile", "No profile selected."); return
    profile_data = get_profile_data_for_editor(selected_profile_id) # Fetches main data
    if not profile_data or not messagebox.askyesno("Confirm Delete",f"Delete '{profile_data['name']}'?\nAll associated data will be removed."): return
    conn,cursor=None,None
    try:
        conn,cursor=connect_db(); cursor.execute("DELETE FROM investor_profiles WHERE profile_id=?",(selected_profile_id,)); conn.commit()
        messagebox.showinfo("Success",f"Profile '{profile_data['name']}' deleted.")
        load_profiles_into_listbox();selected_profile_id=None;refresh_selected_profile_data_display()
    except Exception as e: messagebox.showerror("DB Error",f"Delete failed: {e}")
    finally:
        if conn:conn.close()

# --- Refresh Data Display Functions ---
def refresh_selected_profile_data_display():
    global holdings_tree,tradelog_tree,total_return_label_var,total_trades_label_var,selected_profile_id,root_window
    global winning_trades_label_var, losing_trades_label_var # New stat vars

    profile_name="None Selected"
    if selected_profile_id:
        profile_data=get_profile_data_for_editor(selected_profile_id)
        if profile_data: profile_name=profile_data['name']
    if root_window:root_window.title(f"Zacks Stock Analyzer - Profile: {profile_name}")

    if not holdings_tree or not tradelog_tree: return
    for i in holdings_tree.get_children(): holdings_tree.delete(i)
    for i in tradelog_tree.get_children(): tradelog_tree.delete(i)

    # Update stat labels to N/A before fetching
    if total_trades_label_var: total_trades_label_var.set("Total Trades: N/A")
    if total_return_label_var: total_return_label_var.set("Sum of Returns: N/A") # Removed (Placeholder)
    if winning_trades_label_var: winning_trades_label_var.set("Winning Trades: N/A")
    if losing_trades_label_var: losing_trades_label_var.set("Losing Trades: N/A")

    if selected_profile_id is None: return
    conn,cursor=None,None
    try:
        conn,cursor=connect_db()
        # Holdings: Added entry_price
        h_q="SELECT ticker,company_name,entry_timestamp,entry_zacks_rank,entry_style_value,entry_style_growth,entry_style_momentum,entry_style_vgm,entry_price,last_checked_timestamp,current_zacks_rank,current_style_value,current_style_growth,current_style_momentum,current_style_vgm FROM stock_holdings WHERE profile_id=? ORDER BY entry_timestamp DESC"
        cursor.execute(h_q,(selected_profile_id,));[holdings_tree.insert('',tk.END,values=r) for r in cursor.fetchall()]

        # Trade Logs: Added entry_price, exit_price. Return % is now actual.
        tl_q="SELECT ticker,company_name,entry_timestamp,exit_timestamp,entry_zacks_rank,exit_zacks_rank,entry_style_vgm,exit_style_vgm,entry_price,exit_price,return_percentage,reason_for_exit FROM trade_logs WHERE profile_id=? ORDER BY exit_timestamp DESC"
        cursor.execute(tl_q,(selected_profile_id,));[tradelog_tree.insert('',tk.END,values=r) for r in cursor.fetchall()]

        # Statistics: Updated for actual returns and winning/losing trades
        cursor.execute("SELECT COUNT(*), SUM(return_percentage) FROM trade_logs WHERE profile_id=?",(selected_profile_id,));stats=cursor.fetchone()
        total_trades=stats[0] if stats and stats[0] is not None else 0
        total_return=stats[1] if stats and stats[1] is not None else 0.0

        cursor.execute("SELECT COUNT(*) FROM trade_logs WHERE profile_id=? AND return_percentage > 0",(selected_profile_id,));win_trades_row=cursor.fetchone()
        winning_trades=win_trades_row[0] if win_trades_row else 0

        cursor.execute("SELECT COUNT(*) FROM trade_logs WHERE profile_id=? AND return_percentage <= 0",(selected_profile_id,));lose_trades_row=cursor.fetchone()
        losing_trades=lose_trades_row[0] if lose_trades_row else 0

        if total_trades_label_var:total_trades_label_var.set(f"Total Trades: {total_trades}")
        if total_return_label_var:total_return_label_var.set(f"Sum of Returns: {total_return:.2f}%") # Removed (Placeholder)
        if winning_trades_label_var: winning_trades_label_var.set(f"Winning Trades: {winning_trades}")
        if losing_trades_label_var: losing_trades_label_var.set(f"Losing Trades: {losing_trades}")

    except Exception as e: messagebox.showerror("DB Error",f"Refresh failed: {e}")
    finally:
        if conn:conn.close()

def populate_profile_comparison_view(): # Updated for new stats
    global comparison_tree
    if not comparison_tree: return
    for i in comparison_tree.get_children(): comparison_tree.delete(i)
    conn,cursor=None,None
    try:
        conn,cursor=connect_db();cursor.execute("SELECT profile_id,name FROM investor_profiles WHERE is_active=1 ORDER BY name ASC") # Only active
        profiles_data = cursor.fetchall()
        for pid,name in profiles_data:
            cursor.execute("SELECT COUNT(*),SUM(return_percentage) FROM trade_logs WHERE profile_id=?",(pid,))
            stats=cursor.fetchone();total_trades=stats[0] if stats and stats[0] is not None else 0;total_return=stats[1] if stats and stats[1] is not None else 0.0
            cursor.execute("SELECT COUNT(*) FROM trade_logs WHERE profile_id=? AND return_percentage > 0",(pid,));win_row=cursor.fetchone()
            winning_trades=win_row[0] if win_row else 0
            cursor.execute("SELECT COUNT(*) FROM trade_logs WHERE profile_id=? AND return_percentage <= 0",(pid,));lose_row=cursor.fetchone()
            losing_trades=lose_row[0] if lose_row else 0
            comparison_tree.insert('',tk.END,values=(name,total_trades,winning_trades,losing_trades,f"{total_return:.2f}%"))
    except Exception as e: messagebox.showerror("DB Error",f"Comparison populate failed: {e}")
    finally:
        if conn:conn.close()

def populate_all_scanned_stocks_view(): # Same as before
    global all_scanned_stocks_tree
    if not all_scanned_stocks_tree: return
    for i in all_scanned_stocks_tree.get_children(): all_scanned_stocks_tree.delete(i)
    if hasattr(scanner,'last_raw_scan_results') and scanner.last_raw_scan_results:
        for stock_data in scanner.last_raw_scan_results:
            all_scanned_stocks_tree.insert('',tk.END,values=(stock_data.get('Company Name','N/A'),stock_data.get('Ticker Symbol','N/A'),stock_data.get('Zacks Rank','N/A'),stock_data.get('Value Score','N/A'),stock_data.get('Growth Score','N/A'),stock_data.get('Momentum Score','N/A'),stock_data.get('VGM Score','N/A'),stock_data.get('Stock Page URL','N/A')))

def refresh_all_gui_data(): refresh_selected_profile_data_display(); populate_profile_comparison_view(); populate_all_scanned_stocks_view()

def trigger_manual_scan_all_active(): # Same
    threading.Thread(target=lambda: (scanner.scan_and_update_all_active_profiles(), root_window.after(0, refresh_all_gui_data) if root_window else None), daemon=True).start()
    messagebox.showinfo("Scan Started", "Manual scan for ALL active profiles initiated.")

def hourly_scan_worker(): # Same
    global scanner_active, root_window
    try:
        conn_init,cursor_init=connect_db();create_tables(cursor_init);conn_init.commit();add_predefined_profiles(conn_init,cursor_init);conn_init.close()
    except Exception as e: print(f"BG Scanner: DB setup error: {e}. Thread stopping."); return
    print("BG Scanner: Thread started (scans ALL active profiles).")
    while scanner_active:
        try:
            scanner.scan_and_update_all_active_profiles()
            if root_window and scanner_active: root_window.after(0, refresh_all_gui_data)
        except Exception as e: print(f"[{datetime.datetime.now()}] BG Scanner: Error (ALL active): {e}")
        sleep_duration = 15 # TEST
        for i in range(max(1, sleep_duration // 5)):
            if not scanner_active: break; time.sleep(min(5, sleep_duration - (i * 5)))
    print("BG Scanner: Thread stopped.")

def on_closing(): global scanner_active, root_window; scanner_active=False; print("GUI: Closing..."); root_window.destroy() if root_window else None

# --- Main Window Creation ---
def create_main_window():
    global root_window, holdings_tree, tradelog_tree, profiles_listbox, notebook, comparison_tree, all_scanned_stocks_tree
    global total_return_label_var, total_trades_label_var, winning_trades_label_var, losing_trades_label_var # New stat vars

    root = tk.Tk(); root_window = root
    root.title("Zacks Stock Analyzer"); root.geometry("1400x950"); root.protocol("WM_DELETE_WINDOW", on_closing)
    top_controls_frame=ttk.Frame(root,padding="5"); top_controls_frame.pack(side=tk.TOP,fill=tk.X,pady=(5,0))
    profiles_frame_cont=ttk.LabelFrame(top_controls_frame,text="Investor Profiles",padding="10"); profiles_frame_cont.pack(side=tk.LEFT,padx=5,fill=tk.Y)
    prof_list_sb_frame=ttk.Frame(profiles_frame_cont); prof_list_sb_frame.pack(pady=5,expand=True,fill=tk.BOTH)
    profiles_listbox=tk.Listbox(prof_list_sb_frame,exportselection=False,height=10,width=35)
    prof_list_sb=ttk.Scrollbar(prof_list_sb_frame,orient=tk.VERTICAL,command=profiles_listbox.yview); profiles_listbox.configure(yscrollcommand=prof_list_sb.set)
    profiles_listbox.pack(side=tk.LEFT,expand=True,fill=tk.BOTH); prof_list_sb.pack(side=tk.RIGHT,fill=tk.Y)
    profiles_listbox.bind("<<ListboxSelect>>",on_profile_select)
    prof_btn_frm=ttk.Frame(profiles_frame_cont); prof_btn_frm.pack(fill=tk.X,pady=5,side=tk.BOTTOM)

    # Disable "Add New Profile" button
    add_profile_button = ttk.Button(prof_btn_frm,text="Add New",command=lambda:open_profile_editor_window(), state=tk.DISABLED)
    add_profile_button.pack(side=tk.LEFT,expand=True,fill=tk.X)
    ttk.Button(prof_btn_frm,text="Edit Notes",command=lambda:open_profile_editor_window(selected_profile_id) if selected_profile_id is not None else messagebox.showinfo("Info","Select profile to edit.")).pack(side=tk.LEFT,expand=True,fill=tk.X) # Changed "Edit" to "Edit Notes"
    # Delete button: Check if it's one of the 7 predefined before allowing delete? For now, allow.
    ttk.Button(prof_btn_frm,text="Del Profile",command=delete_selected_profile).pack(side=tk.LEFT,expand=True,fill=tk.X) # Changed "Del" to "Del Profile"

    global_actions_frame=ttk.Frame(top_controls_frame,padding="10"); global_actions_frame.pack(side=tk.LEFT,padx=5,expand=True,fill=tk.X,anchor='n')
    ttk.Button(global_actions_frame,text="Refresh All Displayed Data",command=refresh_all_gui_data).pack(pady=5,fill=tk.X)
    ttk.Button(global_actions_frame,text="Manual Scan ALL Active Profiles",command=trigger_manual_scan_all_active).pack(pady=5,fill=tk.X)

    notebook=ttk.Notebook(root); notebook.pack(expand=True,fill="both",padx=10,pady=10)
    profile_details_tab=ttk.Frame(notebook); notebook.add(profile_details_tab,text="Selected Profile View")

    # Holdings Treeview: Added "Entry Price"
    hold_frm=ttk.LabelFrame(profile_details_tab,text="Current Holdings",padding="5");hold_frm.pack(expand=True,fill=tk.BOTH,pady=5,padx=5)
    hold_cols=("Ticker","Co","Entry Time","Entry Rank","E:Price","E:V","E:G","E:M","E:VGM","Last Check","C Rank","C:V","C:G","C:M","C:VGM") # Added E:Price
    holdings_tree=ttk.Treeview(hold_frm,columns=hold_cols,show="headings")
    for col in hold_cols:
        w=150 if "Time" in col or "Check" in col else (180 if "Co"==col else (80 if "Price" in col else 65)) # Width for E:Price
        a=tk.W if "Co"==col or "Time" in col else tk.CENTER
        t=col # Use col directly for text, or format if needed
        holdings_tree.heading(col,text=t); holdings_tree.column(col,width=w,anchor=a,stretch="Co" in col)
    h_vsb=ttk.Scrollbar(hold_frm,orient="vertical",command=holdings_tree.yview);h_hsb=ttk.Scrollbar(hold_frm,orient="horizontal",command=holdings_tree.xview);holdings_tree.configure(yscrollcommand=h_vsb.set,xscrollcommand=h_hsb.set);h_vsb.pack(side=tk.RIGHT,fill=tk.Y);h_hsb.pack(side=tk.BOTTOM,fill=tk.X);holdings_tree.pack(expand=True,fill=tk.BOTH)

    bot_det_pane=ttk.PanedWindow(profile_details_tab,orient=tk.HORIZONTAL);bot_det_pane.pack(expand=True,fill=tk.BOTH,pady=5,padx=5)
    # Trade Log Treeview: Added "Entry Price", "Exit Price". "Return %" is now actual.
    trade_frm=ttk.LabelFrame(bot_det_pane,text="Trade Log",padding="5");bot_det_pane.add(trade_frm,weight=3)
    trade_cols=("Ticker","Co","Entry Time","Exit Time","E Rank","X Rank","E VGM","X VGM","E Price","X Price","Return %","Reason") # Added E Price, X Price
    tradelog_tree=ttk.Treeview(trade_frm,columns=trade_cols,show="headings")
    for col in trade_cols:
        w=140 if "Time" in col else (180 if "Co"==col else (100 if "Reason"==col else (70 if "Price" in col or "Rank" in col or "VGM" in col or "Return" in col else 70)))
        a=tk.W if "Co"==col or "Time" in col or "Reason"==col else tk.CENTER
        tradelog_tree.heading(col,text=col);tradelog_tree.column(col,width=w,anchor=a,stretch="Co" in col or "Reason" in col)
    tl_vsb=ttk.Scrollbar(trade_frm,orient="vertical",command=tradelog_tree.yview);tl_hsb=ttk.Scrollbar(trade_frm,orient="horizontal",command=tradelog_tree.xview);tradelog_tree.configure(yscrollcommand=tl_vsb.set,xscrollcommand=tl_hsb.set);tl_vsb.pack(side=tk.RIGHT,fill=tk.Y);tl_hsb.pack(side=tk.BOTTOM,fill=tk.X);tradelog_tree.pack(expand=True,fill=tk.BOTH)

    # Statistics Frame: Updated labels
    stats_frm=ttk.LabelFrame(bot_det_pane,text="Statistics",padding="5");bot_det_pane.add(stats_frm,weight=1)
    total_return_label_var=tk.StringVar(value="Sum of Returns: N/A") # Removed (Placeholder)
    total_trades_label_var=tk.StringVar(value="Total Trades: 0")
    winning_trades_label_var=tk.StringVar(value="Winning Trades: N/A") # New
    losing_trades_label_var=tk.StringVar(value="Losing Trades: N/A")   # New
    ttk.Label(stats_frm,textvariable=total_trades_label_var).pack(pady=2,anchor=tk.W)
    ttk.Label(stats_frm,textvariable=winning_trades_label_var).pack(pady=2,anchor=tk.W)
    ttk.Label(stats_frm,textvariable=losing_trades_label_var).pack(pady=2,anchor=tk.W)
    ttk.Label(stats_frm,textvariable=total_return_label_var).pack(pady=2,anchor=tk.W)
    # Info label about placeholder returns is still relevant if actual prices are not always available for calculation
    ttk.Label(stats_frm,text="Note: Return % based on available price data at trade time.",font=('Helvetica',8,'italic')).pack(pady=(5,0),anchor=tk.W)


    comparison_tab=ttk.Frame(notebook);notebook.add(comparison_tab,text="Profile Comparison")
    comp_frm=ttk.LabelFrame(comparison_tab,text="Overall Profile Performance Comparison",padding="10");comp_frm.pack(expand=True,fill=tk.BOTH,padx=10,pady=10)
    # Profile Comparison: Updated column text
    comp_cols=("Profile Name","Total Trades","Winning Trades","Losing Trades","Total Return %");comparison_tree=ttk.Treeview(comp_frm,columns=comp_cols,show="headings")
    for col in comp_cols:w=250 if "Name" in col else 150;comparison_tree.heading(col,text=col.replace(" (Placeholder)",""));comparison_tree.column(col,width=w,anchor=tk.W if "Name" in col else tk.CENTER,stretch="Name" in col)
    comp_vsb=ttk.Scrollbar(comp_frm,orient="vertical",command=comparison_tree.yview);comp_hsb=ttk.Scrollbar(comp_frm,orient="horizontal",command=comparison_tree.xview);comparison_tree.configure(yscrollcommand=comp_vsb.set,xscrollcommand=comp_hsb.set);comp_vsb.pack(side=tk.RIGHT,fill=tk.Y);comp_hsb.pack(side=tk.BOTTOM,fill=tk.X);comparison_tree.pack(expand=True,fill=tk.BOTH)

    all_scanned_tab_frame = ttk.Frame(notebook); notebook.add(all_scanned_tab_frame, text="All Scanned Stocks")
    scanned_stocks_lf=ttk.LabelFrame(all_scanned_tab_frame,text="Results from Last Market Scan",padding="10");scanned_stocks_lf.pack(expand=True,fill=tk.BOTH,padx=10,pady=10)
    scanned_cols=("Company Name","Ticker","Zacks Rank","Value","Growth","Momentum","VGM","Stock Page URL");all_scanned_stocks_tree=ttk.Treeview(scanned_stocks_lf,columns=scanned_cols,show="headings")
    for col_name in scanned_cols:
        col_w=250 if "Company" in col_name else(300 if "URL" in col_name else 100);col_a=tk.W if "Company" in col_name or "URL" in col_name else tk.CENTER
        all_scanned_stocks_tree.heading(col_name,text=col_name);all_scanned_stocks_tree.column(col_name,width=col_w,anchor=col_a,stretch=tk.YES if "Company" in col_name or "URL" in col_name else tk.NO)
    sc_vsb=ttk.Scrollbar(scanned_stocks_lf,orient="vertical",command=all_scanned_stocks_tree.yview);sc_hsb=ttk.Scrollbar(scanned_stocks_lf,orient="horizontal",command=all_scanned_stocks_tree.xview);all_scanned_stocks_tree.configure(yscrollcommand=sc_vsb.set,xscrollcommand=sc_hsb.set);sc_vsb.pack(side=tk.RIGHT,fill=tk.Y);sc_hsb.pack(side=tk.BOTTOM,fill=tk.X);all_scanned_stocks_tree.pack(expand=True,fill=tk.BOTH)

    load_profiles_into_listbox(); refresh_all_gui_data()
    root.mainloop()

if __name__ == "__main__":
    print("Main: Init app & scanner thread..."); scan_thread = threading.Thread(target=hourly_scan_worker, daemon=True); scan_thread.start()
    create_main_window()
    print("Main: GUI closed."); scanner_active = False; print("Main: Exiting.")
