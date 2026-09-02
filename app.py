import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime, date
from fpdf import FPDF
import altair as alt
import os
import hashlib

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

# ==================== DATABASE SETUP ====================
def get_connection():
    db_url = st.secrets["database"]["url"]
    try:
        return psycopg2.connect(db_url)
    except Exception as e:
        st.error(f"🚨 Detailed DB Error: {e}")
        raise e

def hash_password(password):
    """Securely hash passwords using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Users table with secure password hash column
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
            approved_at TEXT
        )
    ''')
    
    # Default users with secure default password: "Password123"
    default_pass_hash = hash_password("Password123")
    default_users = [
        ("porwal.satyam1@gmail.com", "Satyam Porwal", "Admin", "EBND04737", "Nandini Puri", "TL01", default_pass_hash),
        ("ritu.mandal@dl.excitel.in", "Ritu Mandal", "Admin", "EBND04635", "Nandini Puri", "TL01", default_pass_hash),
        ("jamal.khan@dl.excitel.in", "Jamal Khan", "TL", "EBND04471", "Nandini Puri", "TL01", default_pass_hash),
        ("abhishek.pandey@dl.excitel.in", "Abhishek Pandey", "TL", "EBND04472", "Nandini Puri", "TL01", default_pass_hash),
        ("basu.porwal@dl.excitel.in", "Basu Porwal", "Employee", "EBND04475", "Satyam Porwal", "TL02", default_pass_hash)
    ]
    cursor.executemany("""
        INSERT INTO users (email, name, role, emp_id, tl_name, tl_id, password_hash) 
        VALUES (%s, %s, %s, %s, %s, %s, %s) 
        ON CONFLICT (email) DO UPDATE SET 
            name = EXCLUDED.name, role = EXCLUDED.role, emp_id = EXCLUDED.emp_id, 
            tl_name = EXCLUDED.tl_name, tl_id = EXCLUDED.tl_id
    """, default_users)
        
    conn.commit()
    conn.close()

init_db()

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
        h1, h2, h3 { color: #1E3A8A; font-weight: 600; }
        [data-testid="stSidebar"] {
            background-color: #FFFFFF;
            border-right: 1px solid #E1DFDD;
        }
    </style>
""", unsafe_allow_html=True)

# ==================== SESSION STATE AUTHENTICATION ====================
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
                    cursor = conn.cursor()
                    cursor.execute("SELECT name, role, password_hash FROM users WHERE email = %s", (login_email.strip().lower(),))
                    res = cursor.fetchone()
                    conn.close()
                    
                    if res:
                        db_name, db_role, db_pass_hash = res
                        if db_pass_hash == hash_password(login_password):
                            st.session_state.authenticated = True
                            st.session_state.user_email = login_email.strip().lower()
                            st.session_state.user_name = db_name
                            st.session_state.user_role = db_role
                            st.session_state.current_view = "portal"
                            st.success("Login successful! Loading portal...")
                            st.rerun()
                        else:
                            st.error("❌ Incorrect password. Please try again.")
                    else:
                        st.error("❌ Email not found in authorized system registry.")
    st.stop() # Halts rendering of the rest of the app until authenticated

# ==================== FETCH LOGGED-IN USER DETAILS ====================
def get_logged_in_user():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT email, name, role, emp_id, tl_name, tl_id FROM users WHERE email = %s", (st.session_state.user_email,))
    res = cursor.fetchone()
    conn.close()
    if res:
        return {"email": res[0], "name": res[1], "role": res[2], "empId": res[3], "tlName": res[4], "tlId": res[5]}
    return {"email": st.session_state.user_email, "name": st.session_state.user_name, "role": st.session_state.user_role, "empId": "N/A", "tlName": "Unassigned", "tlId": ""}

user = get_logged_in_user()

# ==================== SIDEBAR ====================
st.sidebar.markdown("<div class='brand-logo' style='margin-bottom:15px;'>EXCIT<span>EL</span></div>", unsafe_allow_html=True)
st.sidebar.markdown(f"**Signed In As:**  \n`{user['name']}`")
st.sidebar.markdown(f"**Role:** `{user['role']}`")

