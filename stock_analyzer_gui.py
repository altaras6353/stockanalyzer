import tkinter as tk
from tkinter import ttk
from tkinter import simpledialog, messagebox
import datetime
import threading
import time
import sqlite3

import scanner # scanner.py now has scan_and_update_all_active_profiles and last_raw_scan_results
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
# For "All Scanned Stocks" tab
all_scanned_stocks_tree = None # New Treeview
# For Notebook
notebook = None

scanner_active = True

# --- Profile Management Functions (largely same as Subtask 13) ---
def load_profiles_into_listbox():
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
        if root_window: root_window.after(0, populate_profile_comparison_view)
    except Exception as e: messagebox.showerror("DB Error", f"Failed to load profiles: {e}")
    finally:
        if conn: conn.close()

def on_profile_select(event):
    global selected_profile_id, profiles_listbox, profile_id_map
    if not profiles_listbox or not profiles_listbox.curselection():
        selected_profile_id = None; refresh_selected_profile_data_display(); return
    selected_profile_id = profile_id_map.get(profiles_listbox.curselection()[0])
    refresh_selected_profile_data_display()

def get_profile_data_from_db(profile_id_to_fetch):
    if profile_id_to_fetch is None: return None
    conn, cursor = None, None
    try:
        conn, cursor = connect_db()
        cursor.execute("SELECT profile_id, name, description, is_active FROM investor_profiles WHERE profile_id = ?", (profile_id_to_fetch,))
        profile_main_data = cursor.fetchone()
        if not profile_main_data: return None
        cursor.execute("SELECT category, condition, value1, value2 FROM profile_rules WHERE profile_id = ?", (profile_id_to_fetch,))
        rules_data = cursor.fetchall()
        return {'main': profile_main_data, 'rules': rules_data}
    except Exception as e: messagebox.showerror("DB Error", f"Failed to fetch profile data: {e}"); return None
    finally:
        if conn: conn.close()

