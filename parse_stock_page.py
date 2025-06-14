from bs4 import BeautifulSoup
import re

def extract_stock_ratings(html_content):
    """
    Extracts detailed stock ratings (Value, Growth, Momentum, VGM),
    Zacks Rank, and Company Name from HTML content.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    ratings = {
        'Company Name': None, # New field
        'Zacks Rank': None,
        'Value': None,
        'Growth': None,
        'Momentum': None,
        'VGM': None
    }

    # --- Extract Company Name ---
    # Target Location 1 (Primary): div.quote_summary > header > h1 > a (or similar within quote_ribbon_v2)
    company_name_str = None
    # Try finding within section#quote_ribbon_v2 first as it's a known container
    quote_ribbon_section = soup.find('section', id='quote_ribbon_v2')
    if quote_ribbon_section:
        quote_summary_div = quote_ribbon_section.find('div', class_='quote_summary')
        if quote_summary_div:
            header = quote_summary_div.find('header')
            if header:
                h1 = header.find('h1')
                if h1:
                    link_tag = h1.find('a')
                    if link_tag and link_tag.string:
                        full_text = link_tag.string.strip()
                        # Expected format: "COMPANY NAME (TICKER)"
                        if '(' in full_text and full_text.endswith(')'):
                            company_name_str = full_text.split('(')[0].strip()
                        else:
                            company_name_str = full_text
                        print(f"DEBUG PARSER: Company name from h1>a: '{company_name_str}'")

    ratings['Company Name'] = company_name_str

    # Target Location 2 (Fallback if primary failed): <title> tag
    if not ratings['Company Name']:
        title_tag = soup.find('title')
        if title_tag and title_tag.string:
            title_text = title_tag.string.strip()
            # Example: "International Holding Company PJSC (IHICY) Stock Price, News, Quote & History - Zacks"
            # Heuristic: take the part before the first occurrence of " (" or " - " if they indicate ticker or site name
            parts = re.split(r'\s+\(|\s+-\s+', title_text) # Split by " (" or " - "
            if parts and len(parts) > 0:
                potential_name = parts[0].strip()
                # Avoid setting it if it's just the ticker or too short/generic
                if len(potential_name) > 3 and not potential_name.isupper(): # Simple check
                    ratings['Company Name'] = potential_name
                    print(f"DEBUG PARSER: Company name from title: '{ratings['Company Name']}'")


    # --- Extract Zacks Rank ---
    # (Using existing logic, ensuring it works with updated HTML if quote_ribbon_section is found)
    if quote_ribbon_section:
        rank_summary = quote_ribbon_section.find('div', class_='quote_rank_summary')
        if rank_summary:
            zacks_rank_box = rank_summary.find('div', class_='zr_rankbox', recursive=False)
            if zacks_rank_box and 'composite_group' not in zacks_rank_box.get('class', []):
                rank_view_p = zacks_rank_box.find('p', class_='rank_view')
                if rank_view_p:
                    zacks_rank_text = rank_view_p.get_text(separator='|', strip=True).split('|')[0].strip()
                    ratings['Zacks Rank'] = zacks_rank_text
            elif not ratings['Zacks Rank']:
                all_rank_boxes = rank_summary.find_all('div', class_='zr_rankbox')
                for box in all_rank_boxes:
                    if 'composite_group' not in box.get('class', []):
                        rank_view_p = box.find('p', class_='rank_view')
                        if rank_view_p:
                            title_p = box.find('div', class_='rank_title')
                            if title_p and "Zacks Rank" in title_p.get_text():
                                ratings['Zacks Rank'] = rank_view_p.get_text(separator='|', strip=True).split('|')[0].strip()
                                break

    # --- Extract Style Scores ---
    composite_group_div = None
    if quote_ribbon_section: # Try within quote_ribbon first
        rank_summary_for_style = quote_ribbon_section.find('div', class_='quote_rank_summary')
        if rank_summary_for_style:
            composite_group_div = rank_summary_for_style.find('div', class_='zr_rankbox composite_group')

    if not composite_group_div: # Fallback to global search if not in ribbon
         composite_group_div = soup.find('div', class_='zr_rankbox composite_group')

    if composite_group_div:
        rank_view_p_style = composite_group_div.find('p', class_='rank_view')
        if rank_view_p_style:
            vgm_span = rank_view_p_style.find('span', class_='composite_val_vgm')
            if vgm_span:
                vgm_score_text = vgm_span.get_text(strip=True)
                if vgm_span.next_sibling and "VGM" in vgm_span.next_sibling.strip():
                    ratings['VGM'] = vgm_score_text
            other_score_spans = rank_view_p_style.find_all('span', class_='composite_val')
            for span in other_score_spans:
                if 'composite_val_vgm' in span.get('class', []): continue
                score_value = span.get_text(strip=True)
                next_text_node = span.next_sibling
                if next_text_node and isinstance(next_text_node, str):
                    text_content = next_text_node.strip()
                    if "Value" == text_content: ratings['Value'] = score_value
                    elif "Growth" == text_content: ratings['Growth'] = score_value
                    elif "Momentum" == text_content: ratings['Momentum'] = score_value
    return ratings

if __name__ == "__main__":
    try:
        with open("individual_stock_page.html", "r", encoding="utf-8") as f:
            html_content_for_test = f.read()
    except FileNotFoundError:
        print("Error: individual_stock_page.html not found.")
        html_content_for_test = ""

    if html_content_for_test:
        stock_data = extract_stock_ratings(html_content_for_test)
        if stock_data:
            print("\n--- Extracted Stock Data (from local individual_stock_page.html) ---")
            print(f"  Company Name: {stock_data.get('Company Name')}")
            print(f"  Zacks Rank:   {stock_data.get('Zacks Rank')}")
            print(f"  Value Score:  {stock_data.get('Value')}")
            print(f"  Growth Score: {stock_data.get('Growth')}")
            print(f"  Momentum Score: {stock_data.get('Momentum')}")
            print(f"  VGM Score:    {stock_data.get('VGM')}")
            print("--------------------------------------------------------------------")
        else:
            print("No stock data extracted or an error occurred.")
    else:
        print("Could not read HTML content for test.")
