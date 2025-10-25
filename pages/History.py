# pages/02_History.py
import streamlit as st
import sqlite3
import pandas as pd

DB_PATH = "benkyou.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

st.set_page_config(page_title="Benkyou - History", layout="wide")

st.title("📜 Benkyou History & Analytics")

# --- Summary charts ---
conn = get_conn()
df_stats = pd.read_sql_query("SELECT date, total_xp, streak, booster_multiplier FROM stats ORDER BY date ASC", conn)
conn.close()

if df_stats.empty:
    st.info("No data yet — start working on your cards to build your history!")
else:
    st.subheader("📊 XP Progress Over Time")
    st.line_chart(df_stats.set_index("date")[["total_xp"]])

    st.subheader("🔥 Streak Over Time")
    st.line_chart(df_stats.set_index("date")[["streak"]])

    st.markdown("---")

    # --- Detailed daily breakdown ---
    st.subheader("📅 Daily Breakdown")

    dates = df_stats["date"].tolist()[::-1]
    selected_date = st.selectbox("Select a date to view:", dates)

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM tasks WHERE date = ? ORDER BY id", (selected_date,))
    rows = c.fetchall()
    c.execute("SELECT * FROM boosters WHERE date_granted = ?", (selected_date,))
    booster = c.fetchone()
    conn.close()

    st.markdown(f"### Tasks for {selected_date}")

    if not rows:
        st.warning("No cards were created on this date.")
    else:
        total_xp = sum(r["xp_earned"] for r in rows)
        total_time = sum(r["accumulated_seconds"] for r in rows) // 60
        st.metric("Total XP", total_xp)
        st.metric("Total Focus Time (min)", total_time)

        for row in rows:
            mins = row["accumulated_seconds"] // 60
            st.markdown(f"**🗂 {row['card_name']}** — {mins} min — {row['xp_earned']} XP")

    if booster:
        st.success(f"🎯 Booster earned that day: x{booster['multiplier']} (for next day)")