def open_profile_editor_window(profile_id_to_edit=None): # Uses structured rule editor
    global root_window
    full_profile_data = get_profile_data_from_db(profile_id_to_edit) if profile_id_to_edit else None
    existing_main_data = full_profile_data['main'] if full_profile_data else None
    existing_rules_data = full_profile_data['rules'] if full_profile_data else []
    if profile_id_to_edit and not existing_main_data: messagebox.showerror("Error", "Could not load profile data."); return

    editor_win = tk.Toplevel(root_window); editor_win.title("Edit Profile" if existing_main_data else "Add New Profile")
    editor_win.geometry("600x700"); editor_win.transient(root_window); editor_win.grab_set()
    main_info_frame = ttk.LabelFrame(editor_win, text="Profile Identity", padding="10"); main_info_frame.pack(pady=10, padx=10, fill=tk.X)
    ttk.Label(main_info_frame, text="Profile Name:").grid(row=0, column=0, sticky=tk.W, pady=2)
    name_var = tk.StringVar(value=existing_main_data[1] if existing_main_data else ""); name_entry = ttk.Entry(main_info_frame, textvariable=name_var, width=60); name_entry.grid(row=0, column=1, sticky=tk.EW, pady=2)
    is_active_var = tk.BooleanVar(value=bool(existing_main_data[3]) if existing_main_data else True); active_check = ttk.Checkbutton(main_info_frame, text="Is Active Profile", variable=is_active_var); active_check.grid(row=0, column=2, sticky=tk.W, padx=5, pady=2); main_info_frame.columnconfigure(1, weight=1)
    ttk.Label(main_info_frame, text="Notes (Optional):").grid(row=1, column=0, sticky=tk.NW, pady=2); desc_text_notes = tk.Text(main_info_frame, height=3, width=60, wrap=tk.WORD); desc_text_notes.grid(row=1, column=1, columnspan=2, sticky=tk.EW, pady=2)
    if existing_main_data and existing_main_data[2]: desc_text_notes.insert(tk.END, existing_main_data[2])
    zacks_rank_frame = ttk.LabelFrame(editor_win, text="Zacks Rank Criteria", padding="10"); zacks_rank_frame.pack(pady=10, padx=10, fill=tk.X)
    zacks_rank_vars = {rank: tk.BooleanVar() for rank in range(1, 6)}
    for i, rank_text in enumerate(["1 (Strong Buy)", "2 (Buy)", "3 (Hold)", "4 (Sell)", "5 (Strong Sell)"]): ttk.Checkbutton(zacks_rank_frame, text=rank_text, variable=zacks_rank_vars[i+1]).pack(side=tk.LEFT, padx=5)
    style_scores_frame = ttk.LabelFrame(editor_win, text="Individual Style Scores ('Any' to ignore)", padding="10"); style_scores_frame.pack(pady=10, padx=10, fill=tk.X)
    style_score_names = ['Value', 'Growth', 'Momentum', 'VGM']; style_score_vars = {name: tk.StringVar(value="Any") for name in style_score_names}; combo_opts = ["Any", "A", "B", "C", "D", "F"]
    for i, name in enumerate(style_score_names): ttk.Label(style_scores_frame, text=f"{name} Score:").grid(row=i,column=0,sticky=tk.W,padx=5,pady=2); ttk.Combobox(style_scores_frame,textvariable=style_score_vars[name],values=combo_opts,state="readonly",width=10).grid(row=i,column=1,sticky=tk.EW,padx=5,pady=2)
    style_scores_frame.columnconfigure(1, weight=1)
    style_pattern_frame = ttk.LabelFrame(editor_win, text="Overall Style Score Pattern (Overrides individual)", padding="10"); style_pattern_frame.pack(pady=10, padx=10, fill=tk.X)
    pattern_var = tk.StringVar(value="Any"); pattern_opts = ["Any", "All A (AAAA)", "Max 1 B (AAAB)"]
    ttk.Label(style_pattern_frame, text="Pattern:").pack(side=tk.LEFT, padx=5); ttk.Combobox(style_pattern_frame, textvariable=pattern_var, values=pattern_opts, state="readonly", width=20).pack(side=tk.LEFT, padx=5)
    if existing_rules_data:
        for cat, cond, v1, _ in existing_rules_data:
            if cat=='ZACKS_RANK' and cond=='IN_LIST' and v1: [zacks_rank_vars[int(r)].set(True) for r in v1.split(',') if r.isdigit() and int(r) in zacks_rank_vars]
            elif cat.startswith('STYLE_SCORE_') and cond=='EQUALS': score_type=cat.split('_')[-1].capitalize(); style_score_vars[score_type].set(v1 or "Any")
            elif cat=='STYLE_SCORE_PATTERN' and cond=='MATCHES_PATTERN': pattern_var.set({"AAAA":"All A (AAAA)","AAAB":"Max 1 B (AAAB)"}.get(v1, "Any"))
    def save_profile_and_rules():
        name=name_var.get().strip(); notes=desc_text_notes.get("1.0",tk.END).strip(); is_active=1 if is_active_var.get() else 0
        if not name: messagebox.showerror("Validation Error","Name empty.",parent=editor_win); return
        conn,cursor=None,None
        try:
            conn,cursor=connect_db(); current_pid=profile_id_to_edit
            if current_pid is None: cursor.execute("INSERT INTO investor_profiles(name,description,is_active)VALUES(?,?,?)",(name,notes,is_active)); current_pid=cursor.lastrowid
            else: cursor.execute("UPDATE investor_profiles SET name=?,description=?,is_active=? WHERE profile_id=?",(name,notes,is_active,current_pid))
            cursor.execute("DELETE FROM profile_rules WHERE profile_id=?",(current_pid,))
            sel_ranks=[str(r) for r,v in zacks_rank_vars.items() if v.get()]
            if sel_ranks: cursor.execute("INSERT INTO profile_rules(profile_id,category,condition,value1)VALUES(?,?,?,?)",(current_pid,'ZACKS_RANK','IN_LIST',",".join(sel_ranks)))
            pat_disp=pattern_var.get(); pat_val={"All A (AAAA)":'AAAA',"Max 1 B (AAAB)":'AAAB'}.get(pat_disp)
            if pat_val: cursor.execute("INSERT INTO profile_rules(profile_id,category,condition,value1)VALUES(?,?,?,?)",(current_pid,'STYLE_SCORE_PATTERN','MATCHES_PATTERN',pat_val))
            else: [cursor.execute("INSERT INTO profile_rules(profile_id,category,condition,value1)VALUES(?,?,?,?)",(current_pid,f"STYLE_SCORE_{s_name.upper()}",'EQUALS',s_val)) for s_name,s_var in style_score_vars.items() if (s_val:=s_var.get())!="Any"]
            conn.commit(); messagebox.showinfo("Success","Profile saved.",parent=editor_win); load_profiles_into_listbox(); editor_win.destroy()
        except sqlite3.IntegrityError: messagebox.showerror("DB Error",f"Profile name '{name}' exists.",parent=editor_win)
        except Exception as e: messagebox.showerror("DB Error",f"Save failed: {e}",parent=editor_win)
        finally:
            if conn:conn.close()
    btn_frm_edit=ttk.Frame(editor_win);btn_frm_edit.pack(pady=10,fill=tk.X,side=tk.BOTTOM);ttk.Button(btn_frm_edit,text="Save",command=save_profile_and_rules).pack(side=tk.RIGHT,padx=10);ttk.Button(btn_frm_edit,text="Cancel",command=editor_win.destroy).pack(side=tk.RIGHT);name_entry.focus_set()

