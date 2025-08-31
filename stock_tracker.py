import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from datetime import date, timedelta

# ------------------- Utility: Fetch HTML with headers -------------------
def fetch_html(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.text

# ------------------- Fetch US Top 50 -------------------
@st.cache_data
def get_us_top50():
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    html = fetch_html(url)
    tables = pd.read_html(html)
    tickers = tables[0]["Symbol"].tolist()
    return tickers[:50]

# ------------------- Fetch India Top 50 -------------------
@st.cache_data
def get_india_top50():
    url = "https://en.wikipedia.org/wiki/NIFTY_50"
    html = fetch_html(url)
    tables = pd.read_html(html)

    # Find the table that has "Symbol" or "Company Name"
    table = None
    for t in tables:
        if any(col in t.columns for col in ["Symbol", "Company Name", "Ticker"]):
            table = t
            break

    if table is None:
        st.error("⚠️ Could not find NIFTY 50 table on Wikipedia.")
        return []

    # Pick the correct column
    col_name = None
    for c in ["Symbol", "Ticker", "Company Name"]:
        if c in table.columns:
            col_name = c
            break

    if col_name is None:
        st.error("⚠️ No usable ticker column found in NIFTY 50 table.")
        return []

    # Convert to Yahoo Finance tickers
    tickers = table[col_name].astype(str).apply(lambda x: x + ".NS").tolist()
    return tickers[:50]


# ------------------- Streamlit UI -------------------
st.title("📈 Stock Tracker - US & India")

exchange = st.radio("Select Exchange", ["US", "India"])

start_date = st.date_input("Start Date", date(2024, 1, 1))
end_date = st.date_input("End Date", date.today())

tickers = get_us_top50() if exchange == "US" else get_india_top50()

# --- Adjust end_date (+1 day for Yahoo Finance bug) ---
end_date_plus = end_date + timedelta(days=1)

# ------------------- Fetch Stock Data -------------------
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
    except Exception as e:
        st.write(f"⚠️ Skipping {ticker} ({e})")
        continue

if results:
    df = pd.DataFrame(results, columns=["Ticker", "Start Price", "End Price", "% Change"])
    df = df.sort_values("% Change", ascending=False).reset_index(drop=True)

    st.dataframe(df)

    overall_pct = df["% Change"].mean()
    st.metric("📊 Overall Portfolio % Change (Top 50)", f"{overall_pct:.2f}%")
else:
    st.error("No stock data available. Please adjust date range or try again.")

# ------------------- Drop/Gain Analysis -------------------
st.subheader("📉📈 Drop & Gain Analysis (Last Week)")

with st.expander("Set Thresholds"):
    drop_threshold = st.slider("Drop Threshold (%)", -10.0, 0.0, -2.0, step=0.5)
    gain_threshold = st.slider("Gain Threshold (%)", 0.0, 10.0, 1.0, step=0.5)

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

            if pct_change <= drop_threshold or pct_change >= gain_threshold:
                drop_gain_results.append([ticker, start_price, end_price, pct_change])
    except:
        continue

if drop_gain_results:
    drop_gain_df = pd.DataFrame(
        drop_gain_results, columns=["Ticker", "Start Price", "End Price", "% Change"]
    )
    st.dataframe(drop_gain_df)
else:
    st.info("No stocks matched the drop/gain criteria in the last week.")
