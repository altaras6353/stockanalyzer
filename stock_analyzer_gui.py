import tkinter as tk
from tkinter import ttk
from tkinter import simpledialog, messagebox
import datetime
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
scanner_active = True
manual_entry_button = None
delete_holding_button = None
delete_tradelog_button = None

# --- Manual Stock Entry ---
def handle_manual_stock_entry(): # As implemented
    global selected_profile_id, root_window
    if selected_profile_id is None: messagebox.showerror("Error", "No profile selected.", parent=root_window); return
    ticker_symbol = simpledialog.askstring("Manual Stock Entry", "Enter Ticker Symbol:", parent=root_window)
    if not ticker_symbol: return
    ticker_symbol = ticker_symbol.strip().upper()
    if not ticker_symbol: messagebox.showerror("Error", "Ticker symbol cannot be empty.", parent=root_window); return
    def fetch_and_add_task(profile_id_local, ticker_local):
        # ... (Implementation from Subtask 26, confirmed correct) ...
        print(f"MANUAL ENTRY THREAD: Starting for {ticker_local}, Profile ID: {profile_id_local}")
        url = f"https://www.zacks.com/stock/quote/{ticker_local}"; individual_page_html_content = None
        try:
            response_stock = requests.get(url, headers=scanner.HEADERS, timeout=10); response_stock.raise_for_status()
            individual_page_html_content = response_stock.text
        except Exception as e_fetch:
            print(f"MANUAL ENTRY THREAD: Failed live fetch for {ticker_local}: {e_fetch}. Using fallback HTML.")
            try:
                with open("individual_stock_page.html", "r", encoding="utf-8") as f: individual_page_html_content = f.read()
            except FileNotFoundError:
                if root_window: root_window.after(0, lambda: messagebox.showerror("Error", f"Could not fetch data for {ticker_local} (fallback HTML missing).", parent=root_window)); return
        ratings_data = extract_stock_ratings(individual_page_html_content); current_zacks_rank_str = ratings_data.get('Zacks Rank')
        company_name_from_parse = ratings_data.get('Company Name', ticker_local)
        style_scores_dict = {'Value':ratings_data.get('Value'),'Growth':ratings_data.get('Growth'),'Momentum':ratings_data.get('Momentum'),'VGM':ratings_data.get('VGM')}
        entry_price = get_current_price(ticker_local)
        data_missing=False; error_msg_parts=[]
        if not current_zacks_rank_str: data_missing=True; error_msg_parts.append("- Zacks Rank missing.")
        if not all(s is not None and s!="N/A" for s in style_scores_dict.values()) or len(style_scores_dict)<4: data_missing=True;error_msg_parts.append("- Some Style Scores missing.")
        if entry_price is None or entry_price<=0: data_missing=True;error_msg_parts.append("- Valid entry price missing.")
        if data_missing:
            if root_window: root_window.after(0,lambda:messagebox.showerror("Error",f"Could not retrieve all data for {ticker_local}:\n"+"\n".join(error_msg_parts),parent=root_window)); return
        conn_task,cursor_task=connect_db()
        try:
            cursor_task.execute("SELECT holding_id FROM stock_holdings WHERE profile_id=? AND ticker=?",(profile_id_local,ticker_local))
            if cursor_task.fetchone():
                if root_window:root_window.after(0,lambda:messagebox.showinfo("Info",f"{ticker_local} already in holdings.",parent=root_window)); return
            now_ts_iso=datetime.datetime.now().isoformat();notes=f"Manually added on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            entry_values=(profile_id_local,ticker_local,company_name_from_parse,now_ts_iso,current_zacks_rank_str,style_scores_dict.get('Value'),style_scores_dict.get('Growth'),style_scores_dict.get('Momentum'),style_scores_dict.get('VGM'),entry_price,now_ts_iso,current_zacks_rank_str,style_scores_dict.get('Value'),style_scores_dict.get('Growth'),style_scores_dict.get('Momentum'),style_scores_dict.get('VGM'),notes)
            cursor_task.execute("INSERT INTO stock_holdings (profile_id,ticker,company_name,entry_timestamp,entry_zacks_rank,entry_style_value,entry_style_growth,entry_style_momentum,entry_style_vgm,entry_price,last_checked_timestamp,current_zacks_rank,current_style_value,current_style_growth,current_style_momentum,current_style_vgm,notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",entry_values)
            conn_task.commit()
            if root_window:root_window.after(0,lambda:messagebox.showinfo("Success",f"{ticker_local} added to profile {profile_id_local}.",parent=root_window));root_window.after(0,refresh_all_gui_data)
        except Exception as e_db:
            if root_window:root_window.after(0,lambda:messagebox.showerror("DB Error",f"Failed to add {ticker_local}: {e_db}",parent=root_window))
        finally:
            if conn_task:conn_task.close()
    messagebox.showinfo("In Progress",f"Fetching data for {ticker_symbol} for profile {selected_profile_id}. Result via popup.",parent=root_window)
    threading.Thread(target=fetch_and_add_task,args=(selected_profile_id,ticker_symbol),daemon=True).start()