def delete_selected_profile():
    global selected_profile_id
    if selected_profile_id is None: messagebox.showwarning("Selection Error","No profile selected."); return
    profile_data = get_profile_data_from_db(selected_profile_id)
    if not profile_data or not profile_data['main'] or not messagebox.askyesno("Confirm Delete",f"Delete profile '{profile_data['main'][1]}'?\nAssociated data (rules, holdings, logs) will be deleted."): return
    conn,cursor=None,None
    try:
        conn,cursor=connect_db(); cursor.execute("DELETE FROM investor_profiles WHERE profile_id=?",(selected_profile_id,)); conn.commit() # ON DELETE CASCADE handles related tables
        messagebox.showinfo("Success",f"Profile '{profile_data['main'][1]}' deleted.")
        load_profiles_into_listbox();selected_profile_id=None;refresh_selected_profile_data_display()
    except Exception as e: messagebox.showerror("DB Error",f"Delete failed: {e}")
    finally:
        if conn:conn.close()

# --- Refresh Data Display Functions ---
def refresh_selected_profile_data_display():
    global holdings_tree,tradelog_tree,total_return_label_var,total_trades_label_var,selected_profile_id,root_window
    profile_name="None Selected"; did_fetch_profile_data=False
    if selected_profile_id:
        profile_data=get_profile_data_from_db(selected_profile_id)
        if profile_data and profile_data['main']: profile_name=profile_data['main'][1]; did_fetch_profile_data=True
    if root_window:root_window.title(f"Zacks Stock Analyzer - Profile: {profile_name}")
    if not holdings_tree or not tradelog_tree: return
    for i in holdings_tree.get_children(): holdings_tree.delete(i)
    for i in tradelog_tree.get_children(): tradelog_tree.delete(i)
    if total_trades_label_var:total_trades_label_var.set("Total Trades: N/A")
    if total_return_label_var:total_return_label_var.set("Sum of Return % (Placeholder): N/A")
    if selected_profile_id is None or not did_fetch_profile_data: return
    conn,cursor=None,None
    try:
        conn,cursor=connect_db()
        h_q="SELECT ticker,company_name,entry_timestamp,entry_zacks_rank,entry_style_value,entry_style_growth,entry_style_momentum,entry_style_vgm,last_checked_timestamp,current_zacks_rank,current_style_value,current_style_growth,current_style_momentum,current_style_vgm FROM stock_holdings WHERE profile_id=? ORDER BY entry_timestamp DESC"
        cursor.execute(h_q,(selected_profile_id,));[holdings_tree.insert('',tk.END,values=r) for r in cursor.fetchall()]
        tl_q="SELECT ticker,company_name,entry_timestamp,exit_timestamp,entry_zacks_rank,exit_zacks_rank,entry_style_vgm,exit_style_vgm,return_percentage,reason_for_exit FROM trade_logs WHERE profile_id=? ORDER BY exit_timestamp DESC"
        cursor.execute(tl_q,(selected_profile_id,));[tradelog_tree.insert('',tk.END,values=r) for r in cursor.fetchall()]
        cursor.execute("SELECT COUNT(*),SUM(return_percentage) FROM trade_logs WHERE profile_id=?",(selected_profile_id,));stats=cursor.fetchone()
        trades=stats[0] if stats and stats[0] is not None else 0; ret=stats[1] if stats and stats[1] is not None else 0.0
        if total_trades_label_var:total_trades_label_var.set(f"Total Trades: {trades}")
        if total_return_label_var:total_return_label_var.set(f"Sum of Return % (Placeholder): {ret:.2f}%")
    except Exception as e:messagebox.showerror("DB Error",f"Refresh failed: {e}")
    finally:
        if conn:conn.close()

