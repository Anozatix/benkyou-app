# Benkyou - Streamlit MVP
# Run: streamlit run benkyou_streamlit_app.py

import streamlit as st
import sqlite3
from datetime import datetime, date, timedelta
import time

DB_PATH = "benkyou.db"

# ---------- Utilities ----------

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def create_tables():
    conn = get_conn()
    c = conn.cursor()

    # tasks: stores cumulative seconds and optional running start timestamp
    c.execute('''
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY,
        date TEXT,
        card_name TEXT,
        accumulated_seconds INTEGER DEFAULT 0,
        start_ts REAL DEFAULT NULL,
        xp_earned INTEGER DEFAULT 0,
        status TEXT DEFAULT 'active'
    )
    ''')

    # stats: daily summary
    c.execute('''
    CREATE TABLE IF NOT EXISTS stats (
        date TEXT PRIMARY KEY,
        total_xp INTEGER DEFAULT 0,
        streak INTEGER DEFAULT 0,
        booster_multiplier INTEGER DEFAULT 1,
        has_streak_freeze INTEGER DEFAULT 0
    )
    ''')

    # boosters: record of boosters granted
    c.execute('''
    CREATE TABLE IF NOT EXISTS boosters (
        id INTEGER PRIMARY KEY,
        date_granted TEXT,
        multiplier INTEGER,
        expires_on TEXT
    )
    ''')

    # cards: shop/collection
    c.execute('''
    CREATE TABLE IF NOT EXISTS cards (
        id INTEGER PRIMARY KEY,
        name TEXT,
        image_path TEXT,
        rarity TEXT,
        xp_cost INTEGER,
        unlocked INTEGER DEFAULT 0,
        date_acquired TEXT
    )
    ''')

    conn.commit()
    conn.close()


# ---------- Core logic ----------

def today_str(d=None):
    d = d or date.today()
    return d.strftime('%Y-%m-%d')


