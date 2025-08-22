import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import google.generativeai as genai
import tempfile
import os
import json
import re
from datetime import datetime, timedelta, time
import pytz
from streamlit_autorefresh import st_autorefresh

# ----------------------------
# Configure Gemini API
# ----------------------------
GOOGLE_API_KEY = "AIzaSyCwb6CDQutEVXRjhufOnf4LuUUs4zwAxow"
genai.configure(api_key=GOOGLE_API_KEY)
MODEL_NAME = 'gemini-2.0-flash'
gen_model = genai.GenerativeModel(MODEL_NAME)

# ----------------------------
# Streamlit settings
# ----------------------------
st.set_page_config(layout="wide", page_title="AI-Powered Indian Stock Dashboard", page_icon="📈")
st.title("📊 AI-Powered Indian Stock Dashboard 🇮🇳")

# ----------------------------
# Sidebar configuration
# ----------------------------
st.sidebar.header("Configuration")
mode = st.sidebar.radio("Mode", ["Historical", "Live Intraday (1-min)", "Indicator Guide"], index=0)

# Default to popular Indian stocks
tickers_input = st.sidebar.text_input("Enter Indian Stock Tickers (comma-separated):", 
                                      "RELIANCE.NS, HDFCBANK.NS, TCS.NS, INFY.NS")
tickers = [ticker.strip().upper() for ticker in tickers_input.split(",") if ticker.strip()]

# Date selection (only for historical)
date_today = datetime.today()
start_date_default = date_today - timedelta(days=365)
if mode == "Historical":
    start_date = st.sidebar.date_input("Start Date", value=start_date_default)
    end_date = st.sidebar.date_input("End Date", value=date_today)

# Technical indicators
st.sidebar.subheader("Technical Indicators")
indicators = st.sidebar.multiselect(
    "Select Indicators:",
    ["20-Day SMA", "50-Day SMA", "20-Day EMA", "50-Day EMA", "20-Day Bollinger Bands", "MACD", "VWAP"],
    default=["20-Day SMA", "50-Day SMA"]
)

# ----------------------------
# Indicator Guide UI
# ----------------------------
if mode == "Indicator Guide":
    st.header("📘 Quick Guide to Indicators")
    st.write("No boring finance textbook here.")

    with st.expander("20-Day SMA & 50-Day SMA (Simple Moving Average)"):
        st.markdown("""
        - **SMA = Average price over X days.**
        - 20-Day = short-term vibes.
        - 50-Day = long-term, more stable.
        - 20 > 50 → 🟢 Golden Cross (bullish).
        - 20 < 50 → 🔴 Death Cross (bearish).
        """)

    with st.expander("20-Day EMA & 50-Day EMA (Exponential Moving Average)"):
        st.markdown("""
        - Like SMA but reacts faster (recent days matter more).
        - 20 EMA = short-term flips.
        - 50 EMA = smoother, medium-term.
        """)

    with st.expander("20-Day Bollinger Bands"):
        st.markdown("""
        - Rubber band around price 📏.
        - Upper = maybe overbought.
        - Lower = maybe oversold.
        """)

    with st.expander("MACD (Momentum Meter)"):
        st.markdown("""
        - Speedometer of trend 🚗.
        - Above 0 = 🚀 bullish, below = 📉 bearish.
        """)

    with st.expander("VWAP (Volume Weighted Average Price)"):
        st.markdown("""
        - Fair price line of the day.
        - Above VWAP = buyers winning ⚡.
        - Below VWAP = sellers in control 🛑.
        """)

# ----------------------------
# Helper: Run LLM with robust JSON parsing
# ----------------------------
def run_llm(prompt, image_bytes=None):
    contents = [{"role": "user", "parts": [prompt]}]
    if image_bytes:
        contents.append({"role": "user", "parts": [{"data": image_bytes, "mime_type": "image/png"}]})

    response = gen_model.generate_content(contents=contents)

    try:
        result_text = response.text.strip()
        result_text = re.sub(r"^```json\s*|\s*```$", "", result_text, flags=re.DOTALL).strip()
        json_start_index = result_text.find('{')
        json_end_index = result_text.rfind('}') + 1
        if json_start_index != -1 and json_end_index > json_start_index:
            json_string = result_text[json_start_index:json_end_index]
            return json.loads(json_string)
        else:
            raise ValueError("No valid JSON found in the response.")
    except Exception:
        return {"error": f"(Fallback) Raw: {response.text[:500]}..."}

