import tkinter as tk
from tkinter import ttk
from tkinter import simpledialog, messagebox
import datetime
from datetime import timedelta
import threading
import time
import sqlite3
import requests

import scanner
from parse_stock_page import extract_stock_ratings
from price_fetcher import get_current_price
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
manual_entry_button = None
delete_holding_button = None
delete_tradelog_button = None
scanner_active = True
next_scan_time_var = None

# --- GUI Helper, Command, Event Handler, and Worker Functions ---

def get_profile_rules_display_text(profile_type: str | None) -> dict:
    buy_rule = "Entry: Zacks Rank '1' AND (Style Scores: All 'A' OR Max 1 'B' with rest 'A')."
    sell_rule = "N/A"
    if profile_type == "Cautious": sell_rule = "Exit: Zacks Rank is no longer '1' OR Calculated Score > 4 OR Score is invalid."
    elif profile_type == "Hesitant": sell_rule = "Exit: Zacks Rank is no longer '1' OR Calculated Score > 5 OR Score is invalid."
    elif profile_type == "Brave": sell_rule = "Exit: Zacks Rank is no longer '1' OR Calculated Score > 6 OR Score is invalid."
    elif profile_type == "Reckless": sell_rule = "Exit: Zacks Rank is no longer '1' OR Calculated Score > 7 OR Score is invalid."
    elif profile_type == "Greedy2Pct": sell_rule = "Exit: (Zacks Rank is no longer '1' OR Calculated Score > 4 OR Score is invalid) OR Profit >= 2%."
    elif profile_type == "Greedy3Pct": sell_rule = "Exit: (Zacks Rank is no longer '1' OR Calculated Score > 4 OR Score is invalid) OR Profit >= 3%."
    elif profile_type == "Greedy4Pct": sell_rule = "Exit: (Zacks Rank is no longer '1' OR Calculated Score > 5 OR Score is invalid) OR Profit >= 4%."
    elif profile_type is None or profile_type == "N/A (Custom)": buy_rule = "Entry: Rules not predefined."; sell_rule = "Exit: Rules not predefined."
    return {'buy': buy_rule, 'sell': sell_rule}

def get_profile_data_for_display(pid):
    if pid is None: return None; conn,cur=None,None
    try: conn,cur=connect_db(); cur.execute("SELECT profile_id,name,description,is_active,profile_type FROM investor_profiles WHERE profile_id=?",(pid,)); return cur.fetchone()
    except Exception as e: messagebox.showerror("DB Error",f"Fetch profile failed: {e}"); return None
    finally:
        if conn:conn.close()