def fetch_tasks_for_date(d=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT * FROM tasks WHERE date = ? ORDER BY id', (today_str(d),))
    rows = c.fetchall()
    conn.close()
    return rows


def add_task(card_name):
    conn = get_conn()
    c = conn.cursor()
    c.execute('INSERT INTO tasks (date, card_name) VALUES (?, ?)', (today_str(), card_name))
    conn.commit()
    conn.close()


def start_task(task_id):
    conn = get_conn()
    c = conn.cursor()
    # set start timestamp if not already running
    now_ts = time.time()
    c.execute('UPDATE tasks SET start_ts = ? WHERE id = ? AND start_ts IS NULL', (now_ts, task_id))
    conn.commit()
    conn.close()


def pause_task(task_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT start_ts, accumulated_seconds FROM tasks WHERE id = ?', (task_id,))
    row = c.fetchone()
    if row and row['start_ts']:
        elapsed = int(time.time() - row['start_ts'])
        new_acc = row['accumulated_seconds'] + elapsed
        c.execute('UPDATE tasks SET accumulated_seconds = ?, start_ts = NULL WHERE id = ?', (new_acc, task_id))
    conn.commit()
    conn.close()


def stop_task(task_id):
    # alias to pause but also mark as paused (status remains active until day end)
    pause_task(task_id)


def get_task_total_seconds(task_row):
    total = task_row['accumulated_seconds']
    if task_row['start_ts']:
        total += int(time.time() - task_row['start_ts'])
    return total


def compute_xp_for_seconds(seconds, multiplier=1):
    minutes = seconds // 60
    return minutes * multiplier


def ensure_today_stats():
    conn = get_conn()
    c = conn.cursor()
    t = today_str()
    c.execute('INSERT OR IGNORE INTO stats (date, booster_multiplier) VALUES (?, 1)', (t,))
    conn.commit()
    conn.close()


def evaluate_boosters_and_stats():
    """Evaluate today's boosters and update stats. This can be run at day end or manually.
    Booster rule (v1): if you create >=2 cards and each has >=15 minutes total -> next day multiplier = number of valid cards
    Streak rule: if any card today >=5 minutes, streak+1 else streak reset (unless streak freeze)
    """
    conn = get_conn()
    c = conn.cursor()
    t = today_str()

    # ensure stats row
    c.execute('INSERT OR IGNORE INTO stats (date, booster_multiplier) VALUES (?, 1)', (t,))

    # fetch today's tasks
    c.execute('SELECT * FROM tasks WHERE date = ?', (t,))
    tasks = c.fetchall()

    valid_cards = 0
    streak_hit = False
    total_xp = 0

    for row in tasks:
        secs = get_task_total_seconds(row)
        if secs >= 5 * 60:
            streak_hit = True
        if secs >= 15 * 60:
            valid_cards += 1
        # compute xp for this card (today); booster multiplier for today's XP is from yesterday's boosters
        # fetch today's booster multiplier (already set) (version: use current stats booster_multiplier)
        c.execute('SELECT booster_multiplier FROM stats WHERE date = ?', (t,))
        bm = c.fetchone()['booster_multiplier']
        xp = compute_xp_for_seconds(secs, multiplier=bm)
        total_xp += xp
        c.execute('UPDATE tasks SET xp_earned = ? WHERE id = ?', (xp, row['id']))

    # update total_xp in stats
    c.execute('UPDATE stats SET total_xp = ? WHERE date = ?', (total_xp, t))

    # update streak
    c.execute('SELECT streak, has_streak_freeze FROM stats WHERE date = ?', (t,))
    srow = c.fetchone()
    # if this is the first time stats row created today, we might not have streak history; look at yesterday
    yesterday = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')
    c.execute('SELECT streak FROM stats WHERE date = ?', (yesterday,))
    yrow = c.fetchone()
    prev_streak = yrow['streak'] if yrow else 0

    has_freeze = srow['has_streak_freeze'] if srow else 0

    if streak_hit:
        new_streak = prev_streak + 1
    else:
        if has_freeze:
            new_streak = prev_streak  # preserve
        else:
            new_streak = 0

    c.execute('UPDATE stats SET streak = ? WHERE date = ?', (new_streak, t))

    # create booster for next day if rule met
    if valid_cards >= 2:
        multiplier = valid_cards
        next_day = (date.today() + timedelta(days=1)).strftime('%Y-%m-%d')
        expires_on = next_day
        c.execute('INSERT INTO boosters (date_granted, multiplier, expires_on) VALUES (?, ?, ?)', (t, multiplier, expires_on))
        # set next day's booster in stats (create or update)
        c.execute('INSERT OR IGNORE INTO stats (date, booster_multiplier) VALUES (?, 1)', (next_day,))
        c.execute('UPDATE stats SET booster_multiplier = ? WHERE date = ?', (multiplier, next_day))

    conn.commit()
    conn.close()


# ---------- Streamlit UI ----------

st.set_page_config(page_title="Benkyou - Focus Tracker", layout='centered')
create_tables()
ensure_today_stats()

st.title("Benkyou — Focus & XP Tracker (MVP)")

# --- Custom CSS (Optional: Modern Theme) ---
st.markdown("""
<style>
    /* Page background */
    .main {
        background: linear-gradient(180deg, #1f1f1f 0%, #2b2b2b 100%);
        color: #EEEEEE;
    }

    /* Buttons */
    .stButton button {
        border-radius: 12px;
        background-color: #00ADB5;
        color: white;
        font-weight: 600;
        transition: 0.3s;
    }
    .stButton button:hover {
        background-color: #06B6D4;
        transform: scale(1.03);
    }

    /* Metric cards */
    div[data-testid="stMetricValue"] {
        color: #00ADB5;
    }

    /* Headers */
    h1, h2, h3 {
        color: #EEEEEE;
    }

    /* Form inputs */
    input, textarea {
        background-color: #393E46 !important;
        color: #EEEEEE !important;
        border-radius: 8px !important;
    }
</style>
""", unsafe_allow_html=True)


# Header: date, streak, XP
conn = get_conn()
c = conn.cursor()
ensure_today_stats()
c.execute('SELECT total_xp, streak, booster_multiplier FROM stats WHERE date = ?', (today_str(),))
stat = c.fetchone()
if stat:
    total_xp = stat['total_xp'] or 0
    streak = stat['streak'] or 0
    booster_mult = stat['booster_multiplier'] or 1
else:
    total_xp = 0
    streak = 0
    booster_mult = 1
conn.close()

col1, col2, col3 = st.columns(3)
col1.metric("Date", today_str())
col2.metric("Streak (days)", streak)
col3.metric("Total XP today", total_xp)

st.markdown(f"**Active XP multiplier for today:** x{booster_mult}")

st.divider()

# Add new card
with st.form('add_card'):
    card_name = st.text_input('Add Card / Task (short description)')
    submitted = st.form_submit_button('Add Card')
    if submitted and card_name.strip():
        add_task(card_name.strip())
        st.experimental_rerun()

# Show today's tasks
st.subheader("Today's cards")
rows = fetch_tasks_for_date()
if not rows:
    st.info('No cards for today yet — add one!')

for row in rows:
    tid = row['id']
    name = row['card_name']
    secs = get_task_total_seconds(row)
    mins = secs // 60
    running = bool(row['start_ts'])

    cols = st.columns([6,2,2,2])
    cols[0].markdown(f"**{name}**  \nTotal: {mins} min {secs%60}s")
    if running:
        cols[1].metric('Status','Running')
    else:
        cols[1].metric('Status',row['status'].capitalize())

    start_btn = cols[2].button('Start' if not running else 'Pause', key=f"start_{tid}")
    stop_btn = cols[3].button('Stop', key=f"stop_{tid}")

    if start_btn:
        if not running:
            start_task(tid)
        else:
            pause_task(tid)
        st.rerun()

    if stop_btn:
        stop_task(tid)
        st.rerun()

st.divider()

# Controls: manual evaluation and collection
st.subheader('Utilities')
if st.button('Evaluate boosters & finalize today'):
    evaluate_boosters_and_stats()
    st.success('Evaluated boosters & stats. Next day booster (if any) assigned.')
    st.rerun()

if st.button('Show boosters log'):
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT * FROM boosters ORDER BY id DESC')
    b = c.fetchall()
    conn.close()
    if not b:
        st.info('No boosters yet.')
    else:
        for bi in b:
            st.write(dict(bi))

st.divider()

# ---------- League Data ----------

STREAK_ACHIEVEMENTS = [
    (7, "Ember Initiate", "Maintain a 7-day streak", 100),
    (14, "Spark Keeper", "Maintain a 14-day streak", 250),
    (30, "Flame Guardian", "Maintain a 30-day streak", 500),
    (60, "Blaze Adept", "Maintain a 60-day streak", 1000),
    (90, "Fire Warden", "Maintain a 90-day streak", 1500),
    (150, "Inferno Knight", "Maintain a 150-day streak", 2500),
    (200, "Phoenix Soul", "Maintain a 200-day streak", 4000),
    (250, "Eternal Ember", "Maintain a 250-day streak", 6000),
    (300, "Legendary Flame", "Maintain a 300-day streak", 9000),
    (365, "Master of Continuum", "Maintain a 365-day streak", 12000)
]

XP_ACHIEVEMENTS = [
    (1000, "Bronze Learner", "Reach 1,000 total XP", "Bronze Badge"),
    (5000, "Silver Seeker", "Reach 5,000 total XP", "Silver Badge"),
    (10000, "Gold Explorer", "Reach 10,000 total XP", "Gold Badge"),
    (20000, "Platinum Scholar", "Reach 20,000 total XP", "Platinum Badge"),
    (35000, "Diamond Achiever", "Reach 35,000 total XP", "Diamond Badge"),
    (50000, "Mastermind", "Reach 50,000 total XP", "Elite Title"),
    (75000, "Sage of Study", "Reach 75,000 total XP", "Special Avatar"),
    (100000, "Luminary", "Reach 100,000 total XP", "Theme Unlock"),
    (150000, "Grandmaster", "Reach 150,000 total XP", "Lifetime Title"),
    (200000, "Benkyou Legend", "Reach 200,000 total XP", "Golden Frame")
]

# ---------- League Progression Logic ----------

def fetch_today_stats():
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT total_xp, streak, booster_multiplier FROM stats WHERE date = ?', (today_str(),))
    row = c.fetchone()
    conn.close()
    if row:
        return row['total_xp'] or 0, row['streak'] or 0, row['booster_multiplier'] or 1
    return 0, 0, 1

def get_cumulative_xp():
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT SUM(total_xp) AS total FROM stats')
    total = c.fetchone()['total'] or 0
    conn.close()
    return total

def get_current_tier(value, table):
    completed = [tier for tier in table if value >= tier[0]]
    if not completed:
        return None, table[0]
    current = completed[-1]
    next_tier = next((t for t in table if t[0] > current[0]), None)
    return current, next_tier

# ---------- League UI Section ----------

st.set_page_config(page_title="Benkyou - League Progression", layout='wide')

st.markdown("""
<style>
    .league-card {
        background-color: #1e1e2f;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 15px;
        color: #EEE;
        box-shadow: 0px 0px 8px rgba(0, 0, 0, 0.2);
    }
    .league-header {
        font-size: 22px;
        color: #00ADB5;
        font-weight: 600;
    }
    .league-subtext {
        font-size: 15px;
        color: #ccc;
    }
</style>
""", unsafe_allow_html=True)

st.title("🏆 Benkyou League Progression")

xp_today, streak_today, multiplier = fetch_today_stats()
total_xp = get_cumulative_xp()

col1, col2, col3 = st.columns(3)
col1.metric("Today's XP", xp_today)
col2.metric("Current Streak", f"{streak_today} days")
col3.metric("Cumulative XP", f"{total_xp}")

st.markdown("---")

# 🔥 Streak League
st.header("🔥 Streak Achievement League")
current_streak_tier, next_streak_tier = get_current_tier(streak_today, STREAK_ACHIEVEMENTS)

if current_streak_tier:
    st.success(f"Current Tier: **{current_streak_tier[1]}** ({current_streak_tier[0]} days milestone reached!)")
else:
    st.info(f"No tier reached yet. First goal: {STREAK_ACHIEVEMENTS[0][1]} — {STREAK_ACHIEVEMENTS[0][2]}")

if next_streak_tier:
    progress = min(streak_today / next_streak_tier[0], 1.0)
    st.progress(progress, text=f"Next Tier: {next_streak_tier[1]} — {next_streak_tier[2]}")

for days, name, desc, reward in STREAK_ACHIEVEMENTS:
    achieved = streak_today >= days
    color = "#00ADB5" if achieved else "#444"
    st.markdown(f"""
    <div class='league-card' style='border-left: 6px solid {color};'>
    <div class='league-header'>{name}</div>
    <div class='league-subtext'>{desc} | Reward: {reward} XP</div>
    </div>
    """, unsafe_allow_html=True)


st.markdown("---")

# ⚡ XP League
st.header("⚡ XP Achievement League")
current_xp_tier, next_xp_tier = get_current_tier(total_xp, XP_ACHIEVEMENTS)

if current_xp_tier:
    st.success(f"Current Tier: **{current_xp_tier[1]}** (Reached {current_xp_tier[0]} XP milestone!)")
else:
    st.info(f"No XP tier reached yet. First goal: {XP_ACHIEVEMENTS[0][1]} — {XP_ACHIEVEMENTS[0][2]}")

if next_xp_tier:
    progress = min(total_xp / next_xp_tier[0], 1.0)
    st.progress(progress, text=f"Next Tier: {next_xp_tier[1]} — {next_xp_tier[2]}")

for req_xp, name, desc, reward in XP_ACHIEVEMENTS:
    achieved = total_xp >= req_xp
    color = "#FFD369" if achieved else "#444"
    st.markdown(f"""
    <div class='league-card' style='border-left: 6px solid {color};'>
        <div class='league-header'>{name}</div>
        <div class='league-subtext'>{desc} | Reward: {reward}</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

st.caption("League progression updates automatically as you gain XP and maintain streaks. More animations and rewards coming soon!")