# --- Delete Selected Holding ---
def handle_delete_selected_holding(): # As implemented in Subtask 30
    global selected_profile_id, holdings_tree, root_window
    if selected_profile_id is None: messagebox.showerror("Error", "No profile selected.", parent=root_window); return
    selected_items = holdings_tree.selection();
    if not selected_items: messagebox.showwarning("No Selection", "No holding selected to delete.", parent=root_window); return
    selected_item_iid = selected_items[0]; item_values = holdings_tree.item(selected_item_iid, 'values')
    if not item_values or len(item_values) == 0: messagebox.showerror("Error", "Could not retrieve details.", parent=root_window); return
    ticker_to_delete = item_values[0]
    profile_data_row = get_profile_data_for_display(selected_profile_id)
    profile_name = profile_data_row['name'] if profile_data_row else f"ID {selected_profile_id}"
    if not messagebox.askyesno("Confirm Delete", f"Delete holding '{ticker_to_delete}' from profile '{profile_name}'?", parent=root_window): return
    conn, cursor = None, None
    try:
        conn, cursor = connect_db()
        cursor.execute("DELETE FROM stock_holdings WHERE profile_id = ? AND ticker = ?", (selected_profile_id, ticker_to_delete)); conn.commit()
        if cursor.rowcount > 0: messagebox.showinfo("Success", f"Holding '{ticker_to_delete}' deleted from '{profile_name}'.", parent=root_window)
        else: messagebox.showwarning("Not Found", f"Holding '{ticker_to_delete}' not found in '{profile_name}'.", parent=root_window)
        if root_window: root_window.after(0, refresh_all_gui_data)
    except Exception as e: messagebox.showerror("DB Error", f"Failed to delete holding: {e}", parent=root_window)
    finally:
        if conn: conn.close()

# --- Delete Selected Trade Log Entry ---
def handle_delete_selected_tradelog():
    global selected_profile_id, tradelog_tree, root_window

    if selected_profile_id is None: # Should ideally not happen if button is managed by profile selection
        messagebox.showerror("Error", "No profile selected.", parent=root_window)
        return

    selected_items_iids = tradelog_tree.selection()
    if not selected_items_iids:
        messagebox.showwarning("No Selection", "No trade log entry selected from the table.", parent=root_window)
        return

    trade_id_to_delete = selected_items_iids[0] # This iid IS the trade_id due to how it's populated

    # Fetch some details for the confirmation message using the trade_id (iid)
    item_values = tradelog_tree.item(trade_id_to_delete, 'values')
    display_ticker = item_values[0] if item_values and len(item_values) > 0 else "Unknown Ticker"
    display_exit_time = item_values[3] if item_values and len(item_values) > 3 else "Unknown Time" # Exit Time is 4th col (idx 3)

    profile_data_row = get_profile_data_for_display(selected_profile_id)
    profile_name = profile_data_row['name'] if profile_data_row else f"ID {selected_profile_id}"

    if not messagebox.askyesno("Confirm Delete",
                               f"Are you sure you want to delete this trade log entry from profile '{profile_name}'?\nTicker: {display_ticker}\nExit Time: {display_exit_time}",
                               parent=root_window):
        return

    conn, cursor = None, None
    try:
        conn, cursor = connect_db()
        print(f"GUI: Deleting trade log entry with trade_id {trade_id_to_delete} for profile_id {selected_profile_id}...")
        # Note: We delete by trade_id, which is unique. Profile_id check is mostly for safety/consistency.
        cursor.execute("DELETE FROM trade_logs WHERE trade_id = ? AND profile_id = ?",
                       (trade_id_to_delete, selected_profile_id))
        conn.commit()

        if cursor.rowcount > 0:
            messagebox.showinfo("Success", f"Trade log entry (ID: {trade_id_to_delete}) deleted successfully from profile '{profile_name}'.", parent=root_window)
            print(f"GUI: Successfully deleted trade log entry ID: {trade_id_to_delete}")
        else:
            messagebox.showwarning("Not Found", f"Trade log entry (ID: {trade_id_to_delete}) not found for profile '{profile_name}' in the database.", parent=root_window)
            print(f"GUI: No trade log entry deleted for ID: {trade_id_to_delete} (already gone or profile ID mismatch?).")

        if root_window:
            root_window.after(0, refresh_all_gui_data) # Refresh all views

    except sqlite3.Error as e:
        print(f"GUI: DB Error deleting trade log entry: {e}")
        messagebox.showerror("Database Error", f"Failed to delete trade log entry: {e}", parent=root_window)
    except Exception as e_gen:
        print(f"GUI: Unexpected error deleting trade log entry: {e_gen}")
        messagebox.showerror("Error", f"An unexpected error occurred: {e_gen}", parent=root_window)
    finally:
        if conn:
            conn.close()


