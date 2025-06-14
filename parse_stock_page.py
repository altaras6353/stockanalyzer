from bs4 import BeautifulSoup
import re

def extract_stock_ratings(html_content):
    """
    Extracts detailed stock ratings (Value, Growth, Momentum, VGM)
    and Zacks Rank from HTML content.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    ratings = {
        'Zacks Rank': None,
        'Value': None,
        'Growth': None,
        'Momentum': None,
        'VGM': None
    }

    # --- Extract Zacks Rank ---
    # Based on structure: section#quote_ribbon_v2 -> div.quote_rank_summary -> div.zr_rankbox (first one) -> p.rank_view
    quote_ribbon = soup.find('section', id='quote_ribbon_v2')
    if quote_ribbon:
        rank_summary = quote_ribbon.find('div', class_='quote_rank_summary')
        if rank_summary:
            # The Zacks Rank is usually in the first zr_rankbox that is NOT a composite_group
            zacks_rank_box = rank_summary.find('div', class_='zr_rankbox', recursive=False) # direct child
            if zacks_rank_box and 'composite_group' not in zacks_rank_box.get('class', []):
                rank_view_p = zacks_rank_box.find('p', class_='rank_view')
                if rank_view_p:
                    # Get all text from rank_view_p, then take the first part before any child span
                    # This handles cases like "1-Strong Buy<span class="sr-only"> of 5</span>"
                    zacks_rank_text = rank_view_p.get_text(separator='|', strip=True).split('|')[0].strip()
                    ratings['Zacks Rank'] = zacks_rank_text
            # Fallback if the above structure is not found (e.g. our simplified test HTML)
            elif not ratings['Zacks Rank']: # if not found by specific path
                all_rank_boxes = rank_summary.find_all('div', class_='zr_rankbox')
                for box in all_rank_boxes:
                    if 'composite_group' not in box.get('class', []):
                        rank_view_p = box.find('p', class_='rank_view')
                        if rank_view_p:
                            title_p = box.find('div', class_='rank_title') # Check title for "Zacks Rank"
                            if title_p and "Zacks Rank" in title_p.get_text():
                                zacks_rank_text = rank_view_p.get_text(separator='|', strip=True).split('|')[0].strip()
                                ratings['Zacks Rank'] = zacks_rank_text
                                break

    # --- Extract Style Scores ---
    # Find the div for composite scores (Style Scores)
    composite_group_div = soup.find('div', class_='zr_rankbox composite_group')
    if not composite_group_div:
        # Try finding within quote_ribbon if not found globally (as per updated HTML structure)
        if rank_summary:
             composite_group_div = rank_summary.find('div', class_='zr_rankbox composite_group')

    if composite_group_div:
        rank_view_p_style = composite_group_div.find('p', class_='rank_view')
        if rank_view_p_style:
            # VGM Score
            vgm_span = rank_view_p_style.find('span', class_='composite_val_vgm')
            if vgm_span:
                vgm_score_text = vgm_span.get_text(strip=True)
                if vgm_span.next_sibling and "VGM" in vgm_span.next_sibling.strip():
                    ratings['VGM'] = vgm_score_text

            # Value, Growth, Momentum Scores
            other_score_spans = rank_view_p_style.find_all('span', class_='composite_val')
            for span in other_score_spans:
                if 'composite_val_vgm' in span.get('class', []): # Already handled
                    continue
                score_value = span.get_text(strip=True)
                next_text_node = span.next_sibling
                if next_text_node and isinstance(next_text_node, str):
                    text_content = next_text_node.strip()
                    if "Value" == text_content: # Exact match after strip
                        ratings['Value'] = score_value
                    elif "Growth" == text_content:
                        ratings['Growth'] = score_value
                    elif "Momentum" == text_content:
                        ratings['Momentum'] = score_value
    return ratings

if __name__ == "__main__":
    try:
        with open("individual_stock_page.html", "r", encoding="utf-8") as f:
            html_content_for_test = f.read()
    except FileNotFoundError:
        print("Error: individual_stock_page.html not found.")
        html_content_for_test = ""

    if html_content_for_test:
        stock_ratings = extract_stock_ratings(html_content_for_test)
        if stock_ratings:
            print("Extracted Stock Ratings (including Zacks Rank):")
            print(stock_ratings)
        else:
            print("No stock ratings extracted or an error occurred.")
    else:
        print("Could not read HTML content for test.")