def refresh_selected_profile_data_display():
    global holdings_tree,tradelog_tree,total_return_label_var,total_trades_label_var,selected_profile_id,root_window,winning_trades_label_var,losing_trades_label_var,buy_rule_text_var,sell_rule_text_var,manual_entry_button, delete_holding_button, delete_tradelog_button
    p_name="None";p_type=None
    if selected_profile_id: p_row=get_profile_data_for_display(selected_profile_id); p_name=p_row['name'] if p_row else "Error"; p_type=p_row['profile_type'] if p_row else None
    if root_window:root_window.title(f"Analyzer - Profile: {p_name}")
    rules_txt=get_profile_rules_display_text(p_type);buy_rule_text_var.set(rules_txt.get('buy','N/A')) if buy_rule_text_var else None;sell_rule_text_var.set(rules_txt.get('sell','N/A')) if sell_rule_text_var else None
    if not holdings_tree or not tradelog_tree: return
    for i in holdings_tree.get_children():holdings_tree.delete(i)
    for i in tradelog_tree.get_children():tradelog_tree.delete(i)
    if total_trades_label_var:total_trades_label_var.set("Trades: N/A")
    if total_return_label_var:total_return_label_var.set("Return: N/A")
    if winning_trades_label_var:winning_trades_label_var.set("Won: N/A")
    if losing_trades_label_var:losing_trades_label_var.set("Lost: N/A")
    if manual_entry_button:manual_entry_button.config(state=tk.NORMAL if selected_profile_id is not None else tk.DISABLED)
    if delete_holding_button: delete_holding_button.config(state=tk.DISABLED)
    if delete_tradelog_button: delete_tradelog_button.config(state=tk.DISABLED)
    if selected_profile_id is None: return
    conn,cur=None,None
    try:
        conn,cur=connect_db()
        h_q="SELECT ticker,company_name,entry_timestamp,entry_zacks_rank,entry_style_value,entry_style_growth,entry_style_momentum,entry_style_vgm,entry_price,last_checked_timestamp,current_zacks_rank,current_style_value,current_style_growth,current_style_momentum,current_style_vgm FROM stock_holdings WHERE profile_id=? ORDER BY entry_timestamp DESC"
        h_rows=cur.execute(h_q,(selected_profile_id,)).fetchall()
        for r_data in h_rows:
            def get_val(r,k,d="N/A"):
                try: v=r[k]; return v if v is not None else d
                except(IndexError,KeyError): return d
            ep_val=f"{get_val(r_data,'entry_price',0.0):.2f}" if isinstance(get_val(r_data,'entry_price',None),(int,float)) else "N/A"
            v_tup=(str(get_val(r_data,'ticker')),str(get_val(r_data,'company_name')),str(get_val(r_data,'entry_timestamp')),str(get_val(r_data,'entry_zacks_rank')),ep_val,str(get_val(r_data,'entry_style_value')),str(get_val(r_data,'entry_style_growth')),str(get_val(r_data,'entry_style_momentum')),str(get_val(r_data,'entry_style_vgm')),str(get_val(r_data,'last_checked_timestamp')),str(get_val(r_data,'current_zacks_rank')),str(get_val(r_data,'current_style_value')),str(get_val(r_data,'current_style_growth')),str(get_val(r_data,'current_style_momentum')),str(get_val(r_data,'current_style_vgm')))
            holdings_tree.insert('',tk.END,values=v_tup)
        tl_q="SELECT trade_id, ticker,company_name,entry_timestamp,exit_timestamp,entry_zacks_rank,exit_zacks_rank,entry_style_vgm,exit_style_vgm,entry_price,exit_price,return_percentage,reason_for_exit FROM trade_logs WHERE profile_id=? ORDER BY exit_timestamp DESC"
        tl_rows=cur.execute(tl_q,(selected_profile_id,)).fetchall()
        for r_data in tl_rows:
            def get_val_tl(r,k,d="N/A"):
                try: v=r[k]; return v if v is not None else d
                except(IndexError,KeyError): return d
            trade_id_for_iid = r_data['trade_id']
            ep_tl=f"{get_val_tl(r_data,'entry_price',0.0):.2f}" if isinstance(get_val_tl(r_data,'entry_price',None),(int,float)) else "N/A"
            xp_tl=f"{get_val_tl(r_data,'exit_price',0.0):.2f}" if isinstance(get_val_tl(r_data,'exit_price',None),(int,float)) else "N/A"
            ret_pct_tl=f"{get_val_tl(r_data,'return_percentage',0.0):.2f}%" if isinstance(get_val_tl(r_data,'return_percentage',None),(int,float)) else "N/A"
            v_tup_tl=(str(get_val_tl(r_data,'ticker')),str(get_val_tl(r_data,'company_name')),str(get_val_tl(r_data,'entry_timestamp')),str(get_val_tl(r_data,'exit_timestamp')),str(get_val_tl(r_data,'entry_zacks_rank')),str(get_val_tl(r_data,'exit_zacks_rank')),str(get_val_tl(r_data,'entry_style_vgm')),str(get_val_tl(r_data,'exit_style_vgm')),ep_tl,xp_tl,ret_pct_tl,str(get_val_tl(r_data,'reason_for_exit')))
            tradelog_tree.insert('',tk.END, iid=trade_id_for_iid, values=v_tup_tl)
        cur.execute("SELECT COUNT(*),SUM(return_percentage) FROM trade_logs WHERE profile_id=?",(selected_profile_id,));stats=cur.fetchone()
        t_trades=stats['COUNT(*)'] if stats and stats['COUNT(*)'] is not None else 0;t_ret=stats['SUM(return_percentage)'] if stats and stats['SUM(return_percentage)'] is not None else 0.0
        cur.execute("SELECT COUNT(*) FROM trade_logs WHERE profile_id=? AND return_percentage > 0",(selected_profile_id,));win_r=cur.fetchone();wins=win_r['COUNT(*)'] if win_r else 0
        cur.execute("SELECT COUNT(*) FROM trade_logs WHERE profile_id=? AND return_percentage <= 0",(selected_profile_id,));lose_r=cur.fetchone();loses=lose_r['COUNT(*)'] if lose_r else 0
        if total_trades_label_var:total_trades_label_var.set(f"Trades: {t_trades}")
        if total_return_label_var:total_return_label_var.set(f"Return Sum: {t_ret:.2f}%")
        if winning_trades_label_var:winning_trades_label_var.set(f"Won: {wins}")
        if losing_trades_label_var:losing_trades_label_var.set(f"Lost: {loses}")
    except Exception as e: messagebox.showerror("DB Error",f"Refresh failed: {e}")
    finally:
        if conn:conn.close()