# --- Helper Function for Profile Rule Display Text ---
def get_profile_rules_display_text(profile_type: str | None) -> dict: # Updated in Subtask 28
    buy_rule = "Entry: Zacks Rank '1' AND (Style Scores: All 'A' OR Max 1 'B' with rest 'A')."
    sell_rule = "N/A"
    if profile_type == "Cautious": sell_rule = "Exit: Rank is not '1' or '2' (i.e., 3, 4, 5) OR Calculated Score > 4 OR Score is invalid."
    elif profile_type == "Hesitant": sell_rule = "Exit: Rank is not '1' OR Calculated Score > 5 OR Score is invalid."
    elif profile_type == "Brave": sell_rule = "Exit: Rank is not '1', '2', or '3' (i.e., 4 or 5) OR Calculated Score > 6 OR Score is invalid."
    elif profile_type == "Reckless": sell_rule = "Exit: Rank is '5' (i.e., >4) OR Score is invalid."
    elif profile_type == "Greedy2Pct": sell_rule = "Exit: (Rank is not '1' OR Calculated Score > 4 OR Score is invalid) OR Profit > 2%."
    elif profile_type == "Greedy3Pct": sell_rule = "Exit: (Rank is not '1' OR Calculated Score > 4 OR Score is invalid) OR Profit > 3%."
    elif profile_type == "Greedy4Pct": sell_rule = "Exit: (Rank is not '1' OR Calculated Score > 4 OR Score is invalid) OR Profit > 4%."
    elif profile_type is None or profile_type == "N/A (Custom)": buy_rule = "Entry: Rules not predefined."; sell_rule = "Exit: Rules not predefined."
    return {'buy': buy_rule, 'sell': sell_rule}

# --- Profile Management Functions ---
def load_profiles_into_listbox(): # ... (as before)
    global profiles_listbox, profile_id_map, root_window;
    if not profiles_listbox: return
    profiles_listbox.delete(0, tk.END); profile_id_map.clear(); conn, cursor = None, None
    try:
        conn, cursor = connect_db(); cursor.execute("SELECT profile_id, name, is_active FROM investor_profiles ORDER BY name ASC")
        for index,p_row in enumerate(cursor.fetchall()): profiles_listbox.insert(tk.END,f"{p_row['name']} {'(Active)' if p_row['is_active'] else '(Inactive)'}"); profile_id_map[index]=p_row['profile_id']
        if root_window: root_window.after(0,refresh_all_gui_data)
    except Exception as e: messagebox.showerror("DB Error",f"Load profiles failed: {e}")
    finally:
        if conn:conn.close()

def on_profile_select(event): # ... (as before, enables/disables manual_entry_button)
    global selected_profile_id, profiles_listbox, profile_id_map, manual_entry_button
    if not profiles_listbox or not profiles_listbox.curselection(): selected_profile_id=None
    else: selected_profile_id = profile_id_map.get(profiles_listbox.curselection()[0])

    if manual_entry_button: manual_entry_button.config(state=tk.NORMAL if selected_profile_id is not None else tk.DISABLED)
    refresh_selected_profile_data_display()

