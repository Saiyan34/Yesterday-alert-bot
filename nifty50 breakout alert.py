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
SWING_LOOKBACK_DAYS = 10       # swing high/low = highest/lowest over this many days

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

# Gold & Silver futures (COMEX, via Yahoo Finance). These have real volume
# data, unlike spot forex-style tickers (XAUUSD=X etc.) which usually don't.
# Note: this tracks international/COMEX prices, not MCX (India) prices.
COMMODITIES = [
    "GC=F",  # Gold futures
    "SI=F",  # Silver futures
]

WATCHLIST = NIFTY_50 + COMMODITIES
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
        # Daily data -> used for yesterday's high/low AND swing high/low
        daily = yf.Ticker(ticker).history(period=f"{SWING_LOOKBACK_DAYS + 10}d", interval="1d")
        if daily.empty or len(daily) < SWING_LOOKBACK_DAYS + 2:
            print(f"[{ticker}] not enough daily data")
            return

        prev_day = daily.iloc[-2]
        prev_high = prev_day["High"]
        prev_low = prev_day["Low"]

        # Swing high/low: highest high & lowest low over the last N days, excluding today
        swing_window = daily.iloc[-(SWING_LOOKBACK_DAYS + 1):-1]
        swing_high = swing_window["High"].max()
        swing_low = swing_window["Low"].min()

        # Weekly data -> previous completed week's high/low
        weekly = yf.Ticker(ticker).history(period="6mo", interval="1wk")
        weekly_high = weekly_low = None
        if not weekly.empty and len(weekly) >= 2:
            prev_week = weekly.iloc[-2]
            weekly_high = prev_week["High"]
            weekly_low = prev_week["Low"]

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

        swing_breakout_up = current_price > swing_high
        swing_breakout_down = current_price < swing_low

        weekly_breakout_up = weekly_high is not None and current_price > weekly_high
        weekly_breakout_down = weekly_low is not None and current_price < weekly_low

        print(f"[{ticker}] price={current_price:.2f} prevHigh={prev_high:.2f} "
              f"prevLow={prev_low:.2f} swingHigh={swing_high:.2f} swingLow={swing_low:.2f} "
              f"5minVolRatio={vol_ratio:.2f}x")

        today_date = intraday.index[-1].date()

        # --- OR logic: any single condition triggers its own alert ---
        if breakout_up:
            key = f"{ticker}-{today_date}-UP"
            if key not in already_alerted:
                send_telegram_message(
                    f"🟢 Breakout UP: {ticker}\n"
                    f"Price {current_price:.2f} crossed prev day high {prev_high:.2f}"
                )
                already_alerted.add(key)

        if breakout_down:
            key = f"{ticker}-{today_date}-DOWN"
            if key not in already_alerted:
                send_telegram_message(
                    f"🔴 Breakdown: {ticker}\n"
                    f"Price {current_price:.2f} crossed below prev day low {prev_low:.2f}"
                )
                already_alerted.add(key)

        if swing_breakout_up:
            key = f"{ticker}-{today_date}-SWINGUP"
            if key not in already_alerted:
                send_telegram_message(
                    f"🟢 Swing High Breakout: {ticker}\n"
                    f"Price {current_price:.2f} crossed {SWING_LOOKBACK_DAYS}-day swing high {swing_high:.2f}"
                )
                already_alerted.add(key)

        if swing_breakout_down:
            key = f"{ticker}-{today_date}-SWINGDOWN"
            if key not in already_alerted:
                send_telegram_message(
                    f"🔴 Swing Low Breakdown: {ticker}\n"
                    f"Price {current_price:.2f} crossed below {SWING_LOOKBACK_DAYS}-day swing low {swing_low:.2f}"
                )
                already_alerted.add(key)

        if weekly_breakout_up:
            key = f"{ticker}-{today_date}-WEEKUP"
            if key not in already_alerted:
                send_telegram_message(
                    f"🟢 Weekly High Breakout: {ticker}\n"
                    f"Price {current_price:.2f} crossed previous week's high {weekly_high:.2f}"
                )
                already_alerted.add(key)

        if weekly_breakout_down:
            key = f"{ticker}-{today_date}-WEEKDOWN"
            if key not in already_alerted:
                send_telegram_message(
                    f"🔴 Weekly Low Breakdown: {ticker}\n"
                    f"Price {current_price:.2f} crossed below previous week's low {weekly_low:.2f}"
                )
                already_alerted.add(key)

        if volume_spike:
            key = f"{ticker}-{today_date}-VOLSPIKE-{intraday.index[-1].strftime('%H%M')}"
            if key not in already_alerted:
                send_telegram_message(
                    f"🟡 Volume Spike: {ticker}\n"
                    f"Latest 5-min volume is {vol_ratio:.2f}x the last {CANDLE_LOOKBACK} candles' average\n"
                    f"Price: {current_price:.2f}"
                )
                already_alerted.add(key)

    except Exception as e:
        print(f"Error checking {ticker}: {e}")


def main():
    print("Starting Nifty 50 breakout OR volume-spike alert monitor. Ctrl+C to stop.")
    while True:
        for ticker in WATCHLIST:
            check_ticker(ticker)
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