def populate_profile_comparison_view():
    global comparison_tree;
    if not comparison_tree: return
    for i in comparison_tree.get_children():comparison_tree.delete(i);conn,cur=None,None
    try:
        conn,cur=connect_db();cur.execute("SELECT profile_id,name FROM investor_profiles WHERE is_active=1 ORDER BY name ASC")
        for p_row_comp in cur.fetchall():
            pid=p_row_comp['profile_id'];name=p_row_comp['name']
            cur.execute("SELECT COUNT(*),SUM(return_percentage) FROM trade_logs WHERE profile_id=?",(pid,));stats=cur.fetchone();trades=stats['COUNT(*)'] if stats and stats['COUNT(*)'] is not None else 0;ret=stats['SUM(return_percentage)'] if stats and stats['SUM(return_percentage)'] is not None else 0.0
            cur.execute("SELECT COUNT(*) FROM trade_logs WHERE profile_id=? AND return_percentage > 0",(pid,));win_r=cur.fetchone();wt=win_r['COUNT(*)'] if win_r else 0
            cur.execute("SELECT COUNT(*) FROM trade_logs WHERE profile_id=? AND return_percentage <= 0",(pid,));lose_r=cur.fetchone();lt=lose_r['COUNT(*)'] if lose_r else 0
            comparison_tree.insert('',tk.END,values=(name,trades,wt,lt,f"{ret:.2f}%"))
    except Exception as e:messagebox.showerror("DB Error",f"Compare populate fail: {e}")
    finally:
        if conn:conn.close()

def populate_all_scanned_stocks_view():
    global all_scanned_stocks_tree;
    if not all_scanned_stocks_tree: return
    for i in all_scanned_stocks_tree.get_children():all_scanned_stocks_tree.delete(i)
    if hasattr(scanner,'last_raw_scan_results') and scanner.last_raw_scan_results:
        for s_data in scanner.last_raw_scan_results: all_scanned_stocks_tree.insert('',tk.END,values=(s_data.get('Company Name','N/A'),s_data.get('Ticker Symbol','N/A'),s_data.get('Zacks Rank','N/A'),s_data.get('Value Score','N/A'),s_data.get('Growth Score','N/A'),s_data.get('Momentum Score','N/A'),s_data.get('VGM Score','N/A'),s_data.get('Stock Page URL','N/A')))

def refresh_all_gui_data():print("DEBUG GUI: Refreshing all GUI data...");refresh_selected_profile_data_display();populate_profile_comparison_view();populate_all_scanned_stocks_view();print("DEBUG GUI: All GUI data refresh attempted.")

