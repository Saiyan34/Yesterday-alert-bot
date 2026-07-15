"""
Nifty 50 Alert: Previous Day High/Low Breakout OR Intraday Volume Spike -> Telegram
------------------------------------------------------------------------------------
Alerts you when EITHER is true for a stock (OR logic):
  1) Price crosses above yesterday's HIGH, or below yesterday's LOW
  2) The latest 5-minute candle's volume is a set multiple of the average
     volume of the last N 5-minute candles (real intraday relative volume,
     not a full-day-vs-daily-average comparison)

Setup:
1. Create a bot via @BotFather on Telegram -> get BOT_TOKEN
2. Get your chat id via @userinfobot -> get CHAT_ID
3. pip install yfinance requests --break-system-packages
4. Fill in the CONFIG section below (or set as env vars on Railway)
5. Run: python nifty50_breakout_alert.py
"""

import os
import time
import requests
import yfinance as yf

# ------------------ CONFIG ------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
CHAT_ID = os.environ.get("CHAT_ID", "YOUR_CHAT_ID_HERE")

VOLUME_MULTIPLE = 5.0          # latest 5-min candle must be >= 5x the recent avg 5-min volume
CANDLE_LOOKBACK = 20           # how many prior 5-min candles to average over
CHECK_INTERVAL_SECONDS = 300   # check every 5 minutes

# Nifty 50 tickers (Yahoo Finance format, .NS = NSE)
NIFTY_50 = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
    "HINDUNILVR.NS", "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "BAJFINANCE.NS",
    "KOTAKBANK.NS", "LT.NS", "AXISBANK.NS", "ASIANPAINT.NS", "MARUTI.NS",
    "SUNPHARMA.NS", "TITAN.NS", "ULTRACEMCO.NS", "NESTLEIND.NS", "WIPRO.NS",
    "ADANIENT.NS", "ADANIPORTS.NS", "BAJAJFINSV.NS", "HCLTECH.NS", "NTPC.NS",
    "POWERGRID.NS", "M&M.NS", "TATAMOTORS.NS", "TATASTEEL.NS", "JSWSTEEL.NS",
    "ONGC.NS", "COALINDIA.NS", "GRASIM.NS", "INDUSINDBK.NS", "TECHM.NS",
    "HINDALCO.NS", "CIPLA.NS", "DRREDDY.NS", "EICHERMOT.NS", "BRITANNIA.NS",
    "APOLLOHOSP.NS", "DIVISLAB.NS", "BPCL.NS", "HEROMOTOCO.NS", "SBILIFE.NS",
    "HDFCLIFE.NS", "BAJAJ-AUTO.NS", "SHRIRAMFIN.NS", "TATACONSUM.NS",
    "UPL.NS", "LTIM.BO",
]
# Note: index constituents change over time — double check against the latest
# official Nifty 50 list before relying on this.
# ---------------------------------------------

already_alerted = set()  # avoids repeat alerts same day/direction


def send_telegram_message(text: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, data={"chat_id": CHAT_ID, "text": text}, timeout=10)
        if resp.status_code != 200:
            print(f"Telegram send failed: {resp.text}")
    except Exception as e:
        print(f"Telegram error: {e}")


def check_ticker(ticker: str):
    try:
        # Daily data -> used only for yesterday's high/low
        daily = yf.Ticker(ticker).history(period="10d", interval="1d")
        if daily.empty or len(daily) < 2:
            print(f"[{ticker}] not enough daily data")
            return

        prev_day = daily.iloc[-2]
        prev_high = prev_day["High"]
        prev_low = prev_day["Low"]

        # Intraday 5-min data -> used for current price + real intraday volume spike
        intraday = yf.Ticker(ticker).history(period="5d", interval="5m")
        if intraday.empty or len(intraday) < CANDLE_LOOKBACK + 1:
            print(f"[{ticker}] not enough intraday data")
            return

        current_candle = intraday.iloc[-1]
        current_price = current_candle["Close"]
        current_volume = current_candle["Volume"]

        # Average volume of the last N candles, excluding the current one
        avg_candle_volume = intraday["Volume"].iloc[-(CANDLE_LOOKBACK + 1):-1].mean()
        vol_ratio = current_volume / avg_candle_volume if avg_candle_volume else 0
        volume_spike = vol_ratio >= VOLUME_MULTIPLE

        breakout_up = current_price > prev_high
        breakout_down = current_price < prev_low

        print(f"[{ticker}] price={current_price:.2f} prevHigh={prev_high:.2f} "
              f"prevLow={prev_low:.2f} 5minVolRatio={vol_ratio:.2f}x")

        today_date = intraday.index[-1].date()

        # --- OR logic: any single condition triggers its own alert ---
        if breakout_up:
            key = f"{ticker}-{today_date}-UP"
            if key not in already_alerted:
                send_telegram_message(
                    f"Breakout UP: {ticker}\n"
                    f"Price {current_price:.2f} crossed prev day high {prev_high:.2f}"
                )
                already_alerted.add(key)

        if breakout_down:
            key = f"{ticker}-{today_date}-DOWN"
            if key not in already_alerted:
                send_telegram_message(
                    f"Breakdown: {ticker}\n"
                    f"Price {current_price:.2f} crossed below prev day low {prev_low:.2f}"
                )
                already_alerted.add(key)

        if volume_spike:
            key = f"{ticker}-{today_date}-VOLSPIKE-{intraday.index[-1].strftime('%H%M')}"
            if key not in already_alerted:
                send_telegram_message(
                    f"Volume Spike: {ticker}\n"
                    f"Latest 5-min volume is {vol_ratio:.2f}x the last {CANDLE_LOOKBACK} candles' average\n"
                    f"Price: {current_price:.2f}"
                )
                already_alerted.add(key)

    except Exception as e:
        print(f"Error checking {ticker}: {e}")


def main():
    print("Starting Nifty 50 breakout OR volume-spike alert monitor. Ctrl+C to stop.")
    while True:
        for ticker in NIFTY_50:
            check_ticker(ticker)
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
