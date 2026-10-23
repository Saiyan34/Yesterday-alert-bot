"""
Gold + Silver Multi-Timeframe VWAP Alert -> Telegram
--------------------------------------------------------------------------------
Watches ONLY Gold (GC=F) and Silver (SI=F).
For EACH of these timeframes: 1min, 5min, 15min, 30min, 45min, 1h, 4h
  - Builds candles of that size from 1-minute data
  - Calculates a VWAP using only that timeframe's candles
  - Alerts when the latest COMPLETED candle's close is 0.75%+ away from
    that timeframe's VWAP (checked independently per timeframe)

Setup:
1. Create a bot via @BotFather on Telegram -> get BOT_TOKEN
2. Get your chat id via @userinfobot -> get CHAT_ID
3. pip install yfinance requests pytz pandas --break-system-packages
4. Fill in CONFIG below (or set as env vars / GitHub Secrets)
5. Run: python "nifty50 breakout alert.py"
"""

import os
import json
import requests
import yfinance as yf
import pandas as pd

# ------------------ CONFIG ------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
CHAT_ID = os.environ.get("CHAT_ID", "YOUR_CHAT_ID_HERE")

VWAP_DEVIATION_PCT = 0.75   # alert if price is +/- this % vs that timeframe's VWAP

# Timeframe label -> pandas resample rule
TIMEFRAMES = {
    "1min": "1min",
    "5min": "5min",
    "15min": "15min",
    "30min": "30min",
    "45min": "45min",
    "1h": "1h",
    "4h": "4h",
}

WATCHLIST = ["GC=F", "SI=F"]  # Gold futures, Silver futures (COMEX, via Yahoo Finance)

STATE_FILE = "alerted_state.json"
# ---------------------------------------------


def load_state():
    try:
        with open(STATE_FILE, "r") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_state(state_set):
    with open(STATE_FILE, "w") as f:
        json.dump(list(state_set), f)


already_alerted = load_state()


def send_telegram_message(text: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, data={"chat_id": CHAT_ID, "text": text}, timeout=10)
        if resp.status_code != 200:
            print(f"Telegram send failed: {resp.text}")
    except Exception as e:
        print(f"Telegram error: {e}")


def build_candles(raw_1m: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample 1-minute data into bigger candles of the given timeframe."""
    candles = raw_1m.resample(rule).agg({
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    })
    return candles.dropna()


def compute_vwap_at_last_completed(candles: pd.DataFrame):
    """Cumulative VWAP using these candles, evaluated at the last FULLY
    COMPLETED candle (not the one still forming)."""
    if len(candles) < 2:
        return None, None, None

    completed = candles.iloc[-2]
    completed_time = candles.index[-2]

    up_to_completed = candles.loc[:completed_time]
    typical_price = (up_to_completed["High"] + up_to_completed["Low"] + up_to_completed["Close"]) / 3
    cum_pv = (typical_price * up_to_completed["Volume"]).cumsum()
    cum_vol = up_to_completed["Volume"].cumsum()

    if cum_vol.iloc[-1] == 0:
        return None, None, None

    vwap = (cum_pv / cum_vol).iloc[-1]
    close_price = completed["Close"]
    return close_price, vwap, completed_time


def check_ticker(ticker: str):
    try:
        raw_1m = yf.Ticker(ticker).history(period="5d", interval="1m")
        if raw_1m.empty:
            print(f"[{ticker}] no 1-min data")
            return

        for tf_label, rule in TIMEFRAMES.items():
            candles = build_candles(raw_1m, rule)
            close_price, vwap, candle_time = compute_vwap_at_last_completed(candles)

            if vwap is None:
                print(f"[{ticker}] {tf_label}: not enough data yet")
                continue

            deviation_pct = ((close_price - vwap) / vwap) * 100
            time_str = candle_time.strftime("%d-%b %H:%M")

            print(f"[{ticker}] {tf_label} @ {time_str} close={close_price:.2f} "
                  f"vwap={vwap:.2f} dev={deviation_pct:.2f}%")

            if deviation_pct >= VWAP_DEVIATION_PCT:
                key = f"{ticker}-{tf_label}-UP-{candle_time.isoformat()}"
                if key not in already_alerted:
                    send_telegram_message(
                        f"🟢 [{tf_label}] {ticker} {VWAP_DEVIATION_PCT}%+ Above VWAP\n"
                        f"Price {close_price:.2f} is {deviation_pct:+.2f}% vs VWAP {vwap:.2f}\n"
                        f"Candle closed at {time_str}"
                    )
                    already_alerted.add(key)

            elif deviation_pct <= -VWAP_DEVIATION_PCT:
                key = f"{ticker}-{tf_label}-DOWN-{candle_time.isoformat()}"
                if key not in already_alerted:
                    send_telegram_message(
                        f"🔴 [{tf_label}] {ticker} {VWAP_DEVIATION_PCT}%+ Below VWAP\n"
                        f"Price {close_price:.2f} is {deviation_pct:+.2f}% vs VWAP {vwap:.2f}\n"
                        f"Candle closed at {time_str}"
                    )
                    already_alerted.add(key)

    except Exception as e:
        print(f"Error checking {ticker}: {e}")


def main():
    print("Running Gold/Silver multi-timeframe VWAP check...")
    for ticker in WATCHLIST:
        check_ticker(ticker)
    save_state(already_alerted)
    print("Done. State saved.")


if __name__ == "__main__":
    main()

