from bs4 import BeautifulSoup
import re

def extract_stock_ratings(html_content):
    """
    Extracts detailed stock ratings (Value, Growth, Momentum, VGM) from HTML content.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    ratings = {
        'Value': None,
        'Growth': None,
        'Momentum': None,
        'VGM': None
    }

    # Find the main div for composite scores
    composite_group_div = soup.find('div', class_='zr_rankbox composite_group')
    if not composite_group_div:
        print("Error: Could not find div with class 'zr_rankbox composite_group'")
        return ratings

    # Find the p tag with class 'rank_view' containing the scores
    rank_view_p = composite_group_div.find('p', class_='rank_view')
    if not rank_view_p:
        print("Error: Could not find p with class 'rank_view' in 'composite_group' div")
        return ratings

    # Iterate through all elements within rank_view_p to find scores
    # We look for a structure like: <span class="composite_val">GRADE</span>&nbsp;NAME

    # VGM Score (has a slightly different class for the span)
    vgm_span = rank_view_p.find('span', class_='composite_val_vgm')
    if vgm_span:
        vgm_score_text = vgm_span.get_text(strip=True)
        # Check if "VGM" text node follows, usually after &nbsp;
        if vgm_span.next_sibling and "VGM" in vgm_span.next_sibling.get_text(strip=True):
             ratings['VGM'] = vgm_score_text
        # Fallback if structure is slightly different, e.g. if "VGM" is part of a sibling span
        elif vgm_span.find_next_sibling(string=re.compile(r"VGM")):
            ratings['VGM'] = vgm_score_text


    # Value, Growth, Momentum Scores
    # These have class 'composite_val' but not 'composite_val_vgm'
    # We find all such spans and then look at their next sibling text node to identify them.
    other_score_spans = rank_view_p.find_all('span', class_='composite_val')

    for span in other_score_spans:
        # Skip the VGM span if it was also caught by this broader search
        if 'composite_val_vgm' in span.get('class', []):
            continue

        score_value = span.get_text(strip=True)
        next_text_node = span.next_sibling

        if next_text_node and isinstance(next_text_node, str):
            text_content = next_text_node.strip()
            if "Value" in text_content:
                ratings['Value'] = score_value
            elif "Growth" in text_content:
                ratings['Growth'] = score_value
            elif "Momentum" in text_content:
                ratings['Momentum'] = score_value

    # A check if any score is still None and try a more direct sibling search if needed
    # This handles cases where the text node might not be immediate due to whitespace or other tags
    if ratings['Value'] is None:
        value_span = rank_view_p.find('span', class_='composite_val', string=re.compile(r"^[A-F]$"))
        if value_span and value_span.find_next(string=re.compile(r"Value")):
             ratings['Value'] = value_span.get_text(strip=True)

    if ratings['Growth'] is None:
        growth_span = rank_view_p.find('span', class_='composite_val', string=re.compile(r"^[A-F]$"))
        # Ensure we are not re-picking Value by checking its next sibling
        if growth_span and growth_span.find_next(string=re.compile(r"Growth")) and not ("Value" in growth_span.find_next(string=re.compile(r"Growth")).previous_sibling.previous_sibling.text):
             ratings['Growth'] = growth_span.get_text(strip=True)
             # This logic gets complicated quickly. A better way for multiple items:
             # Iterate all spans and their subsequent text nodes more systematically.

    # Let's refine the general score extraction for Value, Growth, Momentum
    # to be more robust like the VGM one or the initial loop.
    # The initial loop is generally good if the structure is consistent.
    # The sample HTML has: <span class="composite_val">A</span>&nbsp;Value
    # So, `span.next_sibling` should be the text node containing "&nbsp;Value"

    # Re-evaluating the loop for Value, Growth, Momentum for clarity and robustness
    # The first loop for `other_score_spans` should work given the sample HTML.
    # The key is that `span.next_sibling` contains the text like ' Value', ' Growth'.

    # Let's ensure the previous loop's logic is sound for the sample.
    # <span class="composite_val">A</span>&nbsp;Value
    # span.get_text(strip=True) -> "A"
    # span.next_sibling -> NavigableString " Value" (after strip()) or " Value" (with &nbsp;)
    # The .strip() on text_content should handle the &nbsp; correctly.

    return ratings

if __name__ == "__main__":
    try:
        with open("individual_stock_page.html", "r", encoding="utf-8") as f:
            html_content = f.read()
    except FileNotFoundError:
        print("Error: individual_stock_page.html not found.")
        html_content = ""

    if html_content:
        stock_ratings = extract_stock_ratings(html_content)
        if stock_ratings:
            print("Extracted Stock Ratings:")
            print(stock_ratings)
        else:
            print("No stock ratings extracted or an error occurred.")
    else:
        print("Could not read HTML content.")