def open_profile_editor_window(pid_edit=None):
    global root_window; e_row=get_profile_data_for_display(pid_edit) if pid_edit else None
    if pid_edit and not e_row: messagebox.showerror("Error","Load profile failed."); return
    editor=tk.Toplevel(root_window);editor.title("Edit Profile Notes/Status");editor.geometry("500x350");editor.transient(root_window);editor.grab_set()
    m_frm=ttk.LabelFrame(editor,text="Details",padding="10");m_frm.pack(pady=10,padx=10,fill=tk.BOTH,expand=True)
    ttk.Label(m_frm,text="Name:").grid(row=0,column=0,sticky=tk.W,pady=2);n_var=tk.StringVar(value=e_row['name'] if e_row else "");n_ety=ttk.Entry(m_frm,textvariable=n_var,width=50);n_ety.grid(row=0,column=1,sticky=tk.EW,pady=2)
    p_type_txt=e_row['profile_type'] if e_row and e_row['profile_type'] else "N/A";ttk.Label(m_frm,text="Type:").grid(row=1,column=0,sticky=tk.W,pady=2);ttk.Label(m_frm,text=p_type_txt).grid(row=1,column=1,sticky=tk.W,pady=2)
    act_var=tk.BooleanVar(value=bool(e_row['is_active']) if e_row else True);act_chk=ttk.Checkbutton(m_frm,text="Active",variable=act_var);act_chk.grid(row=0,column=2,rowspan=2,sticky=tk.W,padx=10,pady=2);m_frm.columnconfigure(1,weight=1)
    ttk.Label(m_frm,text="Notes:").grid(row=2,column=0,sticky=tk.NW,pady=(10,2));notes_txt=tk.Text(m_frm,height=5,width=60,wrap=tk.WORD);notes_txt.grid(row=3,column=0,columnspan=3,sticky=tk.EW,pady=2)
    if e_row and e_row['description']: notes_txt.insert(tk.END,e_row['description'])
    def save_profile(): # Renamed inner function to avoid conflict
        name=n_var.get().strip();notes=notes_txt.get("1.0",tk.END).strip();active=1 if act_var.get() else 0
        if not name: messagebox.showerror("Validation Error","Name empty.",parent=editor); return
        conn,cur=None,None
        try:
            conn,cur=connect_db();c_pid=pid_edit
            if c_pid is None: messagebox.showerror("Error","Adding disabled.",parent=editor); return
            else: cur.execute("UPDATE investor_profiles SET name=?,description=?,is_active=? WHERE profile_id=?",(name,notes,active,c_pid))
            conn.commit();messagebox.showinfo("Success","Profile saved.",parent=editor);load_profiles_into_listbox();refresh_selected_profile_data_display();editor.destroy()
        except sqlite3.IntegrityError: messagebox.showerror("DB Error",f"Name '{name}' exists.",parent=editor)
        except Exception as e: messagebox.showerror("DB Error",f"Save failed: {e}",parent=editor)
        finally:
            if conn:conn.close()
    b_frm=ttk.Frame(editor);b_frm.pack(pady=10,fill=tk.X,side=tk.BOTTOM);ttk.Button(b_frm,text="Save",command=save_profile).pack(side=tk.RIGHT,padx=10);ttk.Button(b_frm,text="Cancel",command=editor.destroy).pack(side=tk.RIGHT);n_ety.focus_set()

def delete_selected_profile():
    global selected_profile_id,manual_entry_button;
    if selected_profile_id is None: messagebox.showwarning("No Profile","Select profile."); return
    p_row=get_profile_data_for_display(selected_profile_id)
    if not p_row or not messagebox.askyesno("Confirm Delete",f"Delete '{p_row['name']}'? Data deleted."): return
    conn,cur=None,None
    try: conn,cur=connect_db();cur.execute("DELETE FROM investor_profiles WHERE profile_id=?",(selected_profile_id,));conn.commit();messagebox.showinfo("Success",f"Profile '{p_row['name']}' deleted.")
    except Exception as e: messagebox.showerror("DB Error",f"Delete failed: {e}")
    finally:
        if conn:conn.close()
    load_profiles_into_listbox();selected_profile_id=None;manual_entry_button.config(state=tk.DISABLED) if manual_entry_button else None;refresh_selected_profile_data_display()

def trigger_manual_scan_all_active():threading.Thread(target=lambda: (scanner.scan_and_update_all_active_profiles(),root_window.after(0,refresh_all_gui_data) if root_window else None),daemon=True).start();messagebox.showinfo("Scan Started","Manual scan ALL active profiles initiated.")