st.sidebar.markdown("---")
if st.sidebar.button("🚪 Sign Out", use_container_width=True):
    st.session_state.authenticated = False
    st.session_state.user_email = ""
    st.session_state.user_role = ""
    st.session_state.user_name = ""
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.info("🔒 **Secure Session Active:** All actions are logged and authenticated.")

# ==================== STRICT ROLE-BASED NAVIGATION ====================
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
                    <p style="color: #605E5C; font-size: 14px; margin: 0;">Submit and manage overtime requests securely.</p>
                </div>
                <div class="brand-logo">EXCIT<span>EL</span></div>
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    target_name = user['name']
    target_emp_id = user['empId']
    target_tl = user['tlName']
    
    # TL and Admin can submit proxy requests for employees
    if user['role'] in ["TL", "Admin"]:
        st.markdown("### 🛡️ Submit on Behalf of Employee (Proxy)")
        conn = get_connection()
        emp_df = pd.read_sql("SELECT name FROM users WHERE role = 'Employee'", conn)
        conn.close()
        selected_proxy = st.selectbox("Select Employee:", options=["Select Employee..."] + emp_df['name'].tolist())
        if selected_proxy != "Select Employee...":
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT name, emp_id, tl_name FROM users WHERE name = %s", (selected_proxy,))
            p_res = cursor.fetchone()
            conn.close()
            if p_res:
                target_name, target_emp_id, target_tl = p_res
    
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
        
        if max(s_start_min, o_start_min) < min(s_end_min, o_end_min):
            st.error("❌ Overtime hours cannot overlap regular shift timings.")
        else:
            ot_hours = (o_end_min - o_start_min) / 60.0
            if ot_hours <= 0:
                st.error("❌ OT End time must be after Start time.")
            else:
                std_rate = RATES.get(task_type, 12)
                expected_out = ot_hours * std_rate
                
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO ot_logs (date, employee_name, emp_id, shift_start, shift_end, ot_start, ot_end, ot_hours, task_type, status, tl_name, actual_output, standard_rate, expected_output, productivity, verified_hours, amount, approved_by, approved_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s, %s, 0, 0, 0, '', '')
                """, (req_date.strftime("%Y-%m-%d"), target_name, target_emp_id, shift_start.strftime("%H:%M"), shift_end.strftime("%H:%M"), ot_start.strftime("%H:%M"), ot_end.strftime("%H:%M"), ot_hours, task_type, "Pending", target_tl, std_rate, expected_out))
                conn.commit()
                conn.close()
                st.success(f"✅ OT successfully requested for {target_name} ({ot_hours} hrs)!")

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
                        <p style="color: #605E5C; font-size: 14px; margin: 0;">Review your submitted overtime records and payout summaries.</p>
                    </div>
                    <div class="brand-logo">EXCIT<span>EL</span></div>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        conn = get_connection()
        df = pd.read_sql("SELECT * FROM ot_logs WHERE employee_name = %s", conn, params=(user['name'],))
        conn.close()
        
        if df.empty:
            st.info("No OT records found.")
        else:
            fc1, fc2, fc3 = st.columns(3)
            with fc1:
                start_date_filter = st.date_input("Start Date", value=date(date.today().year, date.today().month, 1))
            with fc2:
                end_date_filter = st.date_input("End Date", value=date.today())
            with fc3:
                status_filter = st.selectbox("Status Filter", options=["All", "Pending", "Approved", "Rejected"])
                
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
            
            styled_history = filtered_history[['date', 'ot_hours', 'task_type', 'productivity', 'status', 'amount']].style.applymap(highlight_status, subset=['status'])
            st.dataframe(styled_history, use_container_width=True)
            
            if not filtered_history.empty:
                pdf_data = generate_pdf_report(filtered_history, f"OT History - {user['name']}")
                st.download_button("Download PDF Statement 📄", data=pdf_data, file_name="my_ot_history.pdf", mime="application/pdf")

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
                        <p style="color: #605E5C; font-size: 14px; margin: 0;">Approve team overtime requests and track operational costs.</p>
                    </div>
                    <div class="brand-logo">EXCIT<span>EL</span></div>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        conn = get_connection()
        query = "SELECT * FROM ot_logs"
        if user['role'] == 'TL':
            query += f" WHERE tl_name = '{user['name']}'"
        df = pd.read_sql(query, conn)
        conn.close()
        
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
            
            st.markdown("### 📈 Visual Analytics & Cost Trends")
            ch1, ch2, ch3 = st.columns(3)
            
            with ch1:
                st.markdown("#### Status Breakdown")
                status_counts = df['status'].value_counts().reset_index()
                status_counts.columns = ['Status', 'Count']
                chart_status = alt.Chart(status_counts).mark_arc(innerRadius=40).encode(
                    theta=alt.Theta(field="Count", type="quantitative"),
                    color=alt.Color(field="Status", type="nominal", scale=alt.Scale(domain=['Pending', 'Approved', 'Rejected'], range=['#F59E0B', '#10B981', '#EF4444']))
                ).properties(height=200)
                st.altair_chart(chart_status, use_container_width=True)
                
            with ch2:
                st.markdown("#### Task-wise OT Hours")
                task_counts = df.groupby('task_type')['ot_hours'].sum().reset_index()
                chart_task = alt.Chart(task_counts).mark_bar(color='#1E3A8A', cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
                    x=alt.X('task_type', sort='-y', title='Task Type'),
                    y=alt.Y('ot_hours', title='Total Hours')
                ).properties(height=200)
                st.altair_chart(chart_task, use_container_width=True)

            with ch3:
                st.markdown("#### Daily Cost Trend")
                trend_df = df[df['status'] == 'Approved'].groupby('date')['amount'].sum().reset_index()
                if not trend_df.empty:
                    chart_trend = alt.Chart(trend_df).mark_line(point=True, color='#FF6B00').encode(
                        x=alt.X('date:T', title='Date'),
                        y=alt.Y('amount:Q', title='Approved Payout (₹)')
                    ).properties(height=200)
                    st.altair_chart(chart_trend, use_container_width=True)
                else:
                    st.info("No approved cost trends yet.")

            st.markdown("### 📝 Pending Requests Review")
            pending_df = df[df['status'] == 'Pending']
            if pending_df.empty:
                st.success("🎉 All caught up! No pending requests.")
            else:
                for idx, row in pending_df.iterrows():
                    with st.expander(f"📌 {row['employee_name']} | Date: {row['date']} | Hours: {row['ot_hours']}h ({row['task_type']})"):
                        col_a, col_b = st.columns(2)
                        with col_a:
                            st.write(f"**TL:** {row['tl_name']}")
                            st.write(f"**Shift:** {row['shift_start']} - {row['shift_end']}")
                            st.write(f"**OT Timing:** {row['ot_start']} - {row['ot_end']}")
                            st.write(f"**Expected Output (Target):** {row['expected_output']}")
                        with col_b:
                            actual_out = st.number_input(f"Enter Actual Output for row {row['id']}", min_value=0.0, value=0.0, key=f"out_{row['id']}")
                            
                            col_btn1, col_btn2 = st.columns(2)
                            if col_btn1.button("Approve ✅", key=f"app_{row['id']}"):
                                expected = row['expected_output']
                                prod = (actual_out / expected) if expected > 0 else 0
                                v_hrs = row['ot_hours'] if prod >= 0.7 else (row['ot_hours'] * 0.5 if prod >= 0.5 else 0)
                                amt = v_hrs * 120
                                
                                conn = get_connection()
                                cursor = conn.cursor()
                                cursor.execute("""
                                    UPDATE ot_logs SET status = 'Approved', actual_output = %s, productivity = %s, verified_hours = %s, amount = %s, approved_by = %s, approved_at = %s
                                    WHERE id = %s
                                """, (actual_out, prod, v_hrs, amt, user['name'], datetime.now().strftime("%Y-%m-%d %H:%M"), row['id']))
                                conn.commit()
                                conn.close()
                                st.success("Approved successfully!")
                                st.rerun()
                                
                            if col_btn2.button("Reject ❌", key=f"rej_{row['id']}"):
                                conn = get_connection()
                                cursor = conn.cursor()
                                cursor.execute("UPDATE ot_logs SET status = 'Rejected', approved_by = %s, approved_at = %s WHERE id = %s", (user['name'], datetime.now().strftime("%Y-%m-%d %H:%M"), row['id']))
                                conn.commit()
                                conn.close()
                                st.warning("Request rejected.")
                                st.rerun()

            st.markdown("### 📋 All Requests Log")
            styled_all_df = df[['date', 'employee_name', 'tl_name', 'task_type', 'ot_hours', 'actual_output', 'status', 'amount']].style.applymap(highlight_status, subset=['status'])
            st.dataframe(styled_all_df, use_container_width=True)

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
        
        col1, col2, col3 = st.columns(3)
        with col1:
            report_month = st.selectbox("Month", options=list(range(1, 13)), index=date.today().month - 1)
        with col2:
            report_year = st.selectbox("Year", options=[2025, 2026, 2027], index=1)
        with col3:
            report_status = st.selectbox("Status Filter", options=["All", "Approved", "Pending", "Rejected"], key="rep_status")
            
        conn = get_connection()
        df = pd.read_sql("SELECT * FROM ot_logs", conn)
        conn.close()
        
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
                st.dataframe(summary_df, use_container_width=True)
                
                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    csv = summary_df.to_csv(index=False).encode('utf-8')
                    st.download_button("Download CSV 📥", csv, "monthly_summary.csv", "text/csv")
                with col_d2:
                    pdf_data = generate_pdf_report(filtered_df, f"Monthly Summary Report - {report_month}/{report_year}")
                    st.download_button("Download PDF 📄", data=pdf_data, file_name="monthly_summary.pdf", mime="application/pdf")
            else:
                styled_report_df = filtered_df[['date', 'employee_name', 'emp_id', 'tl_name', 'task_type', 'ot_hours', 'status', 'amount']].style.applymap(highlight_status, subset=['status'])
                st.dataframe(styled_report_df, use_container_width=True)
                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    csv = filtered_df.to_csv(index=False).encode('utf-8')
                    st.download_button("Download CSV 📥", csv, "detailed_ot_log.csv", "text/csv")
                with col_d2:
                    pdf_data = generate_pdf_report(filtered_df, f"Detailed OT Log Report - {report_month}/{report_year}")
                    st.download_button("Download PDF 📄", data=pdf_data, file_name="detailed_ot_log.pdf", mime="application/pdf")
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
                        <h2 style="margin: 0 0 5px 0; color: #1E3A8A;">⚙️ Admin User & Credential Management</h2>
                        <p style="color: #605E5C; font-size: 14px; margin: 0;">Create user credentials, assign roles, and map team relationships.</p>
                    </div>
                    <div class="brand-logo">EXCIT<span>EL</span></div>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        with st.form("add_user_form"):
            st.markdown("### Create / Update User & Password")
            u_name = st.text_input("Full Name")
            u_email = st.text_input("Official Email ID (Login ID)")
            u_pass = st.text_input("Set / Reset Password", type="password")
            u_role = st.selectbox("Role Assignment", options=["Employee", "TL", "Admin"])
            u_emp_id = st.text_input("Employee ID (e.g. EBND04XXX)")
            u_tl_name = st.text_input("Assigned Team Leader Name")
            u_tl_id = st.text_input("Assigned Team Leader ID")
            
            if st.form_submit_button("Save User Credential ➕", type="primary"):
                if u_name and u_email and u_pass and u_emp_id:
                    conn = get_connection()
                    cursor = conn.cursor()
                    pass_hash = hash_password(u_pass)
                    try:
                        cursor.execute("""
                            INSERT INTO users (email, name, role, emp_id, tl_name, tl_id, password_hash) 
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (email) DO UPDATE SET 
                                name = EXCLUDED.name, 
                                role = EXCLUDED.role, 
                                emp_id = EXCLUDED.emp_id, 
                                tl_name = EXCLUDED.tl_name, 
                                tl_id = EXCLUDED.tl_id,
                                password_hash = EXCLUDED.password_hash
                        """, (u_email.strip().lower(), u_name, u_role, u_emp_id, u_tl_name, u_tl_id, pass_hash))
                        conn.commit()
                        st.success(f"User {u_name} credentials saved successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
                    finally:
                        conn.close()
                else:
                    st.error("Please fill in Name, Email, Password, and Employee ID.")
                    
        st.markdown("### 📋 Active System Users Directory")
        conn = get_connection()
        users_df = pd.read_sql("SELECT email, name, role, emp_id, tl_name FROM users", conn)
        conn.close()
        st.dataframe(users_df, use_container_width=True)