def populate_profile_comparison_view():
    global comparison_tree
    if not comparison_tree: return
    for i in comparison_tree.get_children(): comparison_tree.delete(i)
    conn,cursor=None,None
    try:
        conn,cursor=connect_db();cursor.execute("SELECT profile_id,name FROM investor_profiles ORDER BY name ASC")
        for pid,name in cursor.fetchall():
            cursor.execute("SELECT COUNT(*),SUM(return_percentage) FROM trade_logs WHERE profile_id=?",(pid,))
            stats=cursor.fetchone();trades=stats[0] if stats and stats[0] is not None else 0;ret=stats[1] if stats and stats[1] is not None else 0.0
            comparison_tree.insert('',tk.END,values=(name,trades,"N/A","N/A",f"{ret:.2f}%"))
    except Exception as e:messagebox.showerror("DB Error",f"Comparison populate failed: {e}")
    finally:
        if conn:conn.close()

def populate_all_scanned_stocks_view(): # New function
    global all_scanned_stocks_tree
    if not all_scanned_stocks_tree: print("GUI Error: all_scanned_stocks_tree not initialized."); return
    print("GUI: Populating 'All Scanned Stocks' view...")
    for i in all_scanned_stocks_tree.get_children(): all_scanned_stocks_tree.delete(i)

    # Access the global list from scanner module
    # Ensure scanner module is imported as `import scanner`
    if hasattr(scanner, 'last_raw_scan_results') and scanner.last_raw_scan_results:
        print(f"GUI: Found {len(scanner.last_raw_scan_results)} items in scanner.last_raw_scan_results.")
        for stock_data in scanner.last_raw_scan_results:
            values_to_insert = (
                stock_data.get('Company Name', 'N/A'),
                stock_data.get('Ticker Symbol', 'N/A'),
                stock_data.get('Zacks Rank', 'N/A'),
                stock_data.get('Value Score', 'N/A'),
                stock_data.get('Growth Score', 'N/A'),
                stock_data.get('Momentum Score', 'N/A'),
                stock_data.get('VGM Score', 'N/A'),
                stock_data.get('Stock Page URL', 'N/A')
            )
            all_scanned_stocks_tree.insert('', tk.END, values=values_to_insert)
        print(f"GUI: 'All Scanned Stocks' Tree populated with {len(all_scanned_stocks_tree.get_children())} items.")
    else:
        print("GUI: No data in scanner.last_raw_scan_results to display or scanner module/variable not found.")


