import datetime

def process_stock_data(stock_data_list):
  """
  Processes a list of stock data.

  Args:
    stock_data_list: A list of dictionaries, where each dictionary
                     represents stock data for a company.
  """
  current_timestamp = datetime.datetime.now()
  formatted_timestamp = current_timestamp.strftime("%Y-%m-%d %H:%M:%S")
  # print(f"Data processed at: {formatted_timestamp}") # Keep or remove based on final requirements

  # print(f"Received stock data for {len(stock_data_list)} stocks.") # Keep or remove

  header = "Timestamp           | Company Name         | Ticker | Value | Growth | Momentum | VGM"
  table_rows = [header]

  for stock in stock_data_list:
    # Using f-strings with padding for alignment. Adjust padding as needed.
    # Assuming 'Value', 'Growth', 'Momentum', 'VGM' will be available in stock dict later.
    # Using placeholders like "N/A" for now.
    row_string = (
        f"{formatted_timestamp:<19} | "
        f"{stock.get('Company', 'N/A'):<20} | "
        f"{stock.get('Ticker', 'N/A'):<6} | "
        f"{stock.get('value_rating', 'N/A'):<5} | "
        f"{stock.get('growth_rating', 'N/A'):<6} | "
        f"{stock.get('momentum_rating', 'N/A'):<8} | "
        f"{stock.get('vgm_rating', 'N/A'):<3}"
    )
    table_rows.append(row_string)

  return "\n".join(table_rows)

if __name__ == '__main__':
  # This section demonstrates how to use process_stock_data and display its output.
  # Example usage with dummy data:
  dummy_data = [
      {'Company': 'Alpha Inc.', 'Ticker': 'ALPH', 'Price': 150.00, 'Change': '+2.50', '% Change': '+1.69%', 'value_rating': 'A', 'growth_rating': 'B', 'momentum_rating': 'A', 'vgm_rating': 'A'},
      {'Company': 'Beta Corp.', 'Ticker': 'BETA', 'Price': 75.50, 'Change': '-0.75', '% Change': '-0.98%', 'value_rating': 'C', 'growth_rating': 'C', 'momentum_rating': 'D', 'vgm_rating': 'C'},
      {'Company': 'Gamma Ltd.', 'Ticker': 'GAMM', 'Price': 220.25, 'Change': '+5.10', '% Change': '+2.37%', 'value_rating': 'B', 'growth_rating': 'A', 'momentum_rating': 'B', 'vgm_rating': 'B'}
  ]
  output_table = process_stock_data(dummy_data)
  print("Generated Stock Report:")
  print(output_table)
