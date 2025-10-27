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

# ---------- Gather all available dates (from stats or tasks) ----------
conn = get_conn()
c = conn.cursor()
c.execute("""
    SELECT date FROM stats
    UNION
    SELECT date FROM tasks
    ORDER BY date ASC
""")
date_rows = c.fetchall()
all_dates = [r["date"] for r in date_rows if r["date"]]
conn.close()

# ---------- Load stats for charting ----------
if all_dates:
    conn = get_conn()
    placeholders = ",".join("?" for _ in all_dates)
    query = f"""
        SELECT date, total_xp, streak, booster_multiplier
        FROM stats
        WHERE date IN ({placeholders})
        ORDER BY date ASC
    """
    df_stats = pd.read_sql_query(query, conn, params=all_dates)
    conn.close()
else:
    df_stats = pd.DataFrame(columns=["date", "total_xp", "streak", "booster_multiplier"])

# ---------- Handle empty state ----------
if df_stats.empty and not all_dates:
    st.info("No data yet — start working on your cards to build your history!")
else:
    # ---------- Summary charts ----------
    if not df_stats.empty:
        st.subheader("📊 XP Progress Over Time")
        st.line_chart(df_stats.set_index("date")[["total_xp"]])

        st.subheader("🔥 Streak Over Time")
        st.line_chart(df_stats.set_index("date")[["streak"]])

    st.markdown("---")

    # ---------- Daily breakdown ----------
    st.subheader("📅 Daily Breakdown")

    if all_dates:
        dates = all_dates[::-1]  # recent first
        selected_date = st.selectbox("Select a date to view:", dates)
    else:
        selected_date = None

    if selected_date:
        conn = get_conn()
        c = conn.cursor()

        # Ensure stats entry exists for selected_date
        c.execute("INSERT OR IGNORE INTO stats (date, booster_multiplier) VALUES (?, 1)", (selected_date,))

        # Fetch data for that date
        c.execute("SELECT * FROM tasks WHERE date = ? ORDER BY id", (selected_date,))
        rows = c.fetchall()
        c.execute("SELECT * FROM boosters WHERE date_granted = ?", (selected_date,))
        booster = c.fetchone()
        c.execute("SELECT total_xp, streak FROM stats WHERE date = ?", (selected_date,))
        stat_row = c.fetchone()
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

# ---------- Sidebar debug info (optional; remove later if not needed) ----------
st.sidebar.markdown("### 🧩 Debug Info (for troubleshooting)")
conn = get_conn()
c = conn.cursor()
c.execute("SELECT COUNT(*) AS t FROM tasks")
st.sidebar.write("Total tasks:", c.fetchone()["t"])
c.execute("SELECT COUNT(*) AS s FROM stats")
st.sidebar.write("Total stats rows:", c.fetchone()["s"])
c.execute("SELECT DISTINCT date FROM tasks ORDER BY date DESC LIMIT 5")
recent_dates = [r[0] for r in c.fetchall()]
st.sidebar.write("Recent task dates:", recent_dates)
conn.close()