def refresh_all_gui_data():
    refresh_selected_profile_data_display()
    populate_profile_comparison_view()
    populate_all_scanned_stocks_view() # Add call to new function

# --- Scan Triggers & Background Worker ---
def trigger_manual_scan_all_active():
    threading.Thread(target=lambda: (scanner.scan_and_update_all_active_profiles(), root_window.after(0, refresh_all_gui_data) if root_window else None), daemon=True).start()
    messagebox.showinfo("Scan Started", "Manual scan for ALL active profiles initiated.")

def hourly_scan_worker():
    global scanner_active, root_window
    try:
        conn_init,cursor_init=connect_db();create_tables(cursor_init);conn_init.commit();add_initial_profile(conn_init,cursor_init);conn_init.close()
    except Exception as e: print(f"BG Scanner: DB setup error: {e}. Thread stopping."); return
    print("BG Scanner: Thread started (scans ALL active profiles).")
    while scanner_active:
        try:
            scanner.scan_and_update_all_active_profiles()
            if root_window and scanner_active: root_window.after(0, refresh_all_gui_data)
        except Exception as e: print(f"[{datetime.datetime.now()}] BG Scanner: Error (ALL active): {e}")
        sleep_duration = 15 # TEST
        print(f"[{datetime.datetime.now()}] BG Scanner: Next scan in {sleep_duration}s.")
        for i in range(max(1, sleep_duration // 5)):
            if not scanner_active: break; time.sleep(min(5, sleep_duration - (i * 5)))
    print("BG Scanner: Thread stopped.")

def on_closing(): global scanner_active, root_window; scanner_active=False; print("GUI: Closing..."); root_window.destroy() if root_window else None

# --- Main Window Creation ---
def create_main_window():
    global root_window, holdings_tree, tradelog_tree, profiles_listbox, notebook, comparison_tree, all_scanned_stocks_tree
    global total_return_label_var, total_trades_label_var
    root = tk.Tk(); root_window = root
    root.title("Zacks Stock Analyzer"); root.geometry("1400x950"); root.protocol("WM_DELETE_WINDOW", on_closing) # Wider for new tab
    top_controls_frame=ttk.Frame(root,padding="5"); top_controls_frame.pack(side=tk.TOP,fill=tk.X,pady=(5,0))
    profiles_frame_cont=ttk.LabelFrame(top_controls_frame,text="Investor Profiles",padding="10"); profiles_frame_cont.pack(side=tk.LEFT,padx=5,fill=tk.Y)
    prof_list_sb_frame=ttk.Frame(profiles_frame_cont); prof_list_sb_frame.pack(pady=5,expand=True,fill=tk.BOTH)
    profiles_listbox=tk.Listbox(prof_list_sb_frame,exportselection=False,height=10,width=35)
    prof_list_sb=ttk.Scrollbar(prof_list_sb_frame,orient=tk.VERTICAL,command=profiles_listbox.yview); profiles_listbox.configure(yscrollcommand=prof_list_sb.set)
    profiles_listbox.pack(side=tk.LEFT,expand=True,fill=tk.BOTH); prof_list_sb.pack(side=tk.RIGHT,fill=tk.Y)
    profiles_listbox.bind("<<ListboxSelect>>",on_profile_select)
    prof_btn_frm=ttk.Frame(profiles_frame_cont); prof_btn_frm.pack(fill=tk.X,pady=5,side=tk.BOTTOM)
    ttk.Button(prof_btn_frm,text="Add",command=lambda:open_profile_editor_window()).pack(side=tk.LEFT,expand=True,fill=tk.X)
    ttk.Button(prof_btn_frm,text="Edit",command=lambda:open_profile_editor_window(selected_profile_id) if selected_profile_id is not None else messagebox.showinfo("Info","Select profile to edit.")).pack(side=tk.LEFT,expand=True,fill=tk.X)
    ttk.Button(prof_btn_frm,text="Del",command=delete_selected_profile).pack(side=tk.LEFT,expand=True,fill=tk.X)
    global_actions_frame=ttk.Frame(top_controls_frame,padding="10"); global_actions_frame.pack(side=tk.LEFT,padx=5,expand=True,fill=tk.X,anchor='n')
    ttk.Button(global_actions_frame,text="Refresh All Displayed Data",command=refresh_all_gui_data).pack(pady=5,fill=tk.X)
    ttk.Button(global_actions_frame,text="Manual Scan ALL Active Profiles",command=trigger_manual_scan_all_active).pack(pady=5,fill=tk.X)

    notebook=ttk.Notebook(root); notebook.pack(expand=True,fill="both",padx=10,pady=10)
    profile_details_tab=ttk.Frame(notebook); notebook.add(profile_details_tab,text="Selected Profile View")
    # ... (Selected Profile View tab contents: holdings_tree, tradelog_tree, stats_frm - layout unchanged from Subtask 13) ...
    hold_frm=ttk.LabelFrame(profile_details_tab,text="Current Holdings",padding="5");hold_frm.pack(expand=True,fill=tk.BOTH,pady=5,padx=5)
    hold_cols=("Ticker","Co","Entry Time","E Rank","E:V","E:G","E:M","E:VGM","Last Check","C Rank","C:V","C:G","C:M","C:VGM");holdings_tree=ttk.Treeview(hold_frm,columns=hold_cols,show="headings")
    for col in hold_cols:w=150 if "Time" in col or "Check" in col else(180 if "Co"==col else 65);holdings_tree.heading(col,text=col);holdings_tree.column(col,width=w,anchor=tk.W if "Co"==col or "Time" in col else tk.CENTER,stretch="Co" in col)
    h_vsb=ttk.Scrollbar(hold_frm,orient="vertical",command=holdings_tree.yview);h_hsb=ttk.Scrollbar(hold_frm,orient="horizontal",command=holdings_tree.xview);holdings_tree.configure(yscrollcommand=h_vsb.set,xscrollcommand=h_hsb.set);h_vsb.pack(side=tk.RIGHT,fill=tk.Y);h_hsb.pack(side=tk.BOTTOM,fill=tk.X);holdings_tree.pack(expand=True,fill=tk.BOTH)
    bot_det_pane=ttk.PanedWindow(profile_details_tab,orient=tk.HORIZONTAL);bot_det_pane.pack(expand=True,fill=tk.BOTH,pady=5,padx=5)
    trade_frm=ttk.LabelFrame(bot_det_pane,text="Trade Log",padding="5");bot_det_pane.add(trade_frm,weight=3)
    trade_cols=("Ticker","Co","Entry Time","Exit Time","E Rank","X Rank","E VGM","X VGM","Return %","Reason");tradelog_tree=ttk.Treeview(trade_frm,columns=trade_cols,show="headings")
    for col in trade_cols:w=140 if "Time" in col else(180 if "Co"==col else(100 if "Reason"==col else 70));tradelog_tree.heading(col,text=col);tradelog_tree.column(col,width=w,anchor=tk.W if "Co"==col or "Time" in col or "Reason"==col else tk.CENTER,stretch="Co" in col or "Reason" in col)
    tl_vsb=ttk.Scrollbar(trade_frm,orient="vertical",command=tradelog_tree.yview);tl_hsb=ttk.Scrollbar(trade_frm,orient="horizontal",command=tradelog_tree.xview);tradelog_tree.configure(yscrollcommand=tl_vsb.set,xscrollcommand=tl_hsb.set);tl_vsb.pack(side=tk.RIGHT,fill=tk.Y);tl_hsb.pack(side=tk.BOTTOM,fill=tk.X);tradelog_tree.pack(expand=True,fill=tk.BOTH)
    stats_frm=ttk.LabelFrame(bot_det_pane,text="Statistics",padding="5");bot_det_pane.add(stats_frm,weight=1)
    total_return_label_var=tk.StringVar(value="Sum Return % (Placeholder): N/A");total_trades_label_var=tk.StringVar(value="Total Trades: 0")
    ttk.Label(stats_frm,textvariable=total_return_label_var).pack(pady=5,anchor=tk.W);ttk.Label(stats_frm,textvariable=total_trades_label_var).pack(pady=5,anchor=tk.W)
    ttk.Label(stats_frm,text="Note: Return % is a placeholder.",font=('Helvetica',8,'italic')).pack(pady=(0,5),anchor=tk.W)

    comparison_tab=ttk.Frame(notebook);notebook.add(comparison_tab,text="Profile Comparison")
    comp_frm=ttk.LabelFrame(comparison_tab,text="Overall Profile Performance Comparison",padding="10");comp_frm.pack(expand=True,fill=tk.BOTH,padx=10,pady=10)
    comp_cols=("Profile Name","Total Trades","Winning Trades","Losing Trades","Total Return % (Placeholder)");comparison_tree=ttk.Treeview(comp_frm,columns=comp_cols,show="headings")
    for col in comp_cols:w=250 if "Name" in col else 150;comparison_tree.heading(col,text=col);comparison_tree.column(col,width=w,anchor=tk.W if "Name" in col else tk.CENTER,stretch="Name" in col)
    comp_vsb=ttk.Scrollbar(comp_frm,orient="vertical",command=comparison_tree.yview);comp_hsb=ttk.Scrollbar(comp_frm,orient="horizontal",command=comparison_tree.xview);comparison_tree.configure(yscrollcommand=comp_vsb.set,xscrollcommand=comp_hsb.set);comp_vsb.pack(side=tk.RIGHT,fill=tk.Y);comp_hsb.pack(side=tk.BOTTOM,fill=tk.X);comparison_tree.pack(expand=True,fill=tk.BOTH)

    # Tab 3: All Scanned Stocks (New)
    all_scanned_tab_frame = ttk.Frame(notebook)
    notebook.add(all_scanned_tab_frame, text="All Scanned Stocks")
    scanned_stocks_lf = ttk.LabelFrame(all_scanned_tab_frame, text="Results from Last Market Scan", padding="10")
    scanned_stocks_lf.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)
    scanned_cols = ("Company Name", "Ticker", "Zacks Rank", "Value", "Growth", "Momentum", "VGM", "Stock Page URL")
    all_scanned_stocks_tree = ttk.Treeview(scanned_stocks_lf, columns=scanned_cols, show="headings")
    for col_name in scanned_cols:
        col_width = 250 if "Company" in col_name else (300 if "URL" in col_name else 100)
        col_anchor = tk.W if "Company" in col_name or "URL" in col_name else tk.CENTER
        all_scanned_stocks_tree.heading(col_name, text=col_name)
        all_scanned_stocks_tree.column(col_name, width=col_width, anchor=col_anchor, stretch=tk.YES if "Company" in col_name or "URL" in col_name else tk.NO)
    sc_vsb = ttk.Scrollbar(scanned_stocks_lf, orient="vertical", command=all_scanned_stocks_tree.yview)
    sc_hsb = ttk.Scrollbar(scanned_stocks_lf, orient="horizontal", command=all_scanned_stocks_tree.xview)
    all_scanned_stocks_tree.configure(yscrollcommand=sc_vsb.set, xscrollcommand=sc_hsb.set)
    sc_vsb.pack(side=tk.RIGHT, fill=tk.Y); sc_hsb.pack(side=tk.BOTTOM, fill=tk.X)
    all_scanned_stocks_tree.pack(expand=True, fill=tk.BOTH)

    load_profiles_into_listbox(); refresh_all_gui_data() # Initial loads (now calls all three refresh/populate funcs)
    root.mainloop()

if __name__ == "__main__":
    print("Main: Init app & scanner thread..."); scan_thread = threading.Thread(target=hourly_scan_worker, daemon=True); scan_thread.start()
    create_main_window()
    print("Main: GUI closed."); scanner_active = False; print("Main: Exiting.")