def get_next_weekday_offmarket_scan_time(current_dt):
    slots = [0, 4, 8, 12, 16]; next_scan_dt = None
    for slot_hour in slots:
        potential_scan_time = current_dt.replace(hour=slot_hour, minute=0, second=0, microsecond=0)
        if potential_scan_time > current_dt: next_scan_dt = potential_scan_time; break
    if next_scan_dt is None: next_scan_dt = current_dt.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    market_open_scan_time = current_dt.replace(hour=16, minute=30, second=0, microsecond=0)
    if market_open_scan_time > current_dt and (next_scan_dt is None or market_open_scan_time < next_scan_dt) : return market_open_scan_time
    return next_scan_dt

def hourly_scan_worker():
    global scanner_active,root_window,next_scan_time_var;print("BG Scanner: Starting setup...");
    try:conn,cur=connect_db();create_tables(cur);conn.commit();add_predefined_profiles(conn,cur);conn.close();print("BG Scanner: DB setup done.")
    except Exception as e:print(f"BG Scanner: DB setup error: {e}. Stop.");return
    print("BG Scanner: Thread started.");
    while scanner_active:
        current_time_scan_start = datetime.datetime.now(); print(f"[{current_time_scan_start}] BG Scan: Starting scan cycle.")
        try:scanner.scan_and_update_all_active_profiles();print(f"[{datetime.datetime.now()}] BG Scan: Complete.")
        except Exception as e:print(f"[{datetime.datetime.now()}] BG Scan: Error: {e}")
        if root_window and scanner_active:root_window.after(0,refresh_all_gui_data)
        if not scanner_active: break
        now = datetime.datetime.now(); next_scan_time = None; weekday = now.weekday()
        if 0 <= weekday <= 4:
            time_1630 = now.replace(hour=16, minute=30, second=0, microsecond=0)
            time_2315 = now.replace(hour=23, minute=15, second=0, microsecond=0)
            if time_1630 <= now < time_2315: next_scan_time = now + timedelta(minutes=15); print(f"BG Scanner: Market hours. Next in 15 mins.")
            else:
                if now >= time_2315: next_scan_time = get_next_weekday_offmarket_scan_time( (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0) )
                else: next_scan_time = get_next_weekday_offmarket_scan_time(now)
                print(f"BG Scanner: Weekday OFF-Market hours.")
        else:
            scan_time_1700 = now.replace(hour=17, minute=0, second=0, microsecond=0)
            scan_time_2300 = now.replace(hour=23, minute=0, second=0, microsecond=0)
            if now < scan_time_1700: next_scan_time = scan_time_1700
            elif now < scan_time_2300: next_scan_time = scan_time_2300
            else: next_scan_time = (now + timedelta(days=1)).replace(hour=17, minute=0, second=0, microsecond=0)
            print(f"BG Scanner: Weekend scan.")
        if next_scan_time is None: next_scan_time = now + timedelta(hours=1); print("BG Scanner: Fallback next scan in 1 hour.")
        display_next_scan_str = next_scan_time.strftime('%Y-%m-%d %H:%M:%S')
        if root_window and next_scan_time_var and scanner_active: root_window.after(0, lambda: next_scan_time_var.set(f"Next scan: {display_next_scan_str}"))
        if not scanner_active: break
        sleep_seconds = (next_scan_time - datetime.datetime.now()).total_seconds()
        if sleep_seconds < 0: sleep_seconds = 5; print(f"BG Scanner: Next scan time {display_next_scan_str} is past. Short sleep.")
        print(f"BG Scanner: Next scan at {display_next_scan_str}. Sleeping for {sleep_seconds:.0f}s.")
        if scanner_active:
            if sleep_seconds > 60:
                slept_time = 0; chunk = 30
                while slept_time < sleep_seconds and scanner_active: time.sleep(min(chunk, sleep_seconds - slept_time)); slept_time += chunk
            elif sleep_seconds > 0 : time.sleep(sleep_seconds)
        if not scanner_active: break
        if datetime.datetime.now() >= next_scan_time : print(f"[{datetime.datetime.now()}] BG Scanner: Woke, time for scan.")
        else: print(f"[{datetime.datetime.now()}] BG Scanner: Woke, but not next scan time or scanner inactive.")
    print("BG Scanner: Thread stopped.")

def on_closing():global scanner_active,root_window;scanner_active=False;print("GUI: Closing...");root_window.destroy() if root_window else None