# ----------------------------
# Formatter for justification dict
# ----------------------------
def format_justification(justification):
    if isinstance(justification, dict):
        formatted = []
        for key, value in justification.items():
            formatted.append(f"**{key}:** {value}")
        return "\n".join(formatted)
    return str(justification)

# ----------------------------
# Gradient helper for Final Call
# ----------------------------
def get_reco_color(reco):
    mapping = {
        "Strong Buy": "#00b050",
        "Buy": "#92d050",
        "Weak Buy": "#c6e0b4",
        "Weak Sell": "#f4b084",
        "Sell": "#ff6666",
        "Strong Sell": "#c00000",
    }
    return mapping.get(reco, "#cccccc")

# ----------------------------
# Data Fetch + Analysis
# ----------------------------
if st.sidebar.button("Fetch Data") or mode == "Live Intraday (1-min)":
    stock_data = {}
    for ticker in tickers:
        if mode == "Live Intraday (1-min)":
            st_autorefresh(interval=60 * 1000, key=f"live_refresh_{ticker}")
            ist = pytz.timezone("Asia/Kolkata")
            now = datetime.now(ist).time()
            if now >= time(9, 15) and now <= time(15, 30):
                data = yf.download(ticker, period="1d", interval="1m", multi_level_index=False)
            else:
                st.warning("⏰ Market closed. Live mode only works between 9:15 AM and 3:30 PM IST.")
                continue
        else:
            data = yf.download(ticker, start=start_date, end=end_date, multi_level_index=False)

        # --- Convert index to IST ---
        ist = pytz.timezone("Asia/Kolkata")
        if data.index.tz is None:
            data.index = data.index.tz_localize("UTC").tz_convert(ist)
        else:
            data.index = data.index.tz_convert(ist)

        if not data.empty:
            stock_data[ticker] = data
        else:
            st.warning(f"No data found for {ticker}.")
    st.session_state["stock_data"] = stock_data
    if stock_data:
        st.success("Stock data loaded successfully for: " + ", ".join(stock_data.keys()))

    if "stock_data" in st.session_state and st.session_state["stock_data"]:

        def analyze_ticker(ticker, data):
            fig = go.Figure(data=[
                go.Candlestick(
                    x=data.index,
                    open=data['Open'],
                    high=data['High'],
                    low=data['Low'],
                    close=data['Close'],
                    name="Candlestick"
                )
            ])

            def add_indicator(ind):
                if ind == "20-Day SMA":
                    sma = data['Close'].rolling(window=20).mean()
                    fig.add_trace(go.Scatter(x=data.index, y=sma, mode='lines', name='SMA (20)'))
                elif ind == "50-Day SMA":
                    sma = data['Close'].rolling(window=50).mean()
                    fig.add_trace(go.Scatter(x=data.index, y=sma, mode='lines', name='SMA (50)'))
                elif ind == "20-Day EMA":
                    ema = data['Close'].ewm(span=20, adjust=False).mean()
                    fig.add_trace(go.Scatter(x=data.index, y=ema, mode='lines', name='EMA (20)'))
                elif ind == "50-Day EMA":
                    ema = data['Close'].ewm(span=50, adjust=False).mean()
                    fig.add_trace(go.Scatter(x=data.index, y=ema, mode='lines', name='EMA (50)'))
                elif ind == "20-Day Bollinger Bands":
                    sma = data['Close'].rolling(window=20).mean()
                    std = data['Close'].rolling(window=20).std()
                    bb_upper = sma + 2 * std
                    bb_lower = sma - 2 * std
                    fig.add_trace(go.Scatter(x=data.index, y=bb_upper, mode='lines', name='BB Upper'))
                    fig.add_trace(go.Scatter(x=data.index, y=bb_lower, mode='lines', name='BB Lower'))
                elif ind == "VWAP":
                    data['VWAP'] = (data['Close'] * data['Volume']).cumsum() / data['Volume'].cumsum()
                    fig.add_trace(go.Scatter(x=data.index, y=data['VWAP'], mode='lines', name='VWAP'))
                elif ind == "MACD":
                    exp1 = data['Close'].ewm(span=12, adjust=False).mean()
                    exp2 = data['Close'].ewm(span=26, adjust=False).mean()
                    macd = exp1 - exp2
                    fig.add_trace(go.Scatter(x=data.index, y=macd, mode='lines', name='MACD'))

            for ind in indicators:
                add_indicator(ind)
            fig.update_layout(xaxis_rangeslider_visible=False, template="plotly_dark")

            # Save chart for AI
            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp_file:
                fig.write_image(temp_file.name)
                tmp_file_path = temp_file.name
            with open(tmp_file_path, "rb") as f:
                image_bytes = f.read()
            os.remove(tmp_file_path)

            # --- Technical Analysis ---
            tech_prompt = f"""
            You are a Stock Trader specializing in Technical Analysis at a top financial institution, explaining to a Gen Z student (this is important).
            Analyze the stock chart for {ticker} based on its candlestick chart and the displayed technical indicators.
            Provide a structured explanation one down of the otherin numbered points covering:
            1. Dominant Trend
            2. EMA/SMA Alignment
            3. Price vs Indicators
            4. Momentum & Volume
            5. Reversal / Risk Signals
            6. Gen Z Mindset not cringe

            At the end, give a recommendation from one of these options ONLY:
            ['Strong Buy', 'Buy', 'Weak Buy', 'Weak Sell', 'Sell', 'Strong Sell'].

            Return JSON with:
            {{
              "recommendation": "<Strong Buy / Buy / Weak Buy / Weak Sell / Sell / Strong Sell>",
              "justification": {{
                "1. Dominant Trend": "...",
                "2. EMA/SMA Alignment": "...",
                "3. Price vs Indicators": "...",
                "4. Momentum & Volume": "...",
                "5. Reversal / Risk Signals": "...",
                "6. Mindset": "..."
              }}
            }}
            """
            tech_result = run_llm(tech_prompt, image_bytes=image_bytes)

            # --- Sentiment Analysis ---
            sent_prompt = f"""
            You are analyzing the market sentiment for {ticker} (NSE/BSE).
            Classify sentiment strictly as one of ['Positive', 'Negative', 'Neutral'].
            Justify with 2-3 news-style reasons (like headlines).

            Return JSON:
            {{
              "sentiment": "<Positive / Negative / Neutral>",
              "explanation": "<Why, explained like citing news headlines>"
            }}
            """
            sent_result = run_llm(sent_prompt)

            return fig, tech_result, sent_result

        # Create tabs
        tab_names = ["Overall Summary"] + list(st.session_state["stock_data"].keys())
        tabs = st.tabs(tab_names)

        overall_results = []
        for i, ticker in enumerate(st.session_state["stock_data"]):
            data = st.session_state["stock_data"][ticker]
            fig, tech_result, sent_result = analyze_ticker(ticker, data)
            overall_results.append({"Stock": ticker, "Recommendation": tech_result.get("recommendation", "N/A")})

            with tabs[i + 1]:
                st.subheader(f"📈 Analysis for {ticker}")
                st.plotly_chart(fig, use_container_width=True, key=f"plot_{ticker}")

                # Gradient Final Call Box
                final_reco = tech_result.get("recommendation", "N/A")
                color = get_reco_color(final_reco)
                st.markdown(
                    f"""
                    <div style="
                        background: linear-gradient(to right, white, {color});
                        padding: 15px;
                        border-radius: 10px;
                        font-size: 18px;
                        font-weight: bold;
                        text-align: center;
                    ">
                    ✅ Final Call: {final_reco}
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                # Justification expander
                with st.expander("📊 Technical Justification"):
                    st.markdown(format_justification(tech_result.get("justification", {})))

                # Sentiment box
                with st.expander("📰 Market Sentiment Analysis"):
                    sentiment = sent_result.get("sentiment", "Neutral")
                    explanation = sent_result.get("explanation", "")
                    sent_borders = {
                         "Positive": "#28a745",  # green
                         "Negative": "#dc3545",  # red
                         "Neutral": "#6c757d"    # grey
                         }
                    border_color = sent_borders.get(sentiment, "#6c757d")
                    
                    st.markdown(
                        f"""
                        <div style="
                        background-color: white;
                        padding: 15px;
                        border-radius: 10px;
                        border: 3px solid {border_color};
                        font-size: 16px;
                        ">
                        <b>Sentiment:</b> {sentiment}<br><br>
                        <b>Explanation:</b><br>
                        {explanation}
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

        with tabs[0]:
            st.subheader("📊 Overall Structured Recommendations")
            df_summary = pd.DataFrame(overall_results)
            st.table(df_summary)
else:
    st.info("Please fetch stock data using the sidebar or switch to Live mode.")
