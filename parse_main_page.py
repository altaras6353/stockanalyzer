from bs4 import BeautifulSoup

def extract_top_vgm_stocks(html_content):
    """
    Extracts Top 5 VGM stock information from HTML content.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    stock_data_list = []

    top_movers_vgm_div = soup.find('div', id='topmovers_vgm')
    if not top_movers_vgm_div:
        # Fallback for slight variations if id is not found, try class (example)
        top_movers_vgm_div = soup.find('div', class_='top_movers_vgm') # Hypothetical class
        if not top_movers_vgm_div:
            print("Error: Could not find div with id='topmovers_vgm' or class='top_movers_vgm'")
            return stock_data_list


    table = top_movers_vgm_div.find('table')
    if not table:
        print("Error: Could not find table within the VGM div")
        return stock_data_list

    tbody = table.find('tbody')
    if not tbody:
        print("Error: Could not find tbody within the table")
        return stock_data_list

    for row in tbody.find_all('tr'):
        company_name = "N/A"
        ticker_symbol = "N/A"
        stock_page_url = "N/A"

        company_name_tag = row.find('th')
        if company_name_tag:
            span_tag = company_name_tag.find('span', title=True)
            if span_tag:
                company_name = span_tag['title']
            else: # Fallback if span[title] not found
                company_name = company_name_tag.get_text(strip=True)


        ticker_cell = row.find('td', class_='alpha')
        if ticker_cell:
            link_tag = ticker_cell.find('a')
            if link_tag and link_tag.has_attr('href'):
                ticker_symbol = link_tag.get_text(strip=True)

                href = link_tag['href'].strip()
                if href.startswith('https://www.zacks.com') or href.startswith('http://www.zacks.com'):
                    stock_page_url = href
                elif href.startswith('//'): # Protocol-relative URL
                    stock_page_url = "https:" + href # Assume https
                elif href.startswith('/'):
                    stock_page_url = "https://www.zacks.com" + href
                else:
                    # Could be an unexpected format, log or handle as error
                    print(f"Warning: Encountered unexpected href format: {href}")
                    stock_page_url = href # Use as is, might fail later
            else: # Fallback if <a> tag is missing
                 raw_text = ticker_cell.get_text(strip=True)
                 if raw_text:
                     ticker_symbol = raw_text.split(' ')[0] # Get first part

        if company_name != "N/A" or ticker_symbol != "N/A": # Add if we found something
            stock_data_list.append({
                "Company Name": company_name,
                "Ticker Symbol": ticker_symbol,
                "Stock Page URL": stock_page_url
            })
        if len(stock_data_list) >= 5: # Ensure we only get top 5 as per original intent
            break

    return stock_data_list

if __name__ == "__main__":
    try:
        with open("main_page.html", "r", encoding="utf-8") as f:
            html_content = f.read()
    except FileNotFoundError:
        print("Error: main_page.html not found.")
        html_content = ""

    if html_content:
        top_stocks = extract_top_vgm_stocks(html_content)
        if top_stocks:
            print("Top VGM Stocks (from local main_page.html):")
            for stock in top_stocks:
                print(f"  Company: {stock['Company Name']}")
                print(f"  Ticker: {stock['Ticker Symbol']}")
                print(f"  URL: {stock['Stock Page URL']}")
                print("-" * 20)
        else:
            print("No stock data extracted from local main_page.html.")
    else:
        print("Could not read HTML content from local main_page.html.")