def get_profile_data_for_display(pid): # ... (as before)
    if pid is None: return None; conn,cur=None,None
    try: conn,cur=connect_db(); cur.execute("SELECT profile_id,name,description,is_active,profile_type FROM investor_profiles WHERE profile_id=?",(pid,)); return cur.fetchone()
    except Exception as e: messagebox.showerror("DB Error",f"Fetch profile failed: {e}"); return None
    finally:
        if conn:conn.close()

def open_profile_editor_window(pid_edit=None): # ... (as before, simplified editor)
    global root_window; e_row=get_profile_data_for_display(pid_edit) if pid_edit else None
    if pid_edit and not e_row: messagebox.showerror("Error","Load profile failed."); return
    editor=tk.Toplevel(root_window);editor.title("Edit Profile Notes/Status");editor.geometry("500x350");editor.transient(root_window);editor.grab_set()
    m_frm=ttk.LabelFrame(editor,text="Details",padding="10");m_frm.pack(pady=10,padx=10,fill=tk.BOTH,expand=True)
    ttk.Label(m_frm,text="Name:").grid(row=0,column=0,sticky=tk.W,pady=2);n_var=tk.StringVar(value=e_row['name'] if e_row else "");n_ety=ttk.Entry(m_frm,textvariable=n_var,width=50);n_ety.grid(row=0,column=1,sticky=tk.EW,pady=2)
    p_type_txt=e_row['profile_type'] if e_row and e_row['profile_type'] else "N/A";ttk.Label(m_frm,text="Type:").grid(row=1,column=0,sticky=tk.W,pady=2);ttk.Label(m_frm,text=p_type_txt).grid(row=1,column=1,sticky=tk.W,pady=2)
    act_var=tk.BooleanVar(value=bool(e_row['is_active']) if e_row else True);act_chk=ttk.Checkbutton(m_frm,text="Active",variable=act_var);act_chk.grid(row=0,column=2,rowspan=2,sticky=tk.W,padx=10,pady=2);m_frm.columnconfigure(1,weight=1)
    ttk.Label(m_frm,text="Notes:").grid(row=2,column=0,sticky=tk.NW,pady=(10,2));notes_txt=tk.Text(m_frm,height=5,width=60,wrap=tk.WORD);notes_txt.grid(row=3,column=0,columnspan=3,sticky=tk.EW,pady=2)
    if e_row and e_row['description']: notes_txt.insert(tk.END,e_row['description'])
    def save_profile():
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

def delete_selected_profile(): # ... (as before)
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

# --- Event handler for holdings_tree selection ---
def on_holding_select(event): # As implemented in Subtask 29
    global delete_holding_button, holdings_tree
    if not delete_holding_button or not holdings_tree: return
    selected_items = holdings_tree.selection()
    if selected_items: delete_holding_button.config(state=tk.NORMAL)
    else: delete_holding_button.config(state=tk.DISABLED)

# --- Event handler for tradelog_tree selection ---
def on_tradelog_select(event): # New
    global delete_tradelog_button, tradelog_tree
    if not delete_tradelog_button or not tradelog_tree: return
    selected_items = tradelog_tree.selection()
    if selected_items: delete_tradelog_button.config(state=tk.NORMAL)
    else: delete_tradelog_button.config(state=tk.DISABLED)

# --- Refresh Data Display Functions ---
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

        # Updated tl_q to include trade_id for iid
        tl_q="SELECT trade_id, ticker,company_name,entry_timestamp,exit_timestamp,entry_zacks_rank,exit_zacks_rank,entry_style_vgm,exit_style_vgm,entry_price,exit_price,return_percentage,reason_for_exit FROM trade_logs WHERE profile_id=? ORDER BY exit_timestamp DESC"
        tl_rows=cur.execute(tl_q,(selected_profile_id,)).fetchall()
        for r_data in tl_rows:
            def get_val_tl(r,k,d="N/A"):
                try: v=r[k]; return v if v is not None else d
                except(IndexError,KeyError): return d
            trade_id_for_iid = r_data['trade_id'] # Get trade_id for use as iid
            ep_tl=f"{get_val_tl(r_data,'entry_price',0.0):.2f}" if isinstance(get_val_tl(r_data,'entry_price',None),(int,float)) else "N/A"
            xp_tl=f"{get_val_tl(r_data,'exit_price',0.0):.2f}" if isinstance(get_val_tl(r_data,'exit_price',None),(int,float)) else "N/A"
            ret_pct_tl=f"{get_val_tl(r_data,'return_percentage',0.0):.2f}%" if isinstance(get_val_tl(r_data,'return_percentage',None),(int,float)) else "N/A"
            # Ensure tuple matches trade_cols order, excluding trade_id from *displayed* values
            v_tup_tl=(str(get_val_tl(r_data,'ticker')),str(get_val_tl(r_data,'company_name')),str(get_val_tl(r_data,'entry_timestamp')),str(get_val_tl(r_data,'exit_timestamp')),str(get_val_tl(r_data,'entry_zacks_rank')),str(get_val_tl(r_data,'exit_zacks_rank')),str(get_val_tl(r_data,'entry_style_vgm')),str(get_val_tl(r_data,'exit_style_vgm')),ep_tl,xp_tl,ret_pct_tl,str(get_val_tl(r_data,'reason_for_exit')))
            tradelog_tree.insert('',tk.END, iid=trade_id_for_iid, values=v_tup_tl) # Use trade_id as iid

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

