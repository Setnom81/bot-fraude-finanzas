import sys
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st

# Append repository root directory to sys.path to enable absolute imports from src
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(ROOT_DIR))

from src.database.storage import TransactionStorage

# ---------------------------------------------------------
# Page & Layout Configuration
# ---------------------------------------------------------
st.set_page_config(
    page_title="Financial Fraud Bot | Analytics Dashboard",
    page_icon="🛡️",
    layout="wide"
)

# ---------------------------------------------------------
# Data Ingestion & Preprocessing Pipeline
# ---------------------------------------------------------
@st.cache_data(ttl=60)
def load_data() -> pd.DataFrame:
    """
    Fetches raw transaction payloads from MySQL via TransactionStorage,
    sanitizes numerical values, and handles datetime fallback logic.
    """
    storage = TransactionStorage()
    data = storage.load()
    
    transactions = data.get("transactions", [])
    if not transactions:
        return pd.DataFrame()
        
    df = pd.DataFrame(transactions)
    
    # Numerical Sanitization: Strip currency symbols/formatting and extract floating-point values
    if "amount" in df.columns:
        cleaned_amount = (
            df["amount"]
            .astype(str)
            .str.replace(",", "", regex=False)
            .str.extract(r'(\d+\.?\d*)')[0]
        )
        df["amount"] = pd.to_numeric(cleaned_amount, errors="coerce")
        
    # Datetime Consolidation: Fallback to email ingestion timestamp if transaction_date is NaT/NULL
    date_fallback_col = next((col for col in ["email_date", "received_at", "created_at"] if col in df.columns), None)
    
    if "transaction_date" in df.columns:
        df["transaction_date"] = pd.to_datetime(
            df["transaction_date"], 
            errors="coerce", 
            dayfirst=True, 
            format="mixed"
        )
        
        if date_fallback_col:
            df[date_fallback_col] = pd.to_datetime(
                df[date_fallback_col], 
                errors="coerce", 
                dayfirst=True, 
                format="mixed"
            )
            # Impute missing transaction_date values with email ingestion date
            df["transaction_date"] = df["transaction_date"].fillna(df[date_fallback_col])
    elif date_fallback_col:
        df["transaction_date"] = pd.to_datetime(
            df[date_fallback_col], 
            errors="coerce", 
            dayfirst=True, 
            format="mixed"
        )
        
    return df


# ---------------------------------------------------------
# Main Application Interface
# ---------------------------------------------------------
st.title("🛡️ Financial Fraud & Analytics Dashboard")
st.markdown("Real-time transaction ingestion telemetry and exploratory data interface.")

df = load_data()

if df.empty:
    st.warning("⚠️ No transaction records retrieved from storage.")
    st.stop()

# ---------------------------------------------------------
# Sidebar Filtering Controls
# ---------------------------------------------------------
st.sidebar.header("🔍 Dimension Filters")

# Currency Filter
currencies = df["currency"].unique().tolist() if "currency" in df.columns else []
selected_currency = st.sidebar.selectbox("Filter Currency", currencies) if currencies else None

if selected_currency:
    df_filtered = df[df["currency"] == selected_currency]
else:
    df_filtered = df.copy()

# Merchant Text Search Filter
search_merchant = st.sidebar.text_input("Search Merchant", "")
if search_merchant:
    df_filtered = df_filtered[df_filtered["merchant"].str.contains(search_merchant, case=False, na=False)]

# ---------------------------------------------------------
# Key Performance Indicators (KPIs)
# ---------------------------------------------------------
col1, col2, col3, col4 = st.columns(4)

total_tx = len(df_filtered)
total_amount = float(df_filtered["amount"].sum()) if "amount" in df_filtered.columns else 0.0
avg_amount = float(df_filtered["amount"].mean()) if "amount" in df_filtered.columns else 0.0
max_amount = float(df_filtered["amount"].max()) if "amount" in df_filtered.columns else 0.0

col1.metric("Total Transactions", f"{total_tx}")
col2.metric("Total Volume", f"{selected_currency or ''} {total_amount:,.2f}")
col3.metric("Average Ticket", f"{selected_currency or ''} {avg_amount:,.2f}")
col4.metric("Max Ticket", f"{selected_currency or ''} {max_amount:,.2f}")

st.divider()

# ---------------------------------------------------------
# Visual Analytics Layer (Plotly Express)
# ---------------------------------------------------------
chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    st.subheader("📊 Top 10 Merchants by Total Volume")
    if "merchant" in df_filtered.columns and "amount" in df_filtered.columns:
        top_merchants = (
            df_filtered.groupby("merchant")["amount"]
            .sum()
            .reset_index()
            .sort_values(by="amount", ascending=False)
            .head(10)
        )
        fig_bar = px.bar(
            top_merchants,
            x="amount",
            y="merchant",
            orientation="h",
            labels={"amount": "Total Volume", "merchant": "Merchant"},
            color="amount",
            color_continuous_scale="Blues"
        )
        fig_bar.update_layout(yaxis={'categoryorder': 'total ascending'})
        st.plotly_chart(fig_bar, width="stretch")

with chart_col2:
    st.subheader("📈 Aggregated Daily Spending Trend")
    if "transaction_date" in df_filtered.columns and "amount" in df_filtered.columns:
        # Drop rows with NaT values to prevent resample exceptions
        df_valid_dates = df_filtered.dropna(subset=["transaction_date"])
        
        if not df_valid_dates.empty:
            df_time = (
                df_valid_dates.set_index("transaction_date")
                .resample("D")["amount"]
                .sum()
                .reset_index()
            )
            fig_line = px.line(
                df_time,
                x="transaction_date",
                y="amount",
                labels={"transaction_date": "Timestamp", "amount": "Daily Volume"},
                markers=True
            )
            st.plotly_chart(fig_line, width="stretch")
        else:
            st.info("No valid datetime records available for time-series aggregation.")

st.divider()

# ---------------------------------------------------------
# Tabular Data Ledger (Type-Guarded for Static Analysis)
# ---------------------------------------------------------
st.subheader("📑 Transaction Ledger")

display_cols = [
    col for col in ["transaction_date", "merchant", "amount", "currency", "card_last_digits", "provider"] 
    if col in df_filtered.columns
]

if isinstance(df_filtered, pd.DataFrame):
    display_df = df_filtered[display_cols]
    if "transaction_date" in display_df.columns:
        display_df = display_df.sort_values(by="transaction_date", ascending=False)
        
    st.dataframe(display_df, width="stretch")