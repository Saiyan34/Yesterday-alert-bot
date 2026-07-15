"""
Nifty 50 Alert: Previous Day High/Low Breakout + Volume Spike (AND) -> Telegram
--------------------------------------------------------------------------------
Alerts you ONLY when BOTH are true for a stock:
  1) Price crosses above yesterday's HIGH, or below yesterday's LOW
  2) Today's volume is above a set multiple of its recent average volume

Setup:
1. Create a bot via @BotFather on Telegram -> get BOT_TOKEN
2. Get your chat id via @userinfobot -> get CHAT_ID
3. pip install yfinance requests --break-system-packages
4. Fill in the CONFIG section below
5. Run: python nifty50_breakout_alert.py
   (Keep it running, or schedule via cron/Task Scheduler during market hours)
"""

import os
import time
import requests
import yfinance as yf

# ------------------ CONFIG ------------------
# Reads from environment variables (set these in Railway) so you never
# have to put your real token/chat ID in the code itself.
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
CHAT_ID = os.environ.get("CHAT_ID", "YOUR_CHAT_ID_HERE")

VOLUME_MULTIPLE = 2.0          # today's volume must be >= 2x average to count as "spike"
AVG_WINDOW_DAYS = 20           # window for the average volume
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
    "UPL.NS", "LTIM.NS",
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
        data = yf.Ticker(ticker).history(period=f"{AVG_WINDOW_DAYS + 5}d")
        if data.empty or len(data) < AVG_WINDOW_DAYS + 2:
            print(f"[{ticker}] not enough data")
            return

        prev_day = data.iloc[-2]      # yesterday's candle
        today = data.iloc[-1]         # today's (in-progress or latest) candle

        prev_high = prev_day["High"]
        prev_low = prev_day["Low"]
        current_price = today["Close"]

        avg_volume = data["Volume"][-(AVG_WINDOW_DAYS + 1):-1].mean()
        today_volume = today["Volume"]
        vol_ratio = today_volume / avg_volume if avg_volume else 0
        volume_spike = vol_ratio >= VOLUME_MULTIPLE

        breakout_up = current_price > prev_high
        breakout_down = current_price < prev_low

        print(f"[{ticker}] price={current_price:.2f} prevHigh={prev_high:.2f} "
              f"prevLow={prev_low:.2f} volRatio={vol_ratio:.2f}x")

        today_date = data.index[-1].date()

        if breakout_up and volume_spike:
            key = f"{ticker}-{today_date}-UP"
            if key not in already_alerted:
                msg = (
                    f"📈 Breakout UP: {ticker}\n"
                    f"Price {current_price:.2f} crossed prev day high {prev_high:.2f}\n"
                    f"Volume {vol_ratio:.2f}x average (threshold {VOLUME_MULTIPLE}x)"
                )
                send_telegram_message(msg)
                already_alerted.add(key)

        if breakout_down and volume_spike:
            key = f"{ticker}-{today_date}-DOWN"
            if key not in already_alerted:
                msg = (
                    f"📉 Breakdown: {ticker}\n"
                    f"Price {current_price:.2f} crossed below prev day low {prev_low:.2f}\n"
                    f"Volume {vol_ratio:.2f}x average (threshold {VOLUME_MULTIPLE}x)"
                )
                send_telegram_message(msg)
                already_alerted.add(key)

    except Exception as e:
        print(f"Error checking {ticker}: {e}")


def main():
    print("Starting Nifty 50 breakout + volume alert monitor. Ctrl+C to stop.")
    while True:
        for ticker in NIFTY_50:
            check_ticker(ticker)
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
