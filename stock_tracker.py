import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from datetime import date, timedelta, datetime, time as dt_time
import schedule
import threading
import time
import pytz
import os
from dotenv import load_dotenv

# ------------------- Load environment -------------------
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ------------------- Telegram function -------------------
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        st.write(f"⚠️ Telegram send failed: {e}")

# ------------------- Utility -------------------
def fetch_html(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.text

@st.cache_data
def get_us_top50():
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    html = fetch_html(url)
    tables = pd.read_html(html)
    return tables[0]["Symbol"].tolist()[:50]

@st.cache_data
def get_india_top50():
    url = "https://en.wikipedia.org/wiki/NIFTY_50"
    html = fetch_html(url)
    tables = pd.read_html(html)
    table = None
    for t in tables:
        if any(col in t.columns for col in ["Symbol", "Company Name", "Ticker"]):
            table = t
            break
    if table is None:
        st.error("⚠️ Could not find NIFTY 50 table on Wikipedia.")
        return []
    col_name = None
    for c in ["Symbol", "Ticker", "Company Name"]:
        if c in table.columns:
            col_name = c
            break
    if col_name is None:
        st.error("⚠️ No usable ticker column found in NIFTY 50 table.")
        return []
    return table[col_name].astype(str).apply(lambda x: x + ".NS").tolist()[:50]

# ------------------- Streamlit UI -------------------
st.title("📈 Stock Tracker - US & India")
exchange = st.radio("Select Exchange", ["US", "India"])
start_date = st.date_input("Start Date", date(2024, 1, 1))
end_date = st.date_input("End Date", date.today())

drop_threshold = st.slider("Drop Alert Threshold (%)", -10.0, 0.0, -5.0, step=0.5)
gain_threshold = st.slider("Gain Alert Threshold (%)", 0.0, 10.0, 5.0, step=0.5)

tickers = get_us_top50() if exchange == "US" else get_india_top50()
end_date_plus = end_date + timedelta(days=1)

st.subheader(f"Top 50 Stocks - {exchange}")
results = []
for ticker in tickers:
    try:
        stock = yf.Ticker(ticker)
        data = stock.history(start=start_date, end=end_date_plus)
        if not data.empty:
            start_price = data["Close"].iloc[0]
            end_price = data["Close"].iloc[-1]
            pct_change = ((end_price - start_price) / start_price) * 100
            results.append([ticker, start_price, end_price, pct_change])
    except:
        continue

if results:
    df = pd.DataFrame(results, columns=["Ticker", "Start Price", "End Price", "% Change"])
    df = df.sort_values("% Change", ascending=False).reset_index(drop=True)
    st.dataframe(df)
    overall_pct = df["% Change"].mean()
    st.metric("📊 Overall Portfolio % Change (Top 50)", f"{overall_pct:.2f}%")
else:
    st.error("No stock data available. Please adjust date range or try again.")
    
    
    
# ------------------- Custom Stock Search -------------------
st.subheader("🔍 Custom Stock Search")
custom_input = st.text_input("Enter ticker symbols (comma-separated, e.g., TCS.NS, RELIANCE.NS, INFY.NS)")
if custom_input:
    custom_tickers = [x.strip() for x in custom_input.split(",") if x.strip()]
    custom_results = []

    for ticker in custom_tickers:
        try:
            stock = yf.Ticker(ticker)
            data = stock.history(start=start_date, end=end_date_plus)
            if not data.empty:
                start_price = data["Close"].iloc[0]
                end_price = data["Close"].iloc[-1]
                pct_change = ((end_price - start_price) / start_price) * 100
                custom_results.append([ticker, start_price, end_price, pct_change])
        except Exception as e:
            st.write(f"⚠️ Skipping {ticker}: {e}")
            continue

    if custom_results:
        custom_df = pd.DataFrame(custom_results, columns=["Ticker", "Start Price", "End Price", "% Change"])
        custom_df = custom_df.sort_values("% Change", ascending=False).reset_index(drop=True)
        st.dataframe(custom_df)
        overall_pct_custom = custom_df["% Change"].mean()
        st.metric("📊 Overall Portfolio % Change (Custom Stocks)", f"{overall_pct_custom:.2f}%")
    else:
        st.info("No data available for the entered tickers.")
    

# ------------------- Weekly Drop/Gain Analysis -------------------
st.subheader("📉📈 Drop & Gain Analysis (Last Week)")
with st.expander("Set Weekly Thresholds"):
    drop_weekly_threshold = st.slider("Weekly Drop Threshold (%)", -10.0, 0.0, -2.0, step=0.5)
    gain_weekly_threshold = st.slider("Weekly Gain Threshold (%)", 0.0, 10.0, 1.0, step=0.5)

last_week_start = date.today() - timedelta(days=7)
last_week_end = date.today() + timedelta(days=1)

drop_gain_results = []
for ticker in tickers:
    try:
        stock = yf.Ticker(ticker)
        data = stock.history(start=last_week_start, end=last_week_end)
        if not data.empty:
            start_price = data["Close"].iloc[0]
            end_price = data["Close"].iloc[-1]
            pct_change = ((end_price - start_price) / start_price) * 100
            if pct_change <= drop_weekly_threshold or pct_change >= gain_weekly_threshold:
                drop_gain_results.append([ticker, start_price, end_price, pct_change])
    except:
        continue

if drop_gain_results:
    drop_gain_df = pd.DataFrame(drop_gain_results, columns=["Ticker", "Start Price", "End Price", "% Change"])
    st.dataframe(drop_gain_df)
else:
    st.info("No stocks matched the weekly drop/gain criteria.")

# ------------------- Background Scheduler for India -------------------
def check_indian_stocks(drop_threshold, gain_threshold):
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)
    if now.weekday() >= 5:  # skip weekends
        return
    market_open = dt_time(9, 30)
    market_close = dt_time(15, 30)
    if not (market_open <= now.time() <= market_close):
        return

    tickers_list = get_india_top50()
    for ticker in tickers_list:
        try:
            stock = yf.Ticker(ticker)
            today = now.date()
            data = stock.history(start=today, end=today + timedelta(days=1))
            if not data.empty:
                start_price = data["Close"].iloc[0]
                end_price = data["Close"].iloc[-1]
                pct_change = ((end_price - start_price) / start_price) * 100
                if pct_change <= drop_threshold:
                    message = f"🔻 Alert: {ticker} fell {pct_change:.2f}% today ({start_price:.2f} → {end_price:.2f})"
                    send_telegram_message(message)
                elif pct_change >= gain_threshold:
                    message = f"🔺 Alert: {ticker} rose {pct_change:.2f}% today ({start_price:.2f} → {end_price:.2f})"
                    send_telegram_message(message)
        except:
            continue

def run_indian_scheduler():
    schedule.every(1).hours.do(check_indian_stocks, drop_threshold=drop_threshold, gain_threshold=gain_threshold)
    while True:
        schedule.run_pending()
        time.sleep(60)

# Only run scheduler for India
if exchange == "India":
    threading.Thread(target=run_indian_scheduler, daemon=True).start()
