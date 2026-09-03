import streamlit as st
import psycopg2
from psycopg2 import pool
import pandas as pd
from datetime import datetime, date, timedelta
from fpdf import FPDF
import altair as alt
import os
import hashlib
import time

# ==================== AUTOMATIC LIGHT THEME CONFIG ====================
os.makedirs(".streamlit", exist_ok=True)
config_path = ".streamlit/config.toml"
if not os.path.exists(config_path):
    with open(config_path, "w") as f:
        f.write("""
[theme]
base="light"
primaryColor="#FF6B00"
backgroundColor="#F8F9FA"
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
    pool_conn = get_db_pool()
    return pool_conn.getconn()

def release_connection(conn):
    if conn:
        get_db_pool().putconn(conn)

# ==================== CRYPTOGRAPHIC UTILITIES ====================
SALT_SECRET = "Excitel_Secure_Salt_2026"

def hash_password(password):
    """HMAC Salted PBKDF2 Password Hashing with 100,000 iterations"""
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

        # Add rejection_reason column if migrating from older versions
        cursor.execute("""
            ALTER TABLE ot_logs 
            ADD COLUMN IF NOT EXISTS rejection_reason TEXT DEFAULT '';
        """)
        
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

st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Segoe+UI:wght@400;600;700&display=swap');
        html, body, [class*="css"] {
            font-family: 'Segoe UI', sans-serif;
            background-color: #F8F9FA;
            color: #201F1E;
        }
        .fluent-card {
            background: #FFFFFF;
            border: 1px solid #E1DFDD;
            border-radius: 12px;
            padding: 24px 30px;
            box-shadow: 0 8px 24px rgba(0,0,0,0.06), 0 2px 6px rgba(0,0,0,0.04);
            margin-bottom: 20px;
            border-top: 6px solid #FF6B00;
        }
        .policy-card {
            background: #FFFFFF;
            border: 1px solid #E1DFDD;
            border-radius: 10px;
            padding: 20px 24px;
            box-shadow: 0 4px 14px rgba(0,0,0,0.04);
            margin-bottom: 16px;
        }
        .brand-logo {
            font-size: 26px;
            font-weight: 700;
            letter-spacing: 0.5px;
            color: #1E3A8A;
            text-transform: uppercase;
        }
        .brand-logo span { color: #FF6B00; }
        .stButton>button {
            background: linear-gradient(135deg, #1E3A8A 0%, #152A63 100%) !important;
            color: white !important;
            border-radius: 8px !important;
            font-weight: 600 !important;
            border: none !important;
            padding: 10px 24px !important;
            box-shadow: 0 4px 12px rgba(30, 58, 138, 0.25);
            width: 100%;
        }
        .stButton>button:hover {
            background: linear-gradient(135deg, #FF6B00 0%, #E05D00 100%) !important;
        }
        .table-header {
            font-weight: 600;
            color: #1E3A8A;
            padding-bottom: 8px;
            border-bottom: 2px solid #E1DFDD;
            margin-bottom: 12px;
        }
        .notif-box {
            background-color: #EFF6FF;
            border-left: 4px solid #1E3A8A;
            padding: 10px 14px;
            border-radius: 6px;
            margin-bottom: 8px;
            font-size: 13px;
        }
        .footer-note {
            text-align: center;
            color: #605E5C;
            font-size: 13px;
            margin-top: 40px;
            padding-top: 15px;
            border-top: 1px solid #E1DFDD;
        }
        h1, h2, h3 { color: #1E3A8A; font-weight: 600; }
        [data-testid="stSidebar"] {
            background-color: #FFFFFF;
            border-right: 1px solid #E1DFDD;
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

# ==================== MODAL DIALOGS ====================
@st.dialog("✏️ Edit User Profile")
def edit_user_dialog(user_dict):
    st.markdown(f"<div style='color: #605E5C; margin-bottom: 15px;'>Updating records for: <b>{user_dict['email']}</b></div>", unsafe_allow_html=True)
    
    e_name = st.text_input("Full Name", value=str(user_dict['name']))
    role_opts = ["Employee", "TL", "Admin"]
    cur_role = str(user_dict['role'])
    r_idx = role_opts.index(cur_role) if cur_role in role_opts else 0
    e_role = st.selectbox("Role Assignment", options=role_opts, index=r_idx)
    e_emp_id = st.text_input("Employee ID", value=str(user_dict['emp_id'] if user_dict['emp_id'] else ""))
    e_tl_name = st.text_input("Team Leader Name", value=str(user_dict['tl_name'] if user_dict['tl_name'] else ""))
    e_tl_id = st.text_input("Team Leader ID", value=str(user_dict['tl_id'] if user_dict['tl_id'] else ""))
    
    st.markdown("---")
    e_pass = st.text_input("Reset Password (Optional - Leave blank to keep current)", type="password")
    
    st.markdown("<br>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    if col1.button("Save Changes ✅", type="primary", use_container_width=True):
        conn = get_connection()
        try:
            cursor = conn.cursor()
            if e_pass:
                new_phash = hash_password(e_pass)
                cursor.execute("""
                    UPDATE users SET name = %s, role = %s, emp_id = %s, tl_name = %s, tl_id = %s, password_hash = %s WHERE email = %s
                """, (e_name, e_role, e_emp_id, e_tl_name, e_tl_id, new_phash, user_dict['email']))
                record_audit(st.session_state.user_email, "EDIT_USER_PASSWORD", user_dict['email'], f"Updated role to {e_role}")
            else:
                cursor.execute("""
                    UPDATE users SET name = %s, role = %s, emp_id = %s, tl_name = %s, tl_id = %s WHERE email = %s
                """, (e_name, e_role, e_emp_id, e_tl_name, e_tl_id, user_dict['email']))
                record_audit(st.session_state.user_email, "EDIT_USER", user_dict['email'], f"Updated role to {e_role}")
            conn.commit()
            st.success(f"User {user_dict['email']} updated successfully!")
            st.rerun()
        except Exception as update_err:
            st.error(f"Error updating user: {update_err}")
        finally:
            release_connection(conn)
            
    if col2.button("Cancel", use_container_width=True):
        st.rerun()

@st.dialog("🗑️ Confirm Deletion")
def delete_user_dialog(email, current_user_email):
    st.markdown(f"""
        <div style='background-color: #FEE2E2; padding: 15px; border-radius: 8px; border-left: 5px solid #991B1B; margin-bottom: 20px;'>
            <h4 style='color: #991B1B; margin: 0;'>⚠️ Critical Action Warning</h4>
            <p style='color: #7F1D1D; margin: 5px 0 0 0;'>You are about to permanently delete the profile and access for:<br><br><b>{email}</b><br><br>This action cannot be undone.</p>
        </div>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    if col1.button("Yes, Delete User 🗑️", type="primary", use_container_width=True):
        if email == current_user_email:
            st.error("❌ Action Blocked: You cannot delete your own active admin account!")
        else:
            conn = get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM users WHERE email = %s", (email,))
                conn.commit()
                record_audit(current_user_email, "DELETE_USER", email, "Permanent deletion")
                st.success("User deleted successfully!")
                st.rerun()
            except Exception as del_err:
                st.error(f"Error deleting user: {del_err}")
            finally:
                release_connection(conn)
                
    if col2.button("Cancel", use_container_width=True):
        st.rerun()

# ==================== LOGIN GATEWAY ====================
if not st.session_state.authenticated:
    col_l1, col_l2, col_l3 = st.columns([1, 1.2, 1])
    with col_l2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("""
            <div class="fluent-card" style="text-align: center;">
                <div class="brand-logo" style="margin-bottom: 10px;">EXCIT<span>EL</span></div>
                <h3 style="margin-bottom: 5px;">Overtime Tracking Portal</h3>
                <p style="color: #605E5C; font-size: 13px;">Please sign in with your official credentials.</p>
            </div>
        """, unsafe_allow_html=True)
        
        with st.form("login_form"):
            login_email = st.text_input("Official Email ID")
            login_password = st.text_input("Password", type="password")
            submit_login = st.form_submit_button("Sign In 🔐", use_container_width=True)
            
            if submit_login:
                if not login_email or not login_password:
                    st.error("Please enter both email and password.")
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
                        # Backward compatible: matches PBKDF2 or standard SHA-256 legacy
                        if db_pass_hash == hash_password(login_password) or db_pass_hash == hashlib.sha256(login_password.encode()).hexdigest():
                            st.session_state.authenticated = True
                            st.session_state.user_email = login_email.strip().lower()
                            st.session_state.user_name = db_name
                            st.session_state.user_role = db_role
                            st.session_state.last_activity = time.time()
                            st.session_state.current_view = "portal"
                            record_audit(st.session_state.user_email, "USER_LOGIN", "PORTAL", "Successful authentication")
                            st.success("Login successful! Loading portal...")
                            st.rerun()
                        else:
                            st.error("❌ Incorrect password. Please try again.")
                    else:
                        st.error("❌ Email not found in authorized system registry.")
    st.stop()

# ==================== FETCH LOGGED-IN USER DETAILS ====================
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

# ==================== SIDEBAR & NOTIFICATIONS ====================
st.sidebar.markdown("<div class='brand-logo' style='margin-bottom:15px;'>EXCIT<span>EL</span></div>", unsafe_allow_html=True)
st.sidebar.markdown(f"**Signed In As:**  \n`{user['name']}`")
st.sidebar.markdown(f"**Role:** `{user['role']}`")

st.sidebar.markdown("---")
conn = get_connection()
try:
    notifs_df = pd.read_sql("SELECT message, created_at FROM notifications WHERE recipient_email = %s ORDER BY id DESC LIMIT 5", conn, params=(user['email'],))
    # Query pending counts for live dashboard badge
    if user['role'] == 'TL':
        pending_count = pd.read_sql("SELECT COUNT(*) FROM ot_logs WHERE tl_name = %s AND status = 'Pending'", conn, params=(user['name'],)).iloc[0, 0]
    else:
        pending_count = pd.read_sql("SELECT COUNT(*) FROM ot_logs WHERE status = 'Pending'", conn).iloc[0, 0]
finally:
    release_connection(conn)

with st.sidebar.expander(f"🔔 Alerts & Notifications ({len(notifs_df)})", expanded=not notifs_df.empty):
    if notifs_df.empty:
        st.write("No new alerts.")
    else:
        for _, n_row in notifs_df.iterrows():
            st.markdown(f"<div class='notif-box'><b>{n_row['created_at']}</b><br>{n_row['message']}</div>", unsafe_allow_html=True)

st.sidebar.markdown("---")
if st.sidebar.button("🚪 Sign Out", use_container_width=True):
    record_audit(user['email'], "USER_LOGOUT", "PORTAL", "Manual sign out")
    st.session_state.authenticated = False
    st.session_state.user_email = ""
    st.session_state.user_role = ""
    st.session_state.user_name = ""
    st.rerun()

st.sidebar.caption("⏱️ Session timeout: 30m idle")

# ==================== LIVE TAB BADGE NAVIGATION ====================
st.markdown(f"<div style='font-size: 14px; font-weight: 600; color: #1E3A8A; margin-bottom: 8px;'>🛡️ Secure Session: <b>{user['name']}</b> ({user['role']})</div>", unsafe_allow_html=True)

nav_cols = st.columns(5)

with nav_cols[0]:
    if st.button("📝 Form", use_container_width=True):
        st.session_state.current_view = "portal"
        st.rerun()

if user['role'] in ["Employee", "Admin"]:
    with nav_cols[1]:
        if st.button("📋 History", use_container_width=True):
            st.session_state.current_view = "history"
            st.rerun()

if user['role'] in ["TL", "Admin"]:
    with nav_cols[2]:
        dash_label = f"📊 Dashboard ({pending_count})" if pending_count > 0 else "📊 Dashboard"
        if st.button(dash_label, use_container_width=True):
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

st.markdown("<hr style='margin-top: 15px; margin-bottom: 25px; border: none; border-top: 1px solid #E1DFDD;'>", unsafe_allow_html=True)

RATES = {'Calls': 12, 'Backend': 10, 'Tickets': 12, 'Complaints': 8, 'Email': 15}

def time_to_minutes(t_str):
    h, m = map(int, t_str.split(':'))
    return h * 60 + m

def highlight_status(val):
    if val == 'Approved':
        return 'background-color: #D1FAE5; color: #065F46; font-weight: bold;'
    elif val == 'Pending':
        return 'background-color: #FEF3C7; color: #92400E; font-weight: bold;'
    elif val == 'Rejected':
        return 'background-color: #FEE2E2; color: #991B1B; font-weight: bold;'
    return ''

# ==================== 1. OT FORM PORTAL ====================
if st.session_state.current_view == "portal":
    st.markdown("""
        <div class="fluent-card">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <h2 style="margin: 0 0 5px 0; color: #1E3A8A;">⚡ Overtime Entry Portal</h2>
                    <p style="color: #605E5C; font-size: 14px; margin: 0;">Submit and manage overtime requests with real-time policy verification.</p>
                </div>
                <div class="brand-logo">EXCIT<span>EL</span></div>
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    target_name = user['name']
    target_emp_id = user['empId']
    target_tl = user['tlName']
    
    if user['role'] in ["TL", "Admin"]:
        st.markdown("### 🛡️ Submit on Behalf of Employee (Proxy)")
        conn = get_connection()
        try:
            emp_df = pd.read_sql("SELECT name FROM users WHERE role = 'Employee'", conn)
        finally:
            release_connection(conn)
        selected_proxy = st.selectbox("Select Employee:", options=["Select Employee..."] + emp_df['name'].tolist())
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
        req_date = st.date_input("OT Date", value=date.today())
        
    col3, col4 = st.columns(2)
    with col3:
        shift_start = st.time_input("Shift Start Time", value=datetime.strptime("09:00", "%H:%M").time())
        ot_start = st.time_input("OT Start Time", value=datetime.strptime("18:00", "%H:%M").time())
    with col4:
        shift_end = st.time_input("Shift End Time", value=datetime.strptime("18:00", "%H:%M").time())
        ot_end = st.time_input("OT End Time", value=datetime.strptime("21:00", "%H:%M").time())
        
    task_type = st.selectbox("Task Type", options=['Calls', 'Backend', 'Tickets', 'Complaints', 'Email'])
    
    if st.button("Submit OT Request 🚀", type="primary"):
        s_start_min = time_to_minutes(shift_start.strftime("%H:%M"))
        s_end_min = time_to_minutes(shift_end.strftime("%H:%M"))
        o_start_min = time_to_minutes(ot_start.strftime("%H:%M"))
        o_end_min = time_to_minutes(ot_end.strftime("%H:%M"))
        
        if o_end_min < o_start_min: o_end_min += 1440
        if s_end_min < s_start_min: s_end_min += 1440
        
        ot_hours = (o_end_min - o_start_min) / 60.0
        req_date_str = req_date.strftime("%Y-%m-%d")
        
        # Retroactive Cutoff Check: Max 48 hours back allowed
        earliest_allowed = date.today() - timedelta(days=2)
        
        if req_date < earliest_allowed:
            st.error(f"❌ Submission Lockout: Overtime claims older than 48 hours ({earliest_allowed.strftime('%d-%b-%Y')}) cannot be logged.")
        elif max(s_start_min, o_start_min) < min(s_end_min, o_end_min):
            st.error("❌ Overtime hours cannot overlap regular shift timings.")
        elif ot_hours <= 0:
            st.error("❌ OT End time must be after Start time.")
        elif ot_hours > 3.0:
            st.error(f"❌ Policy Violation: Overtime cannot exceed 3.0 hours in a single day (Requested: {ot_hours:.1f} hrs).")
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
                    st.error(f"❌ Daily Limit Exceeded: You already have {existing_daily:.1f} hrs logged on {req_date_str}. Adding {ot_hours:.1f} hrs exceeds the 3.0h daily limit.")
                elif existing_weekly + ot_hours > 12.0:
                    st.error(f"❌ Weekly Limit Exceeded: You have {existing_weekly:.1f} hrs logged this week. Adding {ot_hours:.1f} hrs exceeds the 12.0h weekly limit.")
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
                        send_notification(tl_email_res[0], f"📥 New OT Request: {target_name} logged {ot_hours}h for {req_date_str} ({task_type}).")
                    
                    st.success(f"✅ OT successfully requested for {target_name} ({ot_hours} hrs)!")
            finally:
                release_connection(conn)

# ==================== 2. MY HISTORY ====================
elif st.session_state.current_view == "history":
    if user['role'] not in ["Employee", "Admin"]:
        st.error("⛔ Access Denied. History view is restricted to Employees.")
    else:
        st.markdown("""
            <div class="fluent-card">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <h2 style="margin: 0 0 5px 0; color: #1E3A8A;">📋 My Overtime History</h2>
                        <p style="color: #605E5C; font-size: 14px; margin: 0;">Review your submitted overtime records, verification statuses, and payout summaries.</p>
                    </div>
                    <div class="brand-logo">EXCIT<span>EL</span></div>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        conn = get_connection()
        try:
            df = pd.read_sql("SELECT * FROM ot_logs WHERE employee_name = %s", conn, params=(user['name'],))
        finally:
            release_connection(conn)
        
        if df.empty:
            st.info("No OT records found.")
        else:
            fc1, fc2, fc3 = st.columns([1.5, 1.5, 2])
            with fc1:
                start_date_filter = st.date_input("Start Date", value=date(date.today().year, date.today().month, 1))
            with fc2:
                end_date_filter = st.date_input("End Date", value=date.today())
            with fc3:
                # Modern Segment Filter Chips
                status_filter = st.segmented_control("Status Filter", options=["All", "Pending", "Approved", "Rejected"], default="All")
                
            df['date_dt'] = pd.to_datetime(df['date']).dt.date
            filtered_history = df[(df['date_dt'] >= start_date_filter) & (df['date_dt'] <= end_date_filter)]
            if status_filter != "All":
                filtered_history = filtered_history[filtered_history['status'] == status_filter]
                
            total_hrs = filtered_history['ot_hours'].sum()
            app_hrs = filtered_history[filtered_history['status'] == 'Approved']['verified_hours'].sum()
            total_amt = filtered_history['amount'].sum()
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Filtered Hours Requested", f"{total_hrs:.1f} hrs")
            c2.metric("Approved Payable Hours", f"{app_hrs:.1f} hrs")
            c3.metric("Filtered Payout Amount", f"₹{total_amt:.0f}")
            
            history_display = filtered_history[['date', 'ot_hours', 'task_type', 'expected_output', 'actual_output', 'productivity', 'status', 'amount', 'rejection_reason']].copy()
            history_display.rename(columns={
                'date': 'Date',
                'ot_hours': 'OT Hours',
                'task_type': 'Task Type',
                'expected_output': 'Target Output',
                'actual_output': 'Actual Output',
                'productivity': 'Productivity',
                'status': 'Status',
                'amount': 'Payout Amount',
                'rejection_reason': 'Rejection Notes'
            }, inplace=True)
            
            styled_history = (
                history_display.style
                .map(highlight_status, subset=['Status'])
                .format({
                    'OT Hours': '{:.1f} hrs',
                    'Target Output': '{:.0f}',
                    'Actual Output': '{:.0f}',
                    'Productivity': '{:.0%}',
                    'Payout Amount': '₹{:.0f}'
                })
            )
            st.dataframe(styled_history, use_container_width=True, hide_index=True)

# ==================== 3. APPROVAL DASHBOARD ====================
elif st.session_state.current_view == "dashboard":
    if user['role'] not in ["TL", "Admin"]:
        st.error("⛔ Access Denied. Dashboard is restricted to Team Leaders and Admins.")
    else:
        st.markdown("""
            <div class="fluent-card">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <h2 style="margin: 0 0 5px 0; color: #1E3A8A;">📊 TL Approval & Analytics Dashboard</h2>
                        <p style="color: #605E5C; font-size: 14px; margin: 0;">Approve requests individually or use <b>Batch Approval</b> to clear requests in bulk.</p>
                    </div>
                    <div class="brand-logo">EXCIT<span>EL</span></div>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        conn = get_connection()
        try:
            query = "SELECT * FROM ot_logs"
            if user['role'] == 'TL':
                query += f" WHERE tl_name = '{user['name']}'"
            df = pd.read_sql(query, conn)
        finally:
            release_connection(conn)
        
        if df.empty:
            st.info("No OT records to review.")
        else:
            total_ot = df['ot_hours'].sum()
            total_cost = df[df['status'] == 'Approved']['amount'].sum()
            pending_cnt = len(df[df['status'] == 'Pending'])
            approved_cnt = len(df[df['status'] == 'Approved'])
            
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total OT Hours", f"{total_ot:.1f}")
            m2.metric("Total OT Cost", f"₹{total_cost:.0f}")
            m3.metric("Pending Approvals", pending_cnt)
            m4.metric("Approved Requests", approved_cnt)
            
            st.markdown("### 📈 Cost & Hours Analytics")
            ch1, ch2 = st.columns(2)
            with ch1:
                status_counts = df['status'].value_counts().reset_index()
                status_counts.columns = ['Status', 'Count']
                chart_status = alt.Chart(status_counts).mark_arc(innerRadius=40).encode(
                    theta=alt.Theta(field="Count", type="quantitative"),
                    color=alt.Color(field="Status", type="nominal", scale=alt.Scale(domain=['Pending', 'Approved', 'Rejected'], range=['#F59E0B', '#10B981', '#EF4444']))
                ).properties(height=200)
                st.altair_chart(chart_status, use_container_width=True)
            with ch2:
                trend_df = df[df['status'] == 'Approved'].groupby('date')['amount'].sum().reset_index()
                if not trend_df.empty:
                    chart_trend = alt.Chart(trend_df).mark_line(point=True, color='#FF6B00').encode(
                        x=alt.X('date:T', title='Date'),
                        y=alt.Y('amount:Q', title='Approved Payout (₹)')
                    ).properties(height=200)
                    st.altair_chart(chart_trend, use_container_width=True)
                else:
                    st.info("No approved payout trends to graph yet.")

            # Batch Approvals Section
            st.markdown("### ⚡ Batch Approval Action")
            pending_df = df[df['status'] == 'Pending']
            
            if pending_df.empty:
                st.success("🎉 All caught up! No pending requests.")
            else:
                with st.expander("⚡ Multi-Select Batch Approval", expanded=True):
                    st.write("Select multiple pending requests to approve simultaneously with 100% verified targets:")
                    selected_ids = []
                    for idx, r in pending_df.iterrows():
                        col_chk, col_det = st.columns([0.5, 9.5])
                        with col_chk:
                            chk = st.checkbox("", key=f"batch_chk_{r['id']}")
                            if chk:
                                selected_ids.append(r)
                        with col_det:
                            st.write(f"📌 **{r['employee_name']}** | {r['date']} | {r['ot_hours']} hrs | {r['task_type']} | Target: {r['expected_output']}")
                    
                    if selected_ids:
                        if st.button(f"Approve Selected ({len(selected_ids)}) ✅", type="primary"):
                            conn = get_connection()
                            try:
                                cursor = conn.cursor()
                                for req in selected_ids:
                                    # Self-Approval Guardrail
                                    if req['employee_name'] == user['name']:
                                        st.error(f"❌ Blocked: Self-approval prohibited for {req['employee_name']} (Record #{req['id']}).")
                                        continue

                                    v_hrs = req['ot_hours']
                                    amt = v_hrs * 120
                                    cursor.execute("""
                                        UPDATE ot_logs SET status = 'Approved', actual_output = %s, productivity = 1.0, verified_hours = %s, amount = %s, approved_by = %s, approved_at = %s
                                        WHERE id = %s
                                    """, (req['expected_output'], v_hrs, amt, user['name'], datetime.now().strftime("%Y-%m-%d %H:%M"), req['id']))
                                    
                                    cursor.execute("SELECT email FROM users WHERE name = %s", (req['employee_name'],))
                                    emp_mail = cursor.fetchone()
                                    if emp_mail:
                                        send_notification(emp_mail[0], f"🎉 OT Approved: Your {req['ot_hours']}h request on {req['date']} was approved by {user['name']}.")
                                    record_audit(user['email'], "BATCH_APPROVE", req['employee_name'], f"Approved OT record #{req['id']}")
                                conn.commit()
                            finally:
                                release_connection(conn)
                            st.success(f"Batch processed {len(selected_ids)} requests!")
                            st.rerun()

                st.markdown("### 📝 Individual Request Review")
                for idx, row in pending_df.iterrows():
                    with st.expander(f"👤 {row['employee_name']} | Date: {row['date']} | Hours: {row['ot_hours']}h ({row['task_type']})"):
                        col_a, col_b = st.columns(2)
                        with col_a:
                            st.write(f"**TL:** {row['tl_name']}")
                            st.write(f"**Shift:** {row['shift_start']} - {row['shift_end']}")
                            st.write(f"**OT Timing:** {row['ot_start']} - {row['ot_end']}")
                            st.write(f"**Target Output:** {row['expected_output']}")
                        with col_b:
                            # Self-Approval Check
                            if row['employee_name'] == user['name']:
                                st.warning("🔒 Self-Approval Guardrail: You cannot verify or approve your own overtime claim.")
                            else:
                                actual_out = st.number_input(
                                    f"Enter Actual Output for row {row['id']}", 
                                    min_value=1.0, 
                                    value=float(row['expected_output']), 
                                    key=f"out_{row['id']}",
                                    help="Must be greater than 0. Zero output cannot be claimed for overtime."
                                )
                                rej_reason = st.text_input("Rejection Reason (Mandatory if Rejecting):", key=f"rej_reason_{row['id']}")

                                col_btn1, col_btn2 = st.columns(2)
                                if col_btn1.button("Approve ✅", key=f"app_{row['id']}"):
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
                                        send_notification(emp_mail[0], f"🎉 OT Approved: Your {row['ot_hours']}h request on {row['date']} has been approved.")
                                    st.success("Approved successfully!")
                                    st.rerun()
                                    
                                if col_btn2.button("Reject ❌", key=f"rej_{row['id']}"):
                                    if not rej_reason.strip():
                                        st.error("❌ Mandatory Field: You must specify a Rejection Reason before rejecting.")
                                    else:
                                        expected = row['expected_output']
                                        prod = (actual_out / expected) if expected > 0 else 0
                                        conn = get_connection()
                                        try:
                                            cursor = conn.cursor()
                                            cursor.execute("""
                                                UPDATE ot_logs 
                                                SET status = 'Rejected', actual_output = %s, productivity = %s, verified_hours = 0, amount = 0, approved_by = %s, approved_at = %s, rejection_reason = %s
                                                WHERE id = %s
                                            """, (actual_out, prod, user['name'], datetime.now().strftime("%Y-%m-%d %H:%M"), rej_reason.strip(), row['id']))
                                            cursor.execute("SELECT email FROM users WHERE name = %s", (row['employee_name'],))
                                            emp_mail = cursor.fetchone()
                                            conn.commit()
                                            record_audit(user['email'], "REJECT_OT", row['employee_name'], f"Reason: {rej_reason.strip()}")
                                        finally:
                                            release_connection(conn)
                                        
                                        if emp_mail:
                                            send_notification(emp_mail[0], f"⚠️ OT Rejected: Your {row['ot_hours']}h request on {row['date']} was rejected. Reason: {rej_reason.strip()}")
                                        st.warning("Request rejected.")
                                        st.rerun()

            st.markdown("### 📋 All Request Logs")
            dashboard_display = df[['date', 'employee_name', 'tl_name', 'task_type', 'ot_hours', 'expected_output', 'actual_output', 'productivity', 'status', 'amount', 'rejection_reason']].copy()
            dashboard_display.rename(columns={
                'date': 'Date',
                'employee_name': 'Employee Name',
                'tl_name': 'Team Leader',
                'task_type': 'Task Type',
                'ot_hours': 'OT Hours',
                'expected_output': 'Target Output',
                'actual_output': 'Actual Output',
                'productivity': 'Productivity',
                'status': 'Status',
                'amount': 'Payout Amount',
                'rejection_reason': 'Rejection Reason'
            }, inplace=True)
            
            styled_all_df = (
                dashboard_display.style
                .map(highlight_status, subset=['Status'])
                .format({
                    'OT Hours': '{:.1f} hrs',
                    'Target Output': '{:.0f}',
                    'Actual Output': '{:.0f}',
                    'Productivity': '{:.0%}',
                    'Payout Amount': '₹{:.0f}'
                })
            )
            st.dataframe(styled_all_df, use_container_width=True, hide_index=True)

# ==================== 4. REPORTS ENGINE ====================
elif st.session_state.current_view == "reports":
    if user['role'] not in ["TL", "Admin"]:
        st.error("⛔ Access Denied. Reports are restricted to Team Leaders and Admins.")
    else:
        st.markdown("""
            <div class="fluent-card">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <h2 style="margin: 0 0 5px 0; color: #1E3A8A;">📈 Advanced Reports Engine</h2>
                        <p style="color: #605E5C; font-size: 14px; margin: 0;">Generate monthly summary reports and export official data.</p>
                    </div>
                    <div class="brand-logo">EXCIT<span>EL</span></div>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        r_type = st.selectbox("Select Report Type", options=["Monthly Summary Report", "Detailed OT Log Report"])
        
        col1, col2, col3 = st.columns([1.5, 1.5, 2])
        with col1:
            report_month = st.selectbox("Month", options=list(range(1, 13)), index=date.today().month - 1)
        with col2:
            report_year = st.selectbox("Year", options=[2025, 2026, 2027], index=1)
        with col3:
            report_status = st.segmented_control("Status Filter", options=["All", "Approved", "Pending", "Rejected"], default="All")
            
        conn = get_connection()
        try:
            df = pd.read_sql("SELECT * FROM ot_logs", conn)
        finally:
            release_connection(conn)
        
        if not df.empty:
            df['date_dt'] = pd.to_datetime(df['date'])
            filtered_df = df[(df['date_dt'].dt.month == report_month) & (df['date_dt'].dt.year == report_year)]
            
            if report_status != "All":
                filtered_df = filtered_df[filtered_df['status'] == report_status]
            
            if user['role'] == 'TL':
                filtered_df = filtered_df[filtered_df['tl_name'] == user['name']]
                
            if r_type == "Monthly Summary Report":
                summary_df = filtered_df.groupby(['employee_name', 'emp_id']).agg(
                    ot_days=('date', 'count'),
                    total_hours=('ot_hours', 'sum'),
                    approved_hours=('verified_hours', 'sum'),
                    total_amount=('amount', 'sum')
                ).reset_index()
                
                st.metric("Total Monthly Payout", f"₹{summary_df['total_amount'].sum():.0f}")
                
                summary_display = summary_df.copy()
                summary_display.rename(columns={
                    'employee_name': 'Employee Name',
                    'emp_id': 'Employee ID',
                    'ot_days': 'Total Days Worked',
                    'total_hours': 'Total Hours Requested',
                    'approved_hours': 'Approved Hours',
                    'total_amount': 'Total Payout'
                }, inplace=True)
                
                styled_summary = (
                    summary_display.style
                    .format({
                        'Total Hours Requested': '{:.1f} hrs',
                        'Approved Hours': '{:.1f} hrs',
                        'Total Payout': '₹{:.0f}'
                    })
                )
                st.dataframe(styled_summary, use_container_width=True, hide_index=True)
                
                csv = summary_display.to_csv(index=False).encode('utf-8')
                st.download_button("Download CSV 📥", csv, "monthly_summary.csv", "text/csv")
            else:
                detailed_display = filtered_df[['date', 'employee_name', 'emp_id', 'tl_name', 'task_type', 'ot_hours', 'expected_output', 'actual_output', 'productivity', 'status', 'amount', 'rejection_reason']].copy()
                detailed_display.rename(columns={
                    'date': 'Date',
                    'employee_name': 'Employee Name',
                    'emp_id': 'Employee ID',
                    'tl_name': 'Team Leader',
                    'task_type': 'Task Type',
                    'ot_hours': 'OT Hours',
                    'expected_output': 'Target Output',
                    'actual_output': 'Actual Output',
                    'productivity': 'Productivity',
                    'status': 'Status',
                    'amount': 'Payout Amount',
                    'rejection_reason': 'Rejection Reason'
                }, inplace=True)
                
                styled_report_df = (
                    detailed_display.style
                    .map(highlight_status, subset=['Status'])
                    .format({
                        'OT Hours': '{:.1f} hrs',
                        'Target Output': '{:.0f}',
                        'Actual Output': '{:.0f}',
                        'Productivity': '{:.0%}',
                        'Payout Amount': '₹{:.0f}'
                    })
                )
                st.dataframe(styled_report_df, use_container_width=True, hide_index=True)
                csv = detailed_display.to_csv(index=False).encode('utf-8')
                st.download_button("Download CSV 📥", csv, "detailed_ot_log.csv", "text/csv")
        else:
            st.info("No records found.")

# ==================== 5. ADMIN MANAGEMENT PANEL ====================
elif st.session_state.current_view == "admin":
    if user['role'] != "Admin":
        st.error("⛔ Access Denied. User Management is strictly restricted to Admins.")
    else:
        st.markdown("""
            <div class="fluent-card">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <h2 style="margin: 0 0 5px 0; color: #1E3A8A;">⚙️ Admin User, Credential & Bulk Onboarding</h2>
                        <p style="color: #605E5C; font-size: 14px; margin: 0;">Manage enterprise users, audit system actions, or upload bulk employee mappings.</p>
                    </div>
                    <div class="brand-logo">EXCIT<span>EL</span></div>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        tab_adm1, tab_adm2, tab_adm3 = st.tabs(["➕ Add User / Bulk Upload", "📋 Active Users Directory", "🔍 Security Audit Trail"])
        
        with tab_adm1:
            col_u1, col_u2 = st.columns(2)
            with col_u1:
                with st.form("add_user_form"):
                    st.markdown("### 👤 Create Single User")
                    u_name = st.text_input("Full Name")
                    u_email = st.text_input("Official Email ID (Login ID)")
                    u_pass = st.text_input("Password", type="password")
                    u_role = st.selectbox("Role Assignment", options=["Employee", "TL", "Admin"])
                    u_emp_id = st.text_input("Employee ID (e.g. EBND04XXX)")
                    u_tl_name = st.text_input("Assigned Team Leader Name")
                    u_tl_id = st.text_input("Assigned Team Leader ID")
                    
                    if st.form_submit_button("Save User ➕", type="primary"):
                        if u_name and u_email and u_pass and u_emp_id:
                            conn = get_connection()
                            try:
                                cursor = conn.cursor()
                                pass_hash = hash_password(u_pass)
                                cursor.execute("""
                                    INSERT INTO users (email, name, role, emp_id, tl_name, tl_id, password_hash) 
                                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                                """, (u_email.strip().lower(), u_name, u_role, u_emp_id, u_tl_name, u_tl_id, pass_hash))
                                conn.commit()
                                record_audit(user['email'], "CREATE_USER", u_email.strip().lower(), f"Created role {u_role}")
                                st.success(f"User {u_name} created successfully!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
                            finally:
                                release_connection(conn)
                        else:
                            st.error("Please fill in Name, Email, Password, and Employee ID.")

            with col_u2:
                st.markdown("### 📁 Bulk Onboard via Excel / CSV")
                st.markdown("""
                    Upload an Excel (`.xlsx`) or CSV file containing user records. 
                    \n**Required Headers:** `email`, `name`, `role`, `emp_id`, `tl_name`, `tl_id`, `password`
                """)
                uploaded_file = st.file_uploader("Upload Employee Data File", type=["xlsx", "csv"])
                if uploaded_file is not None:
                    try:
                        bulk_df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
                        st.dataframe(bulk_df.head(3), use_container_width=True)
                        if st.button("Process Bulk Import 🚀", type="primary"):
                            conn = get_connection()
                            try:
                                cursor = conn.cursor()
                                success_count = 0
                                for _, row in bulk_df.iterrows():
                                    try:
                                        email = str(row['email']).strip().lower()
                                        name = str(row['name']).strip()
                                        role = str(row['role']).strip()
                                        emp_id = str(row['emp_id']).strip()
                                        tl_name = str(row.get('tl_name', 'Unassigned')).strip()
                                        tl_id = str(row.get('tl_id', '')).strip()
                                        raw_pass = str(row.get('password', 'Password123'))
                                        if raw_pass == 'nan' or not raw_pass:
                                            raw_pass = 'Password123'
                                        p_hash = hash_password(raw_pass)
                                        cursor.execute("""
                                            INSERT INTO users (email, name, role, emp_id, tl_name, tl_id, password_hash) 
                                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                                            ON CONFLICT (email) DO UPDATE SET 
                                                name = EXCLUDED.name, role = EXCLUDED.role, emp_id = EXCLUDED.emp_id, 
                                                tl_name = EXCLUDED.tl_name, tl_id = EXCLUDED.tl_id,
                                                password_hash = EXCLUDED.password_hash
                                        """, (email, name, role, emp_id, tl_name, tl_id, p_hash))
                                        success_count += 1
                                    except Exception:
                                        continue
                                conn.commit()
                                record_audit(user['email'], "BULK_IMPORT", f"{success_count}_USERS", "Bulk file onboarding")
                                st.success(f"Successfully imported {success_count} records!")
                                st.rerun()
                            finally:
                                release_connection(conn)
                    except Exception as file_err:
                        st.error(f"Error reading file: {file_err}")

        with tab_adm2:
            st.markdown("### 📋 Active System Users Directory")
            conn = get_connection()
            try:
                users_df = pd.read_sql("SELECT email, name, role, emp_id, tl_name, tl_id FROM users", conn)
            finally:
                release_connection(conn)
            
            if users_df.empty:
                st.info("No users found.")
            else:
                # Direct Directory CSV Export
                csv_export = users_df.to_csv(index=False).encode('utf-8')
                st.download_button("Export Directory as CSV 📥", csv_export, "system_users_directory.csv", "text/csv")
                st.markdown("<br>", unsafe_allow_html=True)
                
                st.markdown("<div class='table-header'>", unsafe_allow_html=True)
                header_cols = st.columns([2, 2.5, 1, 1.5, 1.5, 1, 1.2])
                header_cols[0].markdown("**Name**")
                header_cols[1].markdown("**Email**")
                header_cols[2].markdown("**Role**")
                header_cols[3].markdown("**Emp ID**")
                header_cols[4].markdown("**TL Name**")
                header_cols[5].markdown("**TL ID**")
                header_cols[6].markdown("**Actions**")
                st.markdown("</div>", unsafe_allow_html=True)
                
                for idx, row in users_df.iterrows():
                    row_cols = st.columns([2, 2.5, 1, 1.5, 1.5, 1, 1.2])
                    row_cols[0].write(row['name'])
                    row_cols[1].write(row['email'])
                    row_cols[2].write(row['role'])
                    row_cols[3].write(row['emp_id'])
                    row_cols[4].write(row['tl_name'])
                    row_cols[5].write(row['tl_id'])
                    
                    act_col1, act_col2 = row_cols[6].columns(2)
                    if act_col1.button("✏️", key=f"edit_btn_{row['email']}", help="Edit User Details"):
                        edit_user_dialog(row.to_dict())
                    if act_col2.button("🗑️", key=f"del_btn_{row['email']}", help="Delete User"):
                        delete_user_dialog(row['email'], user['email'])
                    st.markdown("<hr style='margin: 0px; padding: 0px; border-top: 1px solid #F0F0F0;'>", unsafe_allow_html=True)

        with tab_adm3:
            st.markdown("### 🔍 Security Audit Trail")
            conn = get_connection()
            try:
                audit_df = pd.read_sql("SELECT timestamp, performer, action, target, details FROM audit_logs ORDER BY id DESC LIMIT 50", conn)
            finally:
                release_connection(conn)
            
            if audit_df.empty:
                st.info("No audit entries logged yet.")
            else:
                audit_df.rename(columns={
                    'timestamp': 'Timestamp',
                    'performer': 'Actor Email',
                    'action': 'Security Action',
                    'target': 'Target Entity',
                    'details': 'Audit Details'
                }, inplace=True)
                st.dataframe(audit_df, use_container_width=True, hide_index=True)

# ==================== 6. GUIDELINES & SECURITY POLICY PAGE ====================
elif st.session_state.current_view == "guidelines":
    st.markdown("""
        <div class="fluent-card">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <h2 style="margin: 0 0 5px 0; color: #1E3A8A;">📖 Portal Guidelines & Data Security Policy</h2>
                    <p style="color: #605E5C; font-size: 14px; margin: 0;">Official operating guidelines, overtime policy thresholds, and enterprise security standards.</p>
                </div>
                <div class="brand-logo">EXCIT<span>EL</span></div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    st.markdown("""
        <div class="policy-card">
            <h3 style="color: #1E3A8A; margin-top: 0;">1. How to Apply & Workflow Guidelines</h3>
            <ul>
                <li><b>Employees:</b> Log in using your assigned official email credentials. Navigate to the <b>Form</b> tab, verify your shift timings, select your task category, and submit your overtime duration. Review past statuses in the <b>History</b> tab.</li>
                <li><b>Team Leaders (TL):</b> Monitor pending overtime submissions under the <b>Dashboard</b> tab. Verify actual units produced against the standard expected output target, and issue approvals or rejections accordingly. TLs may submit proxy requests for team members via the Form tab.</li>
                <li><b>Overtime Calculation:</b> Standard verified payouts are computed based on operational output targets and verified hours. Weekend and weekday rates follow the standardized enterprise rate card.</li>
            </ul>
        </div>

        <div class="policy-card">
            <h3 style="color: #1E3A8A; margin-top: 0;">2. Operational Limits & Threshold Rules</h3>
            <ul>
                <li><b>Daily Cap:</b> An employee cannot exceed <b>3.0 hours</b> of overtime in a single calendar day.</li>
                <li><b>Weekly Cap:</b> Total aggregated overtime cannot exceed <b>12.0 hours</b> in a rolling calendar week (Monday through Sunday).</li>
                <li><b>Submission Window:</b> Claims must be entered within <b>48 hours</b> of shift completion. Older dates are locked out.</li>
                <li><b>Shift Overlap Prohibition:</b> Overtime hours must not intersect with regular scheduled shift timings under any circumstances. Overlapping submissions will be automatically blocked by system validation.</li>
                <li><b>Zero Deliverables Prohibited:</b> Overtime claims require measurable output. An actual output entry of 0 is not permitted on paid overtime requests.</li>
            </ul>
        </div>

        <div class="policy-card" style="border-left: 5px solid #991B1B;">
            <h3 style="color: #991B1B; margin-top: 0;">3. Data Security & Anti-Falsification Policy</h3>
            <ul>
                <li><b>Strict Prohibition of False Records:</b> Logging fabricated overtime hours, inflating output units, or misrepresenting timings is strictly prohibited and constitutes a direct breach of employment conduct.</li>
                <li><b>Audit Trail:</b> All actions—including form submission times, approval timestamps, and administrative edits—are recorded with user identification in the system audit database.</li>
                <li><b>Self-Approval Prohibition:</b> Supervisors and managers cannot approve their own overtime claims.</li>
                <li><b>Disciplinary Enforcement:</b> Any user caught manipulating credentials, submitting fraudulent overtime, or circumventing system role permissions will be subject to immediate disciplinary review and loss of portal access.</li>
                <li><b>Credential Confidentiality:</b> Users are strictly accountable for maintaining the confidentiality of their portal passwords. Never share passwords or allow third parties to operate under your login session.</li>
            </ul>
        </div>
    """, unsafe_allow_html=True)

    if st.button("⬅️ Return to Main Portal", use_container_width=True):
        st.session_state.current_view = "portal"
        st.rerun()

# ==================== PERSISTENT FOOTER LINK ====================
st.markdown("<br><br>", unsafe_allow_html=True)
footer_col1, footer_col2, footer_col3 = st.columns([1, 2.5, 1])
with footer_col2:
    if st.button("📖 Read Portal Guidelines, Usage Rules & Data Security Policy", use_container_width=True):
        st.session_state.current_view = "guidelines"
        st.rerun()
st.markdown("<div class='footer-note'>© Excitel Overtime Portal — Official Enterprise Compliance & Data Protection</div>", unsafe_allow_html=True)