# --- Main Window Creation ---
def create_main_window():
    global root_window,holdings_tree,tradelog_tree,profiles_listbox,notebook,comparison_tree,all_scanned_stocks_tree,total_return_label_var,total_trades_label_var,winning_trades_label_var,losing_trades_label_var,buy_rule_text_var,sell_rule_text_var,manual_entry_button, delete_holding_button, delete_tradelog_button, next_scan_time_var
    root=tk.Tk();root_window=root;root.title("Stock Analyzer");root.geometry("1400x950");root.protocol("WM_DELETE_WINDOW",on_closing)
    next_scan_time_var = tk.StringVar(value="Next scan: Calculating...")
    status_bar_frame = ttk.Frame(root, padding="2"); status_bar_frame.pack(side=tk.TOP, fill=tk.X, pady=(0,2), padx=2)
    ttk.Label(status_bar_frame, textvariable=next_scan_time_var, font=('Helvetica', 9, 'italic')).pack(side=tk.LEFT, padx=(3,0))
    top_ctrl=ttk.Frame(root,padding="5");top_ctrl.pack(side=tk.TOP,fill=tk.X,pady=(5,0))
    prof_frm_cont=ttk.LabelFrame(top_ctrl,text="Profiles",padding="10");prof_frm_cont.pack(side=tk.LEFT,padx=5,fill=tk.Y)
    prof_lst_sb_frm=ttk.Frame(prof_frm_cont);prof_lst_sb_frm.pack(pady=5,expand=True,fill=tk.BOTH);profiles_listbox=tk.Listbox(prof_lst_sb_frm,exportselection=False,height=10,width=35)
    prof_sb=ttk.Scrollbar(prof_lst_sb_frm,orient=tk.VERTICAL,command=profiles_listbox.yview);profiles_listbox.configure(yscrollcommand=prof_sb.set);profiles_listbox.pack(side=tk.LEFT,expand=True,fill=tk.BOTH);prof_sb.pack(side=tk.RIGHT,fill=tk.Y);profiles_listbox.bind("<<ListboxSelect>>",on_profile_select)
    prof_btn_frm=ttk.Frame(prof_frm_cont);prof_btn_frm.pack(fill=tk.X,pady=5,side=tk.BOTTOM);ttk.Button(prof_btn_frm,text="Add",command=lambda:open_profile_editor_window(),state=tk.DISABLED).pack(side=tk.LEFT,expand=True,fill=tk.X);ttk.Button(prof_btn_frm,text="Edit Notes",command=lambda:open_profile_editor_window(selected_profile_id) if selected_profile_id is not None else messagebox.showinfo("Info","Select profile.")).pack(side=tk.LEFT,expand=True,fill=tk.X);ttk.Button(prof_btn_frm,text="Del",command=delete_selected_profile).pack(side=tk.LEFT,expand=True,fill=tk.X)
    glob_act_frm=ttk.Frame(top_ctrl,padding="10");glob_act_frm.pack(side=tk.LEFT,padx=5,expand=True,fill=tk.X,anchor='n');ttk.Button(glob_act_frm,text="Refresh All",command=refresh_all_gui_data).pack(pady=5,fill=tk.X);ttk.Button(glob_act_frm,text="Manual Scan All",command=trigger_manual_scan_all_active).pack(pady=5,fill=tk.X)
    notebook=ttk.Notebook(root);notebook.pack(expand=True,fill="both",padx=10,pady=10)
    prof_det_tab=ttk.Frame(notebook);notebook.add(prof_det_tab,text="Selected Profile")
    sel_prof_act_btn_frm=ttk.Frame(prof_det_tab);sel_prof_act_btn_frm.pack(fill=tk.X,pady=5,padx=5);manual_entry_button=ttk.Button(sel_prof_act_btn_frm,text="Manual Stock Entry",command=handle_manual_stock_entry,state=tk.DISABLED);manual_entry_button.pack(side=tk.LEFT,padx=5)
    hold_frm=ttk.LabelFrame(prof_det_tab,text="Holdings",padding="5");hold_frm.pack(expand=True,fill=tk.BOTH,pady=5,padx=5);h_cols=("Ticker","Co","Entry Time","E Rank","E:Price","E:V","E:G","E:M","E:VGM","Last Check","C Rank","C:V","C:G","C:M","C:VGM");holdings_tree=ttk.Treeview(hold_frm,columns=h_cols,show="headings")
    for c in h_cols:w=150 if "Time" in c or "Check" in c else(180 if "Co"==c else(80 if "Price" in c else 65));holdings_tree.heading(c,text=c);holdings_tree.column(c,width=w,anchor=tk.W if "Co"==c or "Time" in c else tk.CENTER,stretch="Co" in c)
    h_vsb=ttk.Scrollbar(hold_frm,orient="vertical",command=holdings_tree.yview);h_hsb=ttk.Scrollbar(hold_frm,orient="horizontal",command=holdings_tree.xview);holdings_tree.configure(yscrollcommand=h_vsb.set,xscrollcommand=h_hsb.set);h_vsb.pack(side=tk.RIGHT,fill=tk.Y);h_hsb.pack(side=tk.BOTTOM,fill=tk.X);holdings_tree.pack(expand=True,fill=tk.BOTH)
    holdings_tree.bind("<<TreeviewSelect>>", on_holding_select)
    delete_holding_button = ttk.Button(hold_frm, text="Delete Selected Holding", command=handle_delete_selected_holding, state=tk.DISABLED); delete_holding_button.pack(side=tk.BOTTOM, pady=5, anchor=tk.E)
    bot_det_pane=ttk.PanedWindow(prof_det_tab,orient=tk.HORIZONTAL);bot_det_pane.pack(expand=True,fill=tk.BOTH,pady=5,padx=5)
    trade_frm=ttk.LabelFrame(bot_det_pane,text="Trade Log",padding="5");bot_det_pane.add(trade_frm,weight=2);tl_cols=("Ticker","Co","Entry Time","Exit Time","E Rank","X Rank","E VGM","X VGM","E Price","X Price","Return %","Reason");tradelog_tree=ttk.Treeview(trade_frm,columns=tl_cols,show="headings")
    for c in tl_cols:w=140 if "Time" in c else(180 if "Co"==c else(100 if "Reason"==c else 70));tradelog_tree.heading(c,text=c);tradelog_tree.column(c,width=w,anchor=tk.W if "Co"==c or "Time" in c or "Reason"==c else tk.CENTER,stretch="Co" in c or "Reason" in c)
    tl_vsb=ttk.Scrollbar(trade_frm,orient="vertical",command=tradelog_tree.yview);tl_hsb=ttk.Scrollbar(trade_frm,orient="horizontal",command=tradelog_tree.xview);tradelog_tree.configure(yscrollcommand=tl_vsb.set,xscrollcommand=tl_hsb.set);tl_vsb.pack(side=tk.RIGHT,fill=tk.Y);tl_hsb.pack(side=tk.BOTTOM,fill=tk.X);tradelog_tree.pack(expand=True,fill=tk.BOTH)
    tradelog_tree.bind("<<TreeviewSelect>>", on_tradelog_select)
    delete_tradelog_button = ttk.Button(trade_frm, text="Delete Selected Trade Log Entry", command=handle_delete_selected_tradelog, state=tk.DISABLED)
    delete_tradelog_button.pack(side=tk.BOTTOM, pady=5, anchor=tk.E)
    s_r_frm=ttk.Frame(bot_det_pane);bot_det_pane.add(s_r_frm,weight=1);stats_frm=ttk.LabelFrame(s_r_frm,text="Statistics",padding="5");stats_frm.pack(fill=tk.X,padx=5,pady=(0,5),anchor='n')
    total_return_label_var=tk.StringVar(value="Return Sum: N/A");total_trades_label_var=tk.StringVar(value="Trades: N/A");winning_trades_label_var=tk.StringVar(value="Won: N/A");losing_trades_label_var=tk.StringVar(value="Lost: N/A")
    ttk.Label(stats_frm,textvariable=total_trades_label_var).pack(pady=2,anchor=tk.W);ttk.Label(stats_frm,textvariable=winning_trades_label_var).pack(pady=2,anchor=tk.W);ttk.Label(stats_frm,textvariable=losing_trades_label_var).pack(pady=2,anchor=tk.W);ttk.Label(stats_frm,textvariable=total_return_label_var).pack(pady=2,anchor=tk.W)
    ttk.Label(stats_frm,text="Return % based on available prices.",font=('Helvetica',8,'italic')).pack(pady=(5,0),anchor=tk.W)
    rules_disp_frm=ttk.LabelFrame(s_r_frm,text="Profile Rules Summary",padding="10");rules_disp_frm.pack(fill=tk.BOTH,expand=True,padx=5,pady=5,anchor='n');buy_rule_text_var=tk.StringVar(value="N/A");sell_rule_text_var=tk.StringVar(value="N/A")
    ttk.Label(rules_disp_frm,text="Buy:",font=('Helvetica',10,'bold')).pack(anchor=tk.W);ttk.Label(rules_disp_frm,textvariable=buy_rule_text_var,wraplength=350,justify=tk.LEFT).pack(fill=tk.X,pady=(0,5));ttk.Label(rules_disp_frm,text="Sell:",font=('Helvetica',10,'bold')).pack(anchor=tk.W);ttk.Label(rules_disp_frm,textvariable=sell_rule_text_var,wraplength=350,justify=tk.LEFT).pack(fill=tk.X)
    comp_tab=ttk.Frame(notebook);notebook.add(comp_tab,text="Comparison");comp_frm=ttk.LabelFrame(comp_tab,text="Profile Performance",padding="10");comp_frm.pack(expand=True,fill=tk.BOTH,padx=10,pady=10);comp_cols=("Profile","Trades","Won","Lost","Return %");comparison_tree=ttk.Treeview(comp_frm,columns=comp_cols,show="headings")
    for c in comp_cols:w=250 if "Profile"==c else 150;comparison_tree.heading(c,text=c);comparison_tree.column(c,width=w,anchor=tk.W if "Profile"==c else tk.CENTER,stretch="Profile"==c)
    comp_vsb=ttk.Scrollbar(comp_frm,orient="vertical",command=comparison_tree.yview);comp_hsb=ttk.Scrollbar(comp_frm,orient="horizontal",command=comparison_tree.xview);comparison_tree.configure(yscrollcommand=comp_vsb.set,xscrollcommand=comp_hsb.set);comp_vsb.pack(side=tk.RIGHT,fill=tk.Y);comp_hsb.pack(side=tk.BOTTOM,fill=tk.X);comparison_tree.pack(expand=True,fill=tk.BOTH)
    all_scan_tab=ttk.Frame(notebook);notebook.add(all_scan_tab,text="All Scanned");scan_lf=ttk.LabelFrame(all_scan_tab,text="Last Scan Results",padding="10");scan_lf.pack(expand=True,fill=tk.BOTH,padx=10,pady=10);scan_cols=("Co Name","Ticker","Z Rank","Val","Gro","Mom","VGM","URL");all_scanned_stocks_tree=ttk.Treeview(scan_lf,columns=scan_cols,show="headings")
    for c_name in scan_cols:c_w=250 if "Co Name"==c_name else(300 if "URL"==c_name else 100);c_a=tk.W if "Co Name"==c_name or "URL"==c_name else tk.CENTER;all_scanned_stocks_tree.heading(c_name,text=c_name);all_scanned_stocks_tree.column(c_name,width=c_w,anchor=c_a,stretch="Co Name"==c_name or "URL"==c_name)
    sc_vsb=ttk.Scrollbar(scan_lf,orient="vertical",command=all_scanned_stocks_tree.yview);sc_hsb=ttk.Scrollbar(scan_lf,orient="horizontal",command=all_scanned_stocks_tree.xview);all_scanned_stocks_tree.configure(yscrollcommand=sc_vsb.set,xscrollcommand=sc_hsb.set);sc_vsb.pack(side=tk.RIGHT,fill=tk.Y);sc_hsb.pack(side=tk.BOTTOM,fill=tk.X);all_scanned_stocks_tree.pack(expand=True,fill=tk.BOTH)
    load_profiles_into_listbox();refresh_all_gui_data()
    root.mainloop()

if __name__ == "__main__":
    print("Main: Init app & scanner thread...");scan_thread=threading.Thread(target=hourly_scan_worker,daemon=True);scan_thread.start()
    create_main_window()
    print("Main: GUI closed.");scanner_active=False;print("Main: Exiting.")