def populate_profile_comparison_view(): # ... (as before)
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

def populate_all_scanned_stocks_view(): # ... (as before)
    global all_scanned_stocks_tree;
    if not all_scanned_stocks_tree: return
    for i in all_scanned_stocks_tree.get_children():all_scanned_stocks_tree.delete(i)
    if hasattr(scanner,'last_raw_scan_results') and scanner.last_raw_scan_results:
        for s_data in scanner.last_raw_scan_results: all_scanned_stocks_tree.insert('',tk.END,values=(s_data.get('Company Name','N/A'),s_data.get('Ticker Symbol','N/A'),s_data.get('Zacks Rank','N/A'),s_data.get('Value Score','N/A'),s_data.get('Growth Score','N/A'),s_data.get('Momentum Score','N/A'),s_data.get('VGM Score','N/A'),s_data.get('Stock Page URL','N/A')))

def refresh_all_gui_data():print("DEBUG GUI: Refreshing all GUI data...");refresh_selected_profile_data_display();populate_profile_comparison_view();populate_all_scanned_stocks_view();print("DEBUG GUI: All GUI data refresh attempted.")
def trigger_manual_scan_all_active():threading.Thread(target=lambda: (scanner.scan_and_update_all_active_profiles(),root_window.after(0,refresh_all_gui_data) if root_window else None),daemon=True).start();messagebox.showinfo("Scan Started","Manual scan ALL active profiles initiated.")
def hourly_scan_worker(): # ... (as before, sleep_duration=3600)
    global scanner_active,root_window;print("BG Scanner: Starting setup...");
    try:conn,cur=connect_db();create_tables(cur);conn.commit();add_predefined_profiles(conn,cur);conn.close();print("BG Scanner: DB setup done.")
    except Exception as e:print(f"BG Scanner: DB setup error: {e}. Stop.");return
    print("BG Scanner: Thread started.");
    while scanner_active:
        try:scanner.scan_and_update_all_active_profiles();print(f"[{datetime.datetime.now()}] BG Scan: Complete.")
        except Exception as e:print(f"[{datetime.datetime.now()}] BG Scan: Error: {e}")
        if root_window and scanner_active:root_window.after(0,refresh_all_gui_data)
        s_dur=3600;print(f"[{datetime.datetime.now()}] BG Scan: Next in {s_dur//3600}h.")
        if scanner_active:print(f"[{datetime.datetime.now()}] BG Scan: Sleep {s_dur}s...");time.sleep(s_dur)
        if scanner_active:print(f"[{datetime.datetime.now()}] BG Scan: Woke.")
        else:print(f"[{datetime.datetime.now()}] BG Scan: Woke but inactive.")
    print("BG Scanner: Thread stopped.")
def on_closing():global scanner_active,root_window;scanner_active=False;print("GUI: Closing...");root_window.destroy() if root_window else None

# --- Main Window Creation ---
def create_main_window():
    global root_window,holdings_tree,tradelog_tree,profiles_listbox,notebook,comparison_tree,all_scanned_stocks_tree,total_return_label_var,total_trades_label_var,winning_trades_label_var,losing_trades_label_var,buy_rule_text_var,sell_rule_text_var,manual_entry_button, delete_holding_button, delete_tradelog_button
    root=tk.Tk();root_window=root;root.title("Stock Analyzer");root.geometry("1400x950");root.protocol("WM_DELETE_WINDOW",on_closing)
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
