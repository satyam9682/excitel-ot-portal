import streamlit as st
import psycopg2
from psycopg2 import pool
import pandas as pd
from datetime import datetime, date, timedelta
import os
import hashlib
import time

# ==================== AUTOMATIC THEME CONFIG ====================
os.makedirs(".streamlit", exist_ok=True)
config_path = ".streamlit/config.toml"
if not os.path.exists(config_path):
    with open(config_path, "w") as f:
        f.write("""
[theme]
base="light"
primaryColor="#FF6B00"
backgroundColor="#FF6B00"
secondaryBackgroundColor="#FFFFFF"
textColor="#201F1E"
font="sans serif"
""")

# ==================== DATABASE CONNECTION POOLING ====================
@st.cache_resource
def get_db_pool():
    db_url = st.secrets["database"]["url"]
    return psycopg2.pool.SimpleConnectionPool(minconn=1, maxconn=10, dsn=db_url)

def get_connection():
    return get_db_pool().getconn()

def release_connection(conn):
    if conn:
        get_db_pool().putconn(conn)

# ==================== CRYPTOGRAPHIC UTILITIES ====================
SALT_SECRET = "Excitel_Secure_Salt_2026"

def hash_password(password):
    return hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        SALT_SECRET.encode('utf-8'),
        100000
    ).hex()

