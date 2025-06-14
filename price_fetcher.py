import yfinance as yf
import pandas as pd # yfinance often returns pandas Series/DataFrames

def get_current_price(ticker_symbol: str) -> float | None:
    """
    Fetches the most recent closing price for a given stock ticker.
    Uses "2d" history to ensure data availability even during market hours or for thinly traded stocks.
    """
    print(f"Fetching price for {ticker_symbol}...")
    try:
        ticker = yf.Ticker(ticker_symbol)
        # Using "2d" to get at least one closing price.
        # For very active stocks, "1d" might be enough if market is closed.
        # If market is open, "1d" might not have a 'Close' for the current day yet.
        # "5d" is also common to ensure data. Let's stick to 2d for now.
        hist = ticker.history(period="2d", interval="1d")

        if hist.empty:
            print(f"Warning: No history data returned for {ticker_symbol}.")
            return None

        # Get the last available closing price
        # .iloc[-1] gets the last row.
        # If running during market hours, the last 'Close' might be from previous day.
        # If market just closed, it should be today's close.
        if 'Close' in hist.columns and not hist['Close'].empty:
            current_price = hist['Close'].iloc[-1]
            print(f"Successfully fetched price for {ticker_symbol}: {current_price}")
            return float(current_price)
        else:
            print(f"Warning: 'Close' column not found or empty in history for {ticker_symbol}.")
            # Attempt to get current price using 'fast_info' as a fallback for very recent price
            # This might be more up-to-date if market is open
            try:
                fast_info = ticker.fast_info
                if fast_info and 'lastPrice' in fast_info:
                    current_price = fast_info.lastPrice
                    print(f"Fallback to fast_info: Fetched lastPrice for {ticker_symbol}: {current_price}")
                    return float(current_price)
                else:
                    print(f"Warning: fast_info also did not provide a price for {ticker_symbol}.")
                    return None
            except Exception as e_fast_info:
                print(f"Error fetching fast_info for {ticker_symbol}: {e_fast_info}")
                return None

    except Exception as e:
        print(f"Error fetching price for {ticker_symbol}: {e}")
        return None

if __name__ == "__main__":
    print("--- Testing Price Fetcher ---")

    test_tickers = ["AAPL", "MSFT", "GOOG"] # Common valid tickers
    print(f"\n--- Testing valid tickers: {test_tickers} ---")
    for ticker_str in test_tickers:
        price = get_current_price(ticker_str)
        if price is not None:
            print(f"The current price for {ticker_str} is: ${price:.2f}")
        else:
            print(f"Could not retrieve price for {ticker_str}.")
        print("-" * 20)

    invalid_ticker = "INVALIDTICKERXYZASX" # A clearly invalid ticker
    print(f"\n--- Testing invalid ticker: {invalid_ticker} ---")
    price = get_current_price(invalid_ticker)
    if price is not None:
        print(f"The current price for {invalid_ticker} is: ${price:.2f} (UNEXPECTED!)")
    else:
        print(f"Could not retrieve price for {invalid_ticker}. (Expected)")
    print("-" * 20)

    # Test a ticker that might have issues or is less common (example)
    # Using a real but perhaps less common one, or one that might have data issues sometimes.
    # For now, let's assume the common ones are sufficient to test yfinance functionality.
    # another_ticker = "BRK-A" # Berkshire Hathaway Class A
    # print(f"\n--- Testing another ticker: {another_ticker} ---")
    # price = get_current_price(another_ticker)
    # if price is not None:
    #     print(f"The current price for {another_ticker} is: ${price:.2f}")
    # else:
    #     print(f"Could not retrieve price for {another_ticker}.")
    # print("-" * 20)

    print("\n--- Price Fetcher Test Complete ---")
