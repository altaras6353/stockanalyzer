from bs4 import BeautifulSoup

def extract_top_vgm_stocks(html_content):
    """
    Extracts Top 5 VGM stock information from HTML content.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    stock_data_list = []

    top_movers_vgm_div = soup.find('div', id='topmovers_vgm')
    if not top_movers_vgm_div:
        print("Error: Could not find div with id='topmovers_vgm'")
        return stock_data_list

    table = top_movers_vgm_div.find('table')
    if not table:
        print("Error: Could not find table within div#topmovers_vgm")
        return stock_data_list

    tbody = table.find('tbody')
    if not tbody:
        print("Error: Could not find tbody within the table")
        return stock_data_list

    for row in tbody.find_all('tr'):
        # Company Name
        company_name_tag = row.find('th')
        if company_name_tag:
            span_tag = company_name_tag.find('span', title=True)
            if span_tag:
                company_name = span_tag['title']
            else:
                company_name = "N/A"
        else:
            company_name = "N/A"

        # Ticker Symbol and Stock Page URL
        ticker_symbol = "N/A"
        stock_page_url = "N/A"

        # First td with class="alpha" should contain the ticker
        ticker_cell = row.find('td', class_='alpha')
        if ticker_cell:
            link_tag = ticker_cell.find('a')
            if link_tag and link_tag.has_attr('href'):
                # Extract ticker: text content of the <a> tag
                ticker_symbol = link_tag.get_text(strip=True)

                # Extract URL
                href = link_tag['href']
                if href.startswith('/'):
                    stock_page_url = "https://www.zacks.com" + href
                else:
                    stock_page_url = href
            else: # Fallback if <a> tag is missing, try to get text directly (less robust)
                 ticker_symbol = ticker_cell.get_text(strip=True).split(' ')[0]


        stock_data_list.append({
            "Company Name": company_name,
            "Ticker Symbol": ticker_symbol,
            "Stock Page URL": stock_page_url
        })

    return stock_data_list

if __name__ == "__main__":
    try:
        with open("main_page.html", "r", encoding="utf-8") as f:
            html_content = f.read()
    except FileNotFoundError:
        print("Error: main_page.html not found.")
        html_content = "" # Ensure html_content is defined

    if html_content:
        top_stocks = extract_top_vgm_stocks(html_content)
        if top_stocks:
            print("Top 5 VGM Stocks:")
            for stock in top_stocks:
                print(f"  Company: {stock['Company Name']}")
                print(f"  Ticker: {stock['Ticker Symbol']}")
                print(f"  URL: {stock['Stock Page URL']}")
                print("-" * 20)
        else:
            print("No stock data extracted.")
    else:
        print("Could not read HTML content.")
