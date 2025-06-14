import tkinter as tk
from tkinter import ttk
from datetime import datetime
import requests # For live fetching

# Import parsing functions from other files
from parse_main_page import extract_top_vgm_stocks
from parse_stock_page import extract_stock_ratings

# Global variable for the Treeview widget to be accessible in handle_get_stock_analysis
tree = None

def handle_get_stock_analysis():
    """
    Handles the 'Get Stock Analysis' button click.
    Fetches data (live with fallback to local files) and populates the Treeview.
    """
    global tree
    if tree is None:
        print("Error: Treeview is not initialized.")
        return

    # Clear any previous data from the Treeview
    for i in tree.get_children():
        tree.delete(i)

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

    # --- Fetch Main Page HTML ---
    main_page_html_content = None
    try:
        print("Attempting to fetch main page (https://www.zacks.com/) live...")
        response = requests.get('https://www.zacks.com/', headers=headers, timeout=10)
        response.raise_for_status()  # Raise an exception for HTTP errors
        main_page_html_content = response.text
        print("Successfully fetched main page live.")
    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch main page live: {e}. Falling back to local main_page.html.")
    except Exception as e: # Catch any other unexpected errors during fetch
        print(f"An unexpected error occurred during main page fetch: {e}. Falling back to local main_page.html.")

    if main_page_html_content is None: # Fallback if live fetch failed
        try:
            with open("main_page.html", "r", encoding="utf-8") as f:
                main_page_html_content = f.read()
            print("Loaded main page from local main_page.html.")
        except FileNotFoundError:
            print("Error: main_page.html not found for fallback.")
            return # Critical error, cannot proceed

    top_stocks = extract_top_vgm_stocks(main_page_html_content)

    if not top_stocks:
        print("No top stocks found from main page content.")
        return

    # --- Iterate through top stocks and get detailed ratings ---
    for stock_info in top_stocks:
        company_name = stock_info.get('Company Name', 'N/A')
        ticker = stock_info.get('Ticker Symbol', 'N/A')
        stock_page_url = stock_info.get('Stock Page URL', '') # URL from main page parsing

        individual_page_html_content = None
        if stock_page_url: # Only attempt live fetch if URL is valid
            try:
                print(f"Attempting to fetch individual stock page for {ticker} ({stock_page_url}) live...")
                response = requests.get(stock_page_url, headers=headers, timeout=10)
                response.raise_for_status()
                individual_page_html_content = response.text
                print(f"Successfully fetched page for {ticker} live.")
            except requests.exceptions.RequestException as e:
                print(f"Failed to fetch page for {ticker} live: {e}. Falling back to local individual_stock_page.html.")
            except Exception as e:
                print(f"An unexpected error occurred during {ticker} page fetch: {e}. Falling back to local.")
        else:
            print(f"No valid URL for {ticker}, falling back to local individual_stock_page.html for parsing.")

        if individual_page_html_content is None: # Fallback if live fetch failed or no URL
            try:
                with open("individual_stock_page.html", "r", encoding="utf-8") as f:
                    individual_page_html_content = f.read()
                print(f"Loaded ratings for {ticker} from local individual_stock_page.html (fallback).")
            except FileNotFoundError:
                print(f"Error: individual_stock_page.html not found for {ticker} fallback.")
                # Insert with N/A ratings or skip
                tree.insert('', tk.END, values=(timestamp, company_name, ticker, 'N/A', 'N/A', 'N/A', 'N/A'))
                continue # Move to next stock

        ratings = extract_stock_ratings(individual_page_html_content)

        value_score = ratings.get('Value', 'N/A')
        growth_score = ratings.get('Growth', 'N/A')
        momentum_score = ratings.get('Momentum', 'N/A')
        vgm_score = ratings.get('VGM', 'N/A')

        tree.insert('', tk.END, values=(
            timestamp,
            company_name,
            ticker,
            value_score,
            growth_score,
            momentum_score,
            vgm_score
        ))

def create_main_window():
    global tree
    root = tk.Tk()
    root.title("Zacks Stock Analyzer")
    root.geometry("950x600")

    button_frame = ttk.Frame(root, padding="10")
    button_frame.pack(pady=10)

    get_analysis_button = ttk.Button(button_frame, text="Get Stock Analysis", command=handle_get_stock_analysis)
    get_analysis_button.pack()

    results_frame = ttk.Frame(root, padding="10")
    results_frame.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)

    columns = ("Timestamp", "Company Name", "Ticker", "Value", "Growth", "Momentum", "VGM")
    tree = ttk.Treeview(results_frame, columns=columns, show="headings")

    tree.heading("Timestamp", text="Timestamp")
    tree.heading("Company Name", text="Company Name")
    tree.heading("Ticker", text="Ticker")
    tree.heading("Value", text="Value Score")
    tree.heading("Growth", text="Growth Score")
    tree.heading("Momentum", text="Momentum Score")
    tree.heading("VGM", text="VGM Score")

    tree.column("Timestamp", width=140, anchor=tk.W)
    tree.column("Company Name", width=250, anchor=tk.W)
    tree.column("Ticker", width=80, anchor=tk.CENTER)
    tree.column("Value", width=80, anchor=tk.CENTER)
    tree.column("Growth", width=80, anchor=tk.CENTER)
    tree.column("Momentum", width=100, anchor=tk.CENTER)
    tree.column("VGM", width=80, anchor=tk.CENTER)

    vsb = ttk.Scrollbar(results_frame, orient="vertical", command=tree.yview)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)
    tree.configure(yscrollcommand=vsb.set)

    hsb = ttk.Scrollbar(results_frame, orient="horizontal", command=tree.xview)
    hsb.pack(side=tk.BOTTOM, fill=tk.X)
    tree.configure(xscrollcommand=hsb.set)

    tree.pack(expand=True, fill=tk.BOTH)
    root.mainloop()

if __name__ == "__main__":
    create_main_window()