# ==================== DATABASE SCHEMA & INITIALIZATION ====================
def init_db():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                email TEXT PRIMARY KEY,
                name TEXT,
                role TEXT,
                emp_id TEXT,
                tl_name TEXT,
                tl_id TEXT,
                password_hash TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ot_logs (
                id SERIAL PRIMARY KEY,
                date TEXT,
                employee_name TEXT,
                emp_id TEXT,
                shift_start TEXT,
                shift_end TEXT,
                ot_start TEXT,
                ot_end TEXT,
                ot_hours REAL,
                task_type TEXT,
                status TEXT,
                tl_name TEXT,
                actual_output REAL,
                standard_rate REAL,
                expected_output REAL,
                productivity REAL,
                verified_hours REAL,
                amount REAL,
                approved_by TEXT,
                approved_at TEXT,
                rejection_reason TEXT DEFAULT ''
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                id SERIAL PRIMARY KEY,
                recipient_email TEXT,
                message TEXT,
                created_at TEXT,
                is_read BOOLEAN DEFAULT FALSE
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_logs (
                id SERIAL PRIMARY KEY,
                performer TEXT,
                action TEXT,
                target TEXT,
                timestamp TEXT,
                details TEXT
            )
        ''')
        default_pass_hash = hash_password("Password123")
        default_users = [
            ("porwal.satyam1@gmail.com", "Satyam Porwal", "Admin", "EBND04737", "Nandini Puri", "TL01", default_pass_hash),
            ("ritu.mandal@dl.excitel.in", "Ritu Mandal", "TL", "EBND04635", "Nandini Puri", "TL01", default_pass_hash),
            ("jamal.khan@dl.excitel.in", "Jamal Khan", "TL", "EBND04471", "Nandini Puri", "TL01", default_pass_hash),
            ("abhishek.pandey@dl.excitel.in", "Abhishek Pandey", "TL", "EBND04472", "Nandini Puri", "TL01", default_pass_hash),
            ("basu.porwal@dl.excitel.in", "Basu Porwal", "Employee", "EBND04475", "Satyam Porwal", "TL02", default_pass_hash)
        ]
        cursor.executemany("""
            INSERT INTO users (email, name, role, emp_id, tl_name, tl_id, password_hash) 
            VALUES (%s, %s, %s, %s, %s, %s, %s) 
            ON CONFLICT (email) DO NOTHING
        """, default_users)
        conn.commit()
    finally:
        release_connection(conn)

init_db()

def record_audit(performer, action, target, details=""):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO audit_logs (performer, action, target, timestamp, details)
            VALUES (%s, %s, %s, %s, %s)
        """, (performer, action, target, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), details))
        conn.commit()
    except Exception as e:
        print(f"Audit Log Error: {e}")
    finally:
        release_connection(conn)

def send_notification(recipient_email, message):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO notifications (recipient_email, message, created_at) VALUES (%s, %s, %s)",
            (recipient_email.lower().strip(), message, datetime.now().strftime("%Y-%m-%d %H:%M"))
        )
        conn.commit()
    except Exception as e:
        print(f"Notification Error: {e}")
    finally:
        release_connection(conn)

# ==================== PAGE CONFIG & STYLING ====================
st.set_page_config(page_title="Excitel OT Portal", page_icon="⚡", layout="wide")

# CSS to reproduce the UI shown in the reference image
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Segoe+UI:wght@400;600;700;800&display=swap');
        
        /* App Canvas */
        .stApp {
            background-color: #FF6B00 !important;
            font-family: 'Segoe UI', sans-serif !important;
        }
        
        header[data-testid="stHeader"] {
            display: none !important;
        }
        
        .main .block-container {
            padding: 0 !important;
            max-width: 100% !important;
        }
        
        /* Top Navigation Header Bar */
        .excitel-topbar {
            background: #FFFFFF;
            width: 100%;
            padding: 12px 36px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.08);
            margin-bottom: 20px;
        }
        .brand-cluster {
            display: flex;
            align-items: center;
            gap: 20px;
        }
        .brand-title {
            font-size: 26px;
            font-weight: 800;
            color: #0E2B5C;
            letter-spacing: -0.5px;
            line-height: 1;
        }
        .brand-sub {
            font-size: 11px;
            color: #605E5C;
            letter-spacing: 0.2px;
            margin-top: 3px;
        }
        .topbar-badge {
            background: #FF6B00;
            color: #FFFFFF;
            font-weight: 700;
            font-size: 13px;
            padding: 6px 18px;
            border-radius: 20px;
            letter-spacing: 0.5px;
            display: inline-block;
            text-align: center;
        }
        .user-tag {
            font-size: 14px;
            font-weight: 700;
            color: #0E2B5C;
            border-left: 2px solid #E1DFDD;
            padding-left: 18px;
        }
        
        /* Floating Dark Navy Pill Navigation Header */
        .nav-pill-container {
            background: #233D6B;
            border-radius: 30px;
            padding: 8px 18px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin: 0 auto 24px auto;
            max-width: 1180px;
            box-shadow: 0 4px 18px rgba(0,0,0,0.15);
        }
        .nav-user-label {
            color: #FFFFFF;
            font-weight: 700;
            font-size: 15px;
            display: flex;
            align-items: center;
            gap: 8px;
            padding-left: 10px;
        }

        /* Centered White Work Surface Card */
        .workspace-card {
            background: #FFFFFF;
            border-radius: 20px;
            padding: 30px 40px;
            max-width: 1180px;
            margin: 0 auto 30px auto;
            box-shadow: 0 10px 30px rgba(0,0,0,0.12);
        }

        /* 5 Top Summary Metric Cards */
        .kpi-grid {
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 16px;
            margin-bottom: 25px;
        }
        .kpi-box {
            background: #FFFFFF;
            border-radius: 12px;
            border: 1px solid #E5E7EB;
            padding: 16px 8px;
            text-align: center;
            box-shadow: 0 2px 8px rgba(0,0,0,0.04);
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
        }
        .kpi-val {
            font-size: 28px;
            font-weight: 800;
            line-height: 1.1;
        }
        .kpi-title {
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.6px;
            margin-top: 6px;
            text-transform: uppercase;
        }
        .kpi-navy { border-bottom: 4px solid #1F3A60; color: #1F3A60; }
        .kpi-green { border-bottom: 4px solid #10B981; color: #1F3A60; }
        .kpi-red { border-bottom: 4px solid #EF4444; color: #1F3A60; }
        .kpi-cyan { border-bottom: 4px solid #0EA5E9; color: #1F3A60; }
        .kpi-blue { border-bottom: 4px solid #2563EB; color: #1F3A60; }

        /* Custom Modern Form Inputs */
        div[data-baseweb="input"] {
            border-radius: 8px !important;
        }
        
        /* Interactive Table Aesthetics */
        div[data-testid="stDataFrame"] {
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        }
        
        /* Modal and Dialogs Styling */
        div[data-testid="stDialog"] div[role="dialog"] {
            border-radius: 16px;
            border-top: 6px solid #FF6B00;
        }
    </style>
""", unsafe_allow_html=True)

# ==================== SESSION TIMEOUT LOGIC ====================
INACTIVITY_TIMEOUT_SECONDS = 1800  # 30 Minutes

if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_email' not in st.session_state:
    st.session_state.user_email = ""
if 'user_role' not in st.session_state:
    st.session_state.user_role = ""
if 'user_name' not in st.session_state:
    st.session_state.user_name = ""
if 'current_view' not in st.session_state:
    st.session_state.current_view = "portal"
if 'last_activity' not in st.session_state:
    st.session_state.last_activity = time.time()

if st.session_state.authenticated:
    if time.time() - st.session_state.last_activity > INACTIVITY_TIMEOUT_SECONDS:
        st.session_state.authenticated = False
        st.session_state.user_email = ""
        st.warning("⏱️ Session timed out due to 30 minutes of inactivity. Please sign in again.")
        st.rerun()
    else:
        st.session_state.last_activity = time.time()

# ==================== LOGIN GATEWAY ====================
if not st.session_state.authenticated:
    st.markdown("""
        <div style="background: #FFFFFF; width: 100%; padding: 14px 36px; display: flex; justify-content: space-between; align-items: center; margin-bottom: 40px;">
            <div style="font-size: 26px; font-weight: 800; color: #0E2B5C;">✴️ Excitel<div style="font-size: 11px; color: #605E5C; font-weight: 400;">The world is home</div></div>
            <div class="topbar-badge">SECURE_AUTH</div>
        </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("""
            <div style="background: #FFFFFF; border-radius: 16px; padding: 32px 36px; box-shadow: 0 10px 30px rgba(0,0,0,0.18);">
                <div style="text-align: center; margin-bottom: 20px;">
                    <div style="font-size: 24px; font-weight: 800; color: #0E2B5C; text-transform: uppercase;">Overtime Tracking Portal</div>
                    <div style="font-size: 13px; color: #605E5C; margin-top: 4px;">Sign in with your official Excitel credentials</div>
                </div>
        """, unsafe_allow_html=True)

        with st.form("login_form"):
            login_email = st.text_input("Official Email ID")
            login_password = st.text_input("Password", type="password")
            submit_login = st.form_submit_button("Sign In 🔐", use_container_width=True)

            if submit_login:
                if not login_email or not login_password:
                    st.error("Please provide both email and password.")
                else:
                    conn = get_connection()
                    try:
                        cursor = conn.cursor()
                        cursor.execute("SELECT name, role, password_hash FROM users WHERE email = %s", (login_email.strip().lower(),))
                        res = cursor.fetchone()
                    finally:
                        release_connection(conn)

                    if res:
                        db_name, db_role, db_pass_hash = res
                        if db_pass_hash == hash_password(login_password) or db_pass_hash == hashlib.sha256(login_password.encode()).hexdigest():
                            st.session_state.authenticated = True
                            st.session_state.user_email = login_email.strip().lower()
                            st.session_state.user_name = db_name
                            st.session_state.user_role = db_role
                            st.session_state.last_activity = time.time()
                            st.session_state.current_view = "portal"
                            record_audit(st.session_state.user_email, "USER_LOGIN", "PORTAL", "Successful authentication")
                            st.success("Authenticated! Loading portal...")
                            st.rerun()
                        else:
                            st.error("❌ Incorrect password.")
                    else:
                        st.error("❌ Email not registered in the system.")

        st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

# ==================== FETCH LOGGED-IN USER ====================
def get_logged_in_user():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT email, name, role, emp_id, tl_name, tl_id FROM users WHERE email = %s", (st.session_state.user_email,))
        res = cursor.fetchone()
        if res:
            return {"email": res[0], "name": res[1], "role": res[2], "empId": res[3], "tlName": res[4], "tlId": res[5]}
    finally:
        release_connection(conn)
    return {"email": st.session_state.user_email, "name": st.session_state.user_name, "role": st.session_state.user_role, "empId": "N/A", "tlName": "Unassigned", "tlId": ""}

user = get_logged_in_user()

# ==================== TOP NAVIGATION BAR ====================
PAGE_BADGE_MAP = {
    "portal": "OT_FORM",
    "history": "ACTIONED_OT",
    "dashboard": "TL_DASHBOARD",
    "reports": "REPORTS_ENGINE",
    "admin": "ADMIN_MANAGEMENT",
    "guidelines": "POLICY_RULES"
}
current_badge = PAGE_BADGE_MAP.get(st.session_state.current_view, "OT_TRACKER")

# Render top banner with live dynamic ticking clock via embedded JavaScript
st.markdown(f"""
    <div class="excitel-topbar">
        <div class="brand-cluster">
            <div>
                <div class="brand-title">✴️ Excitel</div>
                <div class="brand-sub">The world is home</div>
            </div>
            <div class="user-tag">👤 User: {user['name']}</div>
        </div>
        <div style="display: flex; align-items: center; gap: 15px;">
            <div class="topbar-badge">{current_badge}</div>
            <div id="live-time-widget" style="font-size: 13px; font-weight: 700; color: #0E2B5C; min-width: 175px; text-align: right;"></div>
        </div>
    </div>
    <script>
        function updateClock() {{
            const now = new Date();
            const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
            const dateStr = months[now.getMonth()] + ' ' + now.getDate() + ', ' + now.getFullYear();
            let hours = now.getHours();
            const minutes = String(now.getMinutes()).padStart(2, '0');
            const seconds = String(now.getSeconds()).padStart(2, '0');
            const ampm = hours >= 12 ? 'PM' : 'AM';
            hours = hours % 12;
            hours = hours ? hours : 12;
            const timeStr = hours + ':' + minutes + ':' + seconds + ' ' + ampm;
            const el = document.getElementById('live-time-widget');
            if (el) {{
                el.innerText = dateStr + ' | ' + timeStr;
            }}
        }}
        setInterval(updateClock, 1000);
        updateClock();
    </script>
""", unsafe_allow_html=True)

# ==================== FLOATING COMMAND NAVBAR ====================
st.markdown(f"""
    <div class="nav-pill-container">
        <div class="nav-user-label">
            <span>🛡️</span> {user['name']} ({user['role']})
        </div>
    </div>
""", unsafe_allow_html=True)

nav_cols = st.columns([1, 1, 1, 1, 1, 0.8])

with nav_cols[0]:
    if st.button("📄 OT Form", use_container_width=True):
        st.session_state.current_view = "portal"
        st.rerun()

with nav_cols[1]:
    if st.button("🕒 History", use_container_width=True):
        st.session_state.current_view = "history"
        st.rerun()

if user['role'] in ["TL", "Admin"]:
    with nav_cols[2]:
        if st.button("📊 Dashboard", use_container_width=True):
            st.session_state.current_view = "dashboard"
            st.rerun()

if user['role'] in ["TL", "Admin"]:
    with nav_cols[3]:
        if st.button("📈 Reports", use_container_width=True):
            st.session_state.current_view = "reports"
            st.rerun()

if user['role'] == "Admin":
    with nav_cols[4]:
        if st.button("⚙️ Admin", use_container_width=True):
            st.session_state.current_view = "admin"
            st.rerun()

with nav_cols[5]:
    if st.button("🚪 Logout", use_container_width=True):
        record_audit(user['email'], "USER_LOGOUT", "PORTAL", "Sign out button clicked")
        st.session_state.authenticated = False
        st.session_state.user_email = ""
        st.session_state.user_role = ""
        st.session_state.user_name = ""
        st.rerun()

st.markdown("<br>", unsafe_allow_html=True)

RATES = {'Calls': 12, 'Backend': 10, 'Tickets': 12, 'Complaints': 8, 'Email': 15}

def time_to_minutes(t_str):
    h, m = map(int, t_str.split(':'))
    return h * 60 + m

# Helper for conditional productivity & status coloring
def color_productivity_and_status(val):
    if isinstance(val, str) and '%' in val:
        try:
            num = float(val.replace('%', ''))
            if num >= 85.0:
                return 'color: #00A86B; font-weight: 800;'
            else:
                return 'color: #E03E3E; font-weight: 800;'
        except:
            pass
    if val == 'APPROVED':
        return 'background-color: #E6F8F0; color: #00A86B; font-weight: 800; border-radius: 12px; text-align: center;'
    elif val == 'REJECTED':
        return 'background-color: #FDE8E8; color: #E03E3E; font-weight: 800; border-radius: 12px; text-align: center;'
    elif val == 'PENDING':
        return 'background-color: #FEF3C7; color: #D97706; font-weight: 800; border-radius: 12px; text-align: center;'
    return ''

# ==================== 1. OT FORM PORTAL ====================
if st.session_state.current_view == "portal":
    st.markdown("""
        <div class="workspace-card">
            <div style="text-align: center; margin-bottom: 24px;">
                <h2 style="color: #0E2B5C; font-weight: 800; text-transform: uppercase; margin: 0;">⚡ Overtime Claim Portal</h2>
                <div style="color: #605E5C; font-size: 13px; font-weight: 600; margin-top: 4px;">Fast & Accurate Verification System</div>
            </div>
    """, unsafe_allow_html=True)
    
    target_name = user['name']
    target_emp_id = user['empId']
    target_tl = user['tlName']
    
    if user['role'] in ["TL", "Admin"]:
        conn = get_connection()
        try:
            emp_df = pd.read_sql("SELECT name FROM users WHERE role = 'Employee'", conn)
        finally:
            release_connection(conn)
        selected_proxy = st.selectbox("Proxy Submission (Optional):", options=["Select Employee..."] + emp_df['name'].tolist())
        if selected_proxy != "Select Employee...":
            conn = get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT name, emp_id, tl_name FROM users WHERE name = %s", (selected_proxy,))
                p_res = cursor.fetchone()
                if p_res:
                    target_name, target_emp_id, target_tl = p_res
            finally:
                release_connection(conn)

    col1, col2 = st.columns(2)
    with col1:
        st.text_input("Employee Name", value=target_name, disabled=True)
        st.text_input("Assigned Team Leader", value=target_tl, disabled=True)
    with col2:
        st.text_input("Employee ID", value=target_emp_id, disabled=True)
        req_date = st.date_input("Overtime Date", value=date.today())
        
    col3, col4 = st.columns(2)
    with col3:
        shift_start = st.time_input("Shift Start Time", value=datetime.strptime("09:00", "%H:%M").time())
        ot_start = st.time_input("OT Start Time", value=datetime.strptime("18:00", "%H:%M").time())
    with col4:
        shift_end = st.time_input("Shift End Time", value=datetime.strptime("18:00", "%H:%M").time())
        ot_end = st.time_input("OT End Time", value=datetime.strptime("21:00", "%H:%M").time())
        
    task_type = st.selectbox("Task Category", options=['Calls', 'Backend', 'Tickets', 'Complaints', 'Email'])
    
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Submit Overtime Request 🚀", type="primary", use_container_width=True):
        s_start_min = time_to_minutes(shift_start.strftime("%H:%M"))
        s_end_min = time_to_minutes(shift_end.strftime("%H:%M"))
        o_start_min = time_to_minutes(ot_start.strftime("%H:%M"))
        o_end_min = time_to_minutes(ot_end.strftime("%H:%M"))
        
        if o_end_min < o_start_min: o_end_min += 1440
        if s_end_min < s_start_min: s_end_min += 1440
        
        ot_hours = (o_end_min - o_start_min) / 60.0
        req_date_str = req_date.strftime("%Y-%m-%d")
        
        earliest_allowed = date.today() - timedelta(days=2)
        
        if req_date < earliest_allowed:
            st.error(f"❌ 48-Hour Lockout: Overtime claims prior to {earliest_allowed.strftime('%d-%b-%Y')} are locked out.")
        elif max(s_start_min, o_start_min) < min(s_end_min, o_end_min):
            st.error("❌ Shift Overlap Violation: Overtime cannot overlap with regular shift hours.")
        elif ot_hours <= 0:
            st.error("❌ Time Error: OT End must be strictly after OT Start.")
        elif ot_hours > 3.0:
            st.error(f"❌ Policy Violation: Maximum 3.0 OT hours allowed per calendar day (Requested: {ot_hours:.1f} hrs).")
        else:
            conn = get_connection()
            try:
                daily_check = pd.read_sql("SELECT ot_hours FROM ot_logs WHERE employee_name = %s AND date = %s AND status != 'Rejected'", conn, params=(target_name, req_date_str))
                existing_daily = daily_check['ot_hours'].sum()
                
                week_start = req_date - timedelta(days=req_date.weekday())
                week_end = week_start + timedelta(days=6)
                weekly_check = pd.read_sql(
                    "SELECT ot_hours FROM ot_logs WHERE employee_name = %s AND date >= %s AND date <= %s AND status != 'Rejected'", 
                    conn, 
                    params=(target_name, week_start.strftime("%Y-%m-%d"), week_end.strftime("%Y-%m-%d"))
                )
                existing_weekly = weekly_check['ot_hours'].sum()
                
                if existing_daily + ot_hours > 3.0:
                    st.error(f"❌ Daily Cap Exceeded: {existing_daily:.1f} hrs already logged on {req_date_str}. Exceeds 3.0h limit.")
                elif existing_weekly + ot_hours > 12.0:
                    st.error(f"❌ Weekly Cap Exceeded: {existing_weekly:.1f} hrs already logged this week. Exceeds 12.0h limit.")
                else:
                    std_rate = RATES.get(task_type, 12)
                    expected_out = ot_hours * std_rate
                    
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO ot_logs (date, employee_name, emp_id, shift_start, shift_end, ot_start, ot_end, ot_hours, task_type, status, tl_name, actual_output, standard_rate, expected_output, productivity, verified_hours, amount, approved_by, approved_at, rejection_reason)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s, %s, 0, 0, 0, '', '', '')
                    """, (req_date_str, target_name, target_emp_id, shift_start.strftime("%H:%M"), shift_end.strftime("%H:%M"), ot_start.strftime("%H:%M"), ot_end.strftime("%H:%M"), ot_hours, task_type, "Pending", target_tl, std_rate, expected_out))
                    
                    cursor.execute("SELECT email FROM users WHERE name = %s", (target_tl,))
                    tl_email_res = cursor.fetchone()
                    conn.commit()
                    
                    record_audit(user['email'], "SUBMIT_OT", target_name, f"Submitted {ot_hours}h for {req_date_str}")
                    if tl_email_res:
                        send_notification(tl_email_res[0], f"📥 New OT Claim: {target_name} logged {ot_hours}h on {req_date_str}.")
                    st.success(f"✅ OT Request logged successfully for {target_name} ({ot_hours} hrs)!")
            finally:
                release_connection(conn)

    st.markdown("</div>", unsafe_allow_html=True)

# ==================== 2. HISTORY TAB (EXCITEL UI) ====================
elif st.session_state.current_view == "history":
    st.markdown("<div class='workspace-card'>", unsafe_allow_html=True)
    
    conn = get_connection()
    try:
        df = pd.read_sql("SELECT * FROM ot_logs WHERE employee_name = %s", conn, params=(user['name'],))
    finally:
        release_connection(conn)
    
    if df.empty:
        st.info("No recorded overtime entries found.")
    else:
        # Calculate Top 5 Metrics
        total_reqs = len(df)
        approved_reqs = len(df[df['status'] == 'Approved'])
        rejected_reqs = len(df[df['status'] == 'Rejected'])
        approved_hours = df[df['status'] == 'Approved']['verified_hours'].sum()
        total_payout = df[df['status'] == 'Approved']['amount'].sum()
        
        # Render the 5 Metrics Card Row
        st.markdown(f"""
            <div class="kpi-grid">
                <div class="kpi-box kpi-navy">
                    <div class="kpi-val">{total_reqs}</div>
                    <div class="kpi-title">TOTAL REQUESTS</div>
                </div>
                <div class="kpi-box kpi-green">
                    <div class="kpi-val">{approved_reqs}</div>
                    <div class="kpi-title">APPROVED</div>
                </div>
                <div class="kpi-box kpi-red">
                    <div class="kpi-val">{rejected_reqs}</div>
                    <div class="kpi-title">REJECTED</div>
                </div>
                <div class="kpi-box kpi-cyan">
                    <div class="kpi-val">{approved_hours:.1f}</div>
                    <div class="kpi-title">APPRVD HOURS</div>
                </div>
                <div class="kpi-box kpi-blue">
                    <div class="kpi-val">₹{total_payout:.0f}</div>
                    <div class="kpi-title">TOTAL AMOUNT</div>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        # Format the interactive sortable table
        display_df = df.copy()
        display_df['formatted_date'] = pd.to_datetime(display_df['date']).dt.strftime('%d-%b-%Y')
        display_df['hours_str'] = display_df['ot_hours'].apply(lambda x: f"{x:.0f}h" if x.is_integer() else f"{x:.1f}h")
        display_df['prod_pct'] = (display_df['productivity'] * 100).round(0).astype(int).astype(str) + '%'
        display_df['status_upper'] = display_df['status'].str.upper()
        display_df['amount_formatted'] = display_df['amount'].apply(lambda x: f"₹{x:.0f}")
        
        final_table = display_df[['formatted_date', 'employee_name', 'hours_str', 'task_type', 'prod_pct', 'status_upper', 'amount_formatted']].copy()
        final_table.columns = ['DATE', 'EMPLOYEE', 'HOURS', 'TASK', 'PROD %', 'STATUS', 'AMOUNT']
        
        styled_df = final_table.style.map(color_productivity_and_status, subset=['PROD %', 'STATUS'])
        
        st.dataframe(styled_df, use_container_width=True, hide_index=True)
        
    st.markdown("</div>", unsafe_allow_html=True)

# ==================== 3. APPROVAL DASHBOARD ====================
elif st.session_state.current_view == "dashboard":
    st.markdown("<div class='workspace-card'>", unsafe_allow_html=True)
    
    conn = get_connection()
    try:
        query = "SELECT * FROM ot_logs"
        if user['role'] == 'TL':
            query += f" WHERE tl_name = '{user['name']}'"
        df = pd.read_sql(query, conn)
    finally:
        release_connection(conn)
    
    if df.empty:
        st.info("No overtime claims in your queue.")
    else:
        total_reqs = len(df)
        approved_reqs = len(df[df['status'] == 'Approved'])
        rejected_reqs = len(df[df['status'] == 'Rejected'])
        approved_hours = df[df['status'] == 'Approved']['verified_hours'].sum()
        total_payout = df[df['status'] == 'Approved']['amount'].sum()
        
        # 5 Top Metrics for Supervisor
        st.markdown(f"""
            <div class="kpi-grid">
                <div class="kpi-box kpi-navy">
                    <div class="kpi-val">{total_reqs}</div>
                    <div class="kpi-title">TOTAL REQUESTS</div>
                </div>
                <div class="kpi-box kpi-green">
                    <div class="kpi-val">{approved_reqs}</div>
                    <div class="kpi-title">APPROVED</div>
                </div>
                <div class="kpi-box kpi-red">
                    <div class="kpi-val">{rejected_reqs}</div>
                    <div class="kpi-title">REJECTED</div>
                </div>
                <div class="kpi-box kpi-cyan">
                    <div class="kpi-val">{approved_hours:.1f}</div>
                    <div class="kpi-title">APPRVD HOURS</div>
                </div>
                <div class="kpi-box kpi-blue">
                    <div class="kpi-val">₹{total_payout:.0f}</div>
                    <div class="kpi-title">TOTAL AMOUNT</div>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        pending_df = df[df['status'] == 'Pending']
        if not pending_df.empty:
            st.markdown("### ⚡ Pending Claims Requiring Verification")
            for idx, row in pending_df.iterrows():
                with st.expander(f"📌 {row['employee_name']} | Date: {row['date']} | {row['ot_hours']}h ({row['task_type']})"):
                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.write(f"**Team Leader:** {row['tl_name']}")
                        st.write(f"**Shift Hours:** {row['shift_start']} - {row['shift_end']}")
                        st.write(f"**OT Duration:** {row['ot_start']} - {row['ot_end']}")
                        st.write(f"**Expected Target Units:** {row['expected_output']}")
                    with col_b:
                        if row['employee_name'] == user['name']:
                            st.warning("🔒 Self-Approval Guardrail: You cannot verify or approve your own claim.")
                        else:
                            actual_out = st.number_input(
                                f"Enter Actual Output for Claim #{row['id']}", 
                                min_value=1.0, 
                                value=float(row['expected_output']), 
                                key=f"out_{row['id']}"
                            )
                            rej_reason = st.text_input("Rejection Reason (Required if Rejecting):", key=f"rej_{row['id']}")
                            
                            c_btn1, c_btn2 = st.columns(2)
                            if c_btn1.button("Approve ✅", key=f"btn_app_{row['id']}", use_container_width=True):
                                expected = row['expected_output']
                                prod = (actual_out / expected) if expected > 0 else 0
                                v_hrs = row['ot_hours'] if prod >= 0.7 else (row['ot_hours'] * 0.5 if prod >= 0.5 else 0)
                                amt = v_hrs * 120
                                
                                conn = get_connection()
                                try:
                                    cursor = conn.cursor()
                                    cursor.execute("""
                                        UPDATE ot_logs SET status = 'Approved', actual_output = %s, productivity = %s, verified_hours = %s, amount = %s, approved_by = %s, approved_at = %s
                                        WHERE id = %s
                                    """, (actual_out, prod, v_hrs, amt, user['name'], datetime.now().strftime("%Y-%m-%d %H:%M"), row['id']))
                                    cursor.execute("SELECT email FROM users WHERE name = %s", (row['employee_name'],))
                                    emp_mail = cursor.fetchone()
                                    conn.commit()
                                    record_audit(user['email'], "APPROVE_OT", row['employee_name'], f"Approved record #{row['id']}")
                                finally:
                                    release_connection(conn)
                                    
                                if emp_mail:
                                    send_notification(emp_mail[0], f"🎉 OT Approved: Your {row['ot_hours']}h claim on {row['date']} has been approved.")
                                st.success("Claim approved!")
                                st.rerun()
                                
                            if c_btn2.button("Reject ❌", key=f"btn_rej_{row['id']}", use_container_width=True):
                                if not rej_reason.strip():
                                    st.error("Rejection Reason is strictly mandatory.")
                                else:
                                    expected = row['expected_output']
                                    prod = (actual_out / expected) if expected > 0 else 0
                                    conn = get_connection()
                                    try:
                                        cursor = conn.cursor()
                                        cursor.execute("""
                                            UPDATE ot_logs SET status = 'Rejected', actual_output = %s, productivity = %s, verified_hours = 0, amount = 0, approved_by = %s, approved_at = %s, rejection_reason = %s
                                            WHERE id = %s
                                        """, (actual_out, prod, user['name'], datetime.now().strftime("%Y-%m-%d %H:%M"), rej_reason.strip(), row['id']))
                                        cursor.execute("SELECT email FROM users WHERE name = %s", (row['employee_name'],))
                                        emp_mail = cursor.fetchone()
                                        conn.commit()
                                        record_audit(user['email'], "REJECT_OT", row['employee_name'], f"Reason: {rej_reason.strip()}")
                                    finally:
                                        release_connection(conn)
                                        
                                    if emp_mail:
                                        send_notification(emp_mail[0], f"⚠️ OT Rejected: Your {row['ot_hours']}h claim on {row['date']} was rejected. Reason: {rej_reason.strip()}")
                                    st.warning("Claim rejected.")
                                    st.rerun()
                                    
        st.markdown("### 📋 Master Claims Data Table")
        disp_df = df.copy()
        disp_df['formatted_date'] = pd.to_datetime(disp_df['date']).dt.strftime('%d-%b-%Y')
        disp_df['hours_str'] = disp_df['ot_hours'].apply(lambda x: f"{x:.0f}h" if x.is_integer() else f"{x:.1f}h")
        disp_df['prod_pct'] = (disp_df['productivity'] * 100).round(0).astype(int).astype(str) + '%'
        disp_df['status_upper'] = disp_df['status'].str.upper()
        disp_df['amount_formatted'] = disp_df['amount'].apply(lambda x: f"₹{x:.0f}")
        
        master_table = disp_df[['formatted_date', 'employee_name', 'hours_str', 'task_type', 'prod_pct', 'status_upper', 'amount_formatted']].copy()
        master_table.columns = ['DATE', 'EMPLOYEE', 'HOURS', 'TASK', 'PROD %', 'STATUS', 'AMOUNT']
        
        styled_master = master_table.style.map(color_productivity_and_status, subset=['PROD %', 'STATUS'])
        st.dataframe(styled_master, use_container_width=True, hide_index=True)

    st.markdown("</div>", unsafe_allow_html=True)

# ==================== 4. REPORTS ENGINE ====================
elif st.session_state.current_view == "reports":
    st.markdown("""
        <div class="workspace-card">
            <h2 style="color: #0E2B5C; font-weight: 800; text-transform: uppercase;">📈 Financial & Productivity Reports</h2>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    with col1:
        rep_month = st.selectbox("Month", options=list(range(1, 13)), index=date.today().month - 1)
    with col2:
        rep_year = st.selectbox("Year", options=[2025, 2026, 2027], index=1)
        
    conn = get_connection()
    try:
        rep_df = pd.read_sql("SELECT * FROM ot_logs", conn)
    finally:
        release_connection(conn)
        
    if not rep_df.empty:
        rep_df['date_dt'] = pd.to_datetime(rep_df['date'])
        f_df = rep_df[(rep_df['date_dt'].dt.month == rep_month) & (rep_df['date_dt'].dt.year == rep_year)]
        
        if user['role'] == 'TL':
            f_df = f_df[f_df['tl_name'] == user['name']]
            
        summary = f_df.groupby(['employee_name', 'emp_id']).agg(
            total_days=('date', 'count'),
            total_hrs=('ot_hours', 'sum'),
            app_hrs=('verified_hours', 'sum'),
            total_amt=('amount', 'sum')
        ).reset_index()
        
        summary.columns = ['EMPLOYEE NAME', 'EMPLOYEE ID', 'TOTAL DAYS', 'REQUESTED HOURS', 'APPROVED HOURS', 'TOTAL PAYOUT (₹)']
        st.dataframe(summary, use_container_width=True, hide_index=True)
        
        csv_data = summary.to_csv(index=False).encode('utf-8')
        st.download_button("Export Report CSV 📥", csv_data, f"Excitel_OT_Report_{rep_month}_{rep_year}.csv", "text/csv")
        
    st.markdown("</div>", unsafe_allow_html=True)

# ==================== 5. ADMIN MANAGEMENT ====================
elif st.session_state.current_view == "admin":
    st.markdown("<div class='workspace-card'>", unsafe_allow_html=True)
    if user['role'] != "Admin":
        st.error("Access restricted to Admins.")
    else:
        st.markdown("<h2 style='color: #0E2B5C; font-weight: 800;'>⚙️ System & User Directory Management</h2>", unsafe_allow_html=True)
        
        conn = get_connection()
        try:
            users_df = pd.read_sql("SELECT email, name, role, emp_id, tl_name, tl_id FROM users", conn)
        finally:
            release_connection(conn)
            
        st.markdown("#### Registered System Users")
        users_df.columns = ['EMAIL', 'NAME', 'ROLE', 'EMP ID', 'TL NAME', 'TL ID']
        st.dataframe(users_df, use_container_width=True, hide_index=True)
        
        csv_users = users_df.to_csv(index=False).encode('utf-8')
        st.download_button("Export Users Directory CSV 📥", csv_users, "system_users_directory.csv", "text/csv")
        
    st.markdown("</div>", unsafe_allow_html=True)

# ==================== PERSISTENT COMPLIANCE FOOTER ====================
st.markdown("""
    <div style="text-align: center; padding: 20px 0; color: #FFFFFF; font-size: 12px; font-weight: 600;">
        © Excitel Broadband Private Limited — Enterprise Overtime Tracking & Security Protocol
    </div>
""", unsafe_allow_html=True)
