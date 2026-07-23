"""
Nifty Next 50 + Nifty Midcap 50 + Gold + Silver Alert
--------------------------------------------------------------------------------
Alerts you when EITHER is true for an instrument (OR logic):
  1) A completed 5-min candle CLOSES above yesterday's HIGH, or below yesterday's LOW
  2) That same candle's volume is a set multiple of the average volume of the
     last N 5-minute candles (real intraday relative volume)

Every alert includes the exact time (IST) the candle closed.

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
from datetime import datetime
import pytz

# ------------------ CONFIG ------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
CHAT_ID = os.environ.get("CHAT_ID", "YOUR_CHAT_ID_HERE")

VOLUME_MULTIPLE = 5.0          # latest completed 5-min candle must be >= 5x the recent avg 5-min volume
CANDLE_LOOKBACK = 20           # how many prior 5-min candles to average over
CHECK_INTERVAL_SECONDS = 300   # check every 5 minutes
IST = pytz.timezone("Asia/Kolkata")

# Nifty Next 50 (ranks 51-100 by market cap)
NIFTY_NEXT_50 = [
    "BAJAJHLDNG.NS", "BRITANNIA.NS", "CGPOWER.NS", "AMBUJACEM.NS", "ABB.NS",
    "INDHOTEL.NS", "CUMMINSIND.NS", "BOSCHLTD.NS", "VEDL.NS", "SHREECEM.NS",
    "SIEMENS.NS", "TATAPOWER.NS", "CHOLAFIN.NS", "BPCL.NS", "HINDZINC.NS",
    "MOTHERSON.NS", "PIDILITIND.NS", "TORNTPHARM.NS", "BANKBARODA.NS", "CANBK.NS",
    "UNIONBANK.NS", "DLF.NS", "PNB.NS", "TVSMOTOR.NS", "UNITDSPR.NS",
    "IOC.NS", "HAL.NS", "PFC.NS", "GAIL.NS", "IRFC.NS",
    "MAZDOCK.NS", "HYUNDAI.NS", "ADANIPOWER.NS", "RECLTD.NS", "LTM.NS",
    "JINDALSTEL.NS", "ZYDUSLIFE.NS", "DIVISLAB.NS", "HDFCAMC.NS", "GODREJCP.NS",
    "VBL.NS", "MUTHOOTFIN.NS", "SOLARINDS.NS", "TATACAP.NS", "LODHA.NS",
    "DMART.NS", "ADANIENSOL.NS", "ADANIGREEN.NS", "TMCV.NS", "ENRIN.NS",
]

# Nifty Midcap 50
NIFTY_MIDCAP_50 = [
    "ASHOKLEY.NS", "BHARATFORG.NS", "COLPAL.NS", "HEROMOTOCO.NS", "MFSL.NS",
    "SRF.NS", "SUPREMEIND.NS", "HINDPETRO.NS", "BHEL.NS", "UPL.NS",
    "LUPIN.NS", "HAVELLS.NS", "MPHASIS.NS", "DABUR.NS", "FEDERALBNK.NS",
    "AUROPHARMA.NS", "OIL.NS", "INDUSINDBK.NS", "PHOENIXLTD.NS", "NMDC.NS",
    "APLAPOLLO.NS", "NHPC.NS", "MARICO.NS", "PRESTIGE.NS", "SUZLON.NS",
    "GODREJPROP.NS", "PERSISTENT.NS", "NAUKRI.NS", "ALKEM.NS", "SBICARD.NS",
    "BSE.NS", "ICICIGI.NS", "GMRAIRPORT.NS", "FORTIS.NS", "COFORGE.NS",
    "YESBANK.NS", "MCX.NS", "POLYCAB.NS", "AUBANK.NS", "DIXON.NS",
    "MANKIND.NS", "WAAREEENER.NS", "PAYTM.NS", "INDUSTOWER.NS", "TIINDIA.NS",
    "POLICYBZR.NS", "LAURUSLABS.NS", "IDFCFIRSTB.NS", "SWIGGY.NS", "NYKAA.NS",
]

# Gold & Silver futures (COMEX, via Yahoo Finance) — have real volume data
COMMODITIES = [
    "GC=F",  # Gold futures
    "SI=F",  # Silver futures
]

WATCHLIST = NIFTY_NEXT_50 + NIFTY_MIDCAP_50 + COMMODITIES
# Note: index constituents change over time — double check against the latest
# official lists before relying on this.
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
        # Daily data -> yesterday's high/low
        daily = yf.Ticker(ticker).history(period="10d", interval="1d")
        if daily.empty or len(daily) < 2:
            print(f"[{ticker}] not enough daily data")
            return

        prev_day = daily.iloc[-2]
        prev_high = prev_day["High"]
        prev_low = prev_day["Low"]

        # Intraday 5-min data
        intraday = yf.Ticker(ticker).history(period="5d", interval="5m")
        if intraday.empty or len(intraday) < CANDLE_LOOKBACK + 2:
            print(f"[{ticker}] not enough intraday data")
            return

        # Use the LAST FULLY COMPLETED 5-min candle (not the one still forming)
        candle = intraday.iloc[-2]
        candle_time = intraday.index[-2]
        # Convert to IST for display
        candle_time_ist = candle_time.tz_convert(IST) if candle_time.tzinfo else IST.localize(candle_time)
        time_str = candle_time_ist.strftime("%d-%b %H:%M")

        close_price = candle["Close"]
        candle_volume = candle["Volume"]

        avg_candle_volume = intraday["Volume"].iloc[-(CANDLE_LOOKBACK + 2):-2].mean()
        vol_ratio = candle_volume / avg_candle_volume if avg_candle_volume else 0
        volume_spike = vol_ratio >= VOLUME_MULTIPLE

        breakout_up = close_price > prev_high
        breakout_down = close_price < prev_low

        print(f"[{ticker}] {time_str} close={close_price:.2f} prevHigh={prev_high:.2f} "
              f"prevLow={prev_low:.2f} volRatio={vol_ratio:.2f}x")

        today_date = candle_time_ist.date()

        if breakout_up:
            key = f"{ticker}-{today_date}-UP"
            if key not in already_alerted:
                send_telegram_message(
                    f"🟢 Breakout UP: {ticker}\n"
                    f"Closed at {close_price:.2f}, above prev day high {prev_high:.2f}\n"
                    f"Candle closed at {time_str} IST"
                )
                already_alerted.add(key)

        if breakout_down:
            key = f"{ticker}-{today_date}-DOWN"
            if key not in already_alerted:
                send_telegram_message(
                    f"🔴 Breakdown: {ticker}\n"
                    f"Closed at {close_price:.2f}, below prev day low {prev_low:.2f}\n"
                    f"Candle closed at {time_str} IST"
                )
                already_alerted.add(key)

        if volume_spike:
            key = f"{ticker}-{today_date}-VOLSPIKE-{candle_time_ist.strftime('%H%M')}"
            if key not in already_alerted:
                send_telegram_message(
                    f"🟡 Volume Spike: {ticker}\n"
                    f"{vol_ratio:.2f}x the last {CANDLE_LOOKBACK} candles' average\n"
                    f"Price: {close_price:.2f}\n"
                    f"Candle closed at {time_str} IST"
                )
                already_alerted.add(key)

    except Exception as e:
        print(f"Error checking {ticker}: {e}")


def main():
    print("Starting Next50 + Midcap50 + Gold/Silver alert monitor. Ctrl+C to stop.")
    while True:
        for ticker in WATCHLIST:
            check_ticker(ticker)
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
