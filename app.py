import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date
from fpdf import FPDF
import altair as alt

# ==================== DATABASE SETUP ====================
DB_NAME = "excitel_ot.db"

def get_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            role TEXT,
            name TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS employees (
            name TEXT PRIMARY KEY,
            emp_id TEXT,
            tl_name TEXT,
            tl_id TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ot_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    
    # Seed default users if empty
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        default_users = [
            ("porwal.satyam1@gmail.com", "Admin", "Satyam Porwal"),
            ("ritu.mandal@dl.excitel.in", "Admin", "Ritu Mandal"),
            ("jamal.khan@dl.excitel.in", "TL", "Jamal Khan"),
            ("abhishek.pandey@dl.excitel.in", "TL", "Abhishek Pandey"),
            ("basu.porwal@dl.excitel.in", "Employee", "Basu Porwal")
        ]
        cursor.executemany("INSERT OR IGNORE INTO users VALUES (?, ?, ?)", default_users)
        
    # Seed default employees if empty
    cursor.execute("SELECT COUNT(*) FROM employees")
    if cursor.fetchone()[0] == 0:
        default_emps = [
            ("Satyam Porwal", "EBND04737", "Nandini Puri", "TL01"),
            ("Ritu Mandal", "EBND04635", "Nandini Puri", "TL01"),
            ("Jamal Khan", "EBND04471", "Nandini Puri", "TL01"),
            ("Abhishek Pandey", "EBND04472", "Nandini Puri", "TL01"),
            ("Basu Porwal", "EBND04475", "Satyam Porwal", "TL02")
        ]
        cursor.executemany("INSERT OR IGNORE INTO employees VALUES (?, ?, ?, ?)", default_emps)

    # Seed sample OT logs so dashboards are never blank
    cursor.execute("SELECT COUNT(*) FROM ot_logs")
    if cursor.fetchone()[0] == 0:
        default_logs = [
            ("2026-08-24", "Basu Porwal", "EBND04475", "09:00", "18:00", "18:00", "21:00", 3.0, "Calls", "Pending", "Satyam Porwal", 0.0, 12.0, 36.0, 0.0, 0.0, 0.0, "", ""),
            ("2026-08-25", "Ritu Mandal", "EBND04635", "09:00", "18:00", "18:00", "21:00", 3.0, "Backend", "Approved", "Nandini Puri", 35.0, 10.0, 30.0, 1.16, 3.0, 360.0, "Satyam Porwal", "2026-08-25 20:00"),
            ("2026-08-25", "Jamal Khan", "EBND04471", "09:00", "18:00", "18:00", "22:00", 4.0, "Tickets", "Pending", "Nandini Puri", 0.0, 12.0, 48.0, 0.0, 0.0, 0.0, "", "")
        ]
        cursor.executemany("""
            INSERT INTO ot_logs (date, employee_name, emp_id, shift_start, shift_end, ot_start, ot_end, ot_hours, task_type, status, tl_name, actual_output, standard_rate, expected_output, productivity, verified_hours, amount, approved_by, approved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, default_logs)
        
    conn.commit()
    conn.close()

init_db()

# ==================== PDF GENERATOR ====================
class OTReportPDF(FPDF):
    def header(self):
        self.set_font('helvetica', 'B', 15)
        self.set_text_color(30, 58, 138)
        self.cell(0, 10, 'EXCITEL - Overtime Report', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('helvetica', 'I', 8)
        self.set_text_color(100, 100, 100)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

def generate_pdf_report(df_to_print, title):
    pdf = OTReportPDF()
    pdf.add_page()
    pdf.set_font('helvetica', 'B', 12)
    pdf.set_text_color(50, 50, 50)
    pdf.cell(0, 10, title, 0, 1, 'L')
    pdf.ln(5)
    
    pdf.set_font('helvetica', 'B', 9)
    pdf.set_fill_color(30, 58, 138)
    pdf.set_text_color(255, 255, 255)
    
    columns = ['Date', 'Employee', 'Task', 'Hours', 'Status', 'Amount']
    col_widths = [25, 45, 30, 20, 25, 30]
    
    for i, col in enumerate(columns):
        pdf.cell(col_widths[i], 8, col, 1, 0, 'C', True)
    pdf.ln()
    
    pdf.set_font('helvetica', '', 9)
    pdf.set_text_color(50, 50, 50)
    for _, row in df_to_print.iterrows():
        pdf.cell(col_widths[0], 7, str(row.get('date', '')), 1, 0, 'C')
        pdf.cell(col_widths[1], 7, str(row.get('employee_name', ''))[:20], 1, 0, 'L')
        pdf.cell(col_widths[2], 7, str(row.get('task_type', '')), 1, 0, 'C')
        pdf.cell(col_widths[3], 7, str(row.get('ot_hours', '')), 1, 0, 'C')
        pdf.cell(col_widths[4], 7, str(row.get('status', '')), 1, 0, 'C')
        pdf.cell(col_widths[5], 7, f"Rs.{row.get('amount', 0)}", 1, 0, 'C')
        pdf.ln()
        
    return bytes(pdf.output())

# ==================== PAGE CONFIG & BRANDED CSS ====================
st.set_page_config(page_title="Excitel OT Portal", page_icon="⚡", layout="wide")

st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700;800&display=swap');
        
        html, body, [class*="css"] {
            font-family: 'Poppins', sans-serif;
            background-color: #F4F7FC;
            color: #334155;
        }
        
        .brand-logo {
            font-size: 24px;
            font-weight: 800;
            letter-spacing: 1px;
            color: #1E3A8A;
            text-transform: uppercase;
        }
        .brand-logo span {
            color: #FF6B00;
        }
        
        .stButton>button {
            background: linear-gradient(135deg, #FF6B00, #FF8B33);
            color: white;
            border-radius: 12px;
            font-weight: 700;
            border: none;
            box-shadow: 0 4px 15px rgba(255,107,0,0.3);
            width: 100%;
        }
        .stButton>button:hover {
            opacity: 0.95;
            box-shadow: 0 6px 20px rgba(255,107,0,0.4);
        }
        
        h1, h2, h3 { color: #1E3A8A; font-weight: 700; }
    </style>
""", unsafe_allow_html=True)

# ==================== SESSION & AUTH STATE ====================
if 'user_email' not in st.session_state:
    st.session_state.user_email = "porwal.satyam1@gmail.com"
if 'current_view' not in st.session_state:
    st.session_state.current_view = "portal"

def get_current_user_info():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT role, name FROM users WHERE email = ?", (st.session_state.user_email,))
    res = cursor.fetchone()
    conn.close()
    if res:
        role, name = res
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT emp_id, tl_name, tl_id FROM employees WHERE name = ?", (name,))
        emp_res = cursor.fetchone()
        conn.close()
        emp_id = emp_res[0] if emp_res else "N/A"
        tl_name = emp_res[1] if emp_res else "Unassigned"
        tl_id = emp_res[2] if emp_res else ""
        return {"email": st.session_state.user_email, "role": role, "name": name, "empId": emp_id, "tlName": tl_name, "tlId": tl_id}
    return {"role": "None", "name": "Guest"}

user = get_current_user_info()

# ==================== SIDEBAR USER SWITCHER ====================
st.sidebar.markdown("<div class='brand-logo' style='font-size:20px; margin-bottom:10px;'>EXCIT<span>EL</span></div>", unsafe_allow_html=True)
st.sidebar.markdown(f"**User:** {user['name']}  \n**Role:** `{user['role']}`")

conn = get_connection()
all_users = pd.read_sql("SELECT email, name, role FROM users", conn)
conn.close()

default_idx = int(all_users[all_users['email'] == st.session_state.user_email].index[0]) if st.session_state.user_email in all_users['email'].values else 0
selected_login = st.sidebar.selectbox(
    "Switch Test User / Role", 
    options=all_users['email'].tolist(), 
    format_func=lambda x: f"{all_users[all_users['email'] == x]['name'].values[0]} ({all_users[all_users['email'] == x]['role'].values[0]})",
    index=default_idx
)
if selected_login != st.session_state.user_email:
    st.session_state.user_email = selected_login
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.info("💡 Switch users here to test Employee, TL, and Admin permissions instantly!")

# ==================== TOP NAVIGATION BAR ====================
col_nav1, col_nav2, col_nav3, col_nav4, col_nav5, col_nav6 = st.columns([2.2, 1, 1, 1, 1, 1])

with col_nav1:
    st.markdown(f"<div style='padding-top: 8px;'><span style='color: #1E3A8A; font-weight: 700; font-size: 14px;'>🛡️ {user['name']} ({user['role']})</span></div>", unsafe_allow_html=True)

with col_nav2:
    if st.button("📝 OT Form", use_container_width=True):
        st.session_state.current_view = "portal"
        st.rerun()

with col_nav3:
    if st.button("📋 History", use_container_width=True):
        st.session_state.current_view = "history"
        st.rerun()

if user['role'] in ["TL", "Admin"]:
    with col_nav4:
        if st.button("📊 Dashboard", use_container_width=True):
            st.session_state.current_view = "dashboard"
            st.rerun()
    with col_nav5:
        if st.button("📈 Reports", use_container_width=True):
            st.session_state.current_view = "reports"
            st.rerun()

if user['role'] == "Admin":
    with col_nav6:
        if st.button("⚙️ Admin", use_container_width=True):
            st.session_state.current_view = "admin"
            st.rerun()

st.markdown("---")

RATES = {'Calls': 12, 'Backend': 10, 'Tickets': 12, 'Complaints': 8, 'Email': 15}

def time_to_minutes(t_str):
    h, m = map(int, t_str.split(':'))
    return h * 60 + m

# ==================== 1. OT FORM PORTAL ====================
if st.session_state.current_view == "portal":
    st.markdown("""
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <h2 style="margin: 0; color: #1E3A8A;">⚡ Overtime Entry Portal</h2>
            <div class="brand-logo">EXCIT<span>EL</span></div>
        </div>
    """, unsafe_allow_html=True)
    
    target_name = user['name']
    target_emp_id = user['empId']
    target_tl = user['tlName']
    
    if user['role'] in ["TL", "Admin"]:
        st.markdown("### 🛡️ Submit on Behalf of Employee (Proxy)")
        conn = get_connection()
        emp_df = pd.read_sql("SELECT name FROM employees", conn)
        conn.close()
        selected_proxy = st.selectbox("Select Employee:", options=["Select Employee..."] + emp_df['name'].tolist())
        if selected_proxy != "Select Employee...":
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT name, emp_id, tl_name FROM employees WHERE name = ?", (selected_proxy,))
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
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, 0, 0, 0, '', '')
                """, (req_date.strftime("%Y-%m-%d"), target_name, target_emp_id, shift_start.strftime("%H:%M"), shift_end.strftime("%H:%M"), ot_start.strftime("%H:%M"), ot_end.strftime("%H:%M"), ot_hours, task_type, "Pending", target_tl, std_rate, expected_out))
                conn.commit()
                conn.close()
                st.success(f"✅ OT successfully requested for {target_name} ({ot_hours} hrs)!")

# ==================== 2. MY HISTORY ====================
elif st.session_state.current_view == "history":
    st.markdown("""
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <h2 style="margin: 0; color: #1E3A8A;">📋 My Overtime History</h2>
            <div class="brand-logo">EXCIT<span>EL</span></div>
        </div>
    """, unsafe_allow_html=True)
    
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM ot_logs WHERE employee_name = ?", conn, params=(user['name'],))
    conn.close()
    
    if df.empty:
        st.info("No OT records found.")
    else:
        total_hrs = df['ot_hours'].sum()
        app_hrs = df[df['status'] == 'Approved']['verified_hours'].sum()
        total_amt = df['amount'].sum()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Hours Requested", f"{total_hrs:.1f} hrs")
        c2.metric("Approved Payable Hours", f"{app_hrs:.1f} hrs")
        c3.metric("Total Payout Amount", f"₹{total_amt:.0f}")
        
        st.dataframe(df[['date', 'ot_hours', 'task_type', 'productivity', 'status', 'amount']], use_container_width=True)
        
        if not df.empty:
            pdf_data = generate_pdf_report(df, f"OT History - {user['name']}")
            st.download_button("Download PDF Statement 📄", data=pdf_data, file_name="my_ot_history.pdf", mime="application/pdf")

# ==================== 3. APPROVAL DASHBOARD ====================
elif st.session_state.current_view == "dashboard":
    st.markdown("""
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <h2 style="margin: 0; color: #1E3A8A;">📊 TL Approval & Modern Analytics Dashboard</h2>
            <div class="brand-logo">EXCIT<span>EL</span></div>
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
        
        st.markdown("### 📈 Visual Analytics")
        ch1, ch2 = st.columns(2)
        
        with ch1:
            st.markdown("#### Status Breakdown")
            status_counts = df['status'].value_counts().reset_index()
            status_counts.columns = ['Status', 'Count']
            chart_status = alt.Chart(status_counts).mark_arc(innerRadius=50).encode(
                theta=alt.Theta(field="Count", type="quantitative"),
                color=alt.Color(field="Status", type="nominal", scale=alt.Scale(domain=['Pending', 'Approved', 'Rejected'], range=['#F59E0B', '#10B981', '#EF4444']))
            ).properties(height=220)
            st.altair_chart(chart_status, use_container_width=True)
            
        with ch2:
            st.markdown("#### Task-wise OT Hours")
            task_counts = df.groupby('task_type')['ot_hours'].sum().reset_index()
            chart_task = alt.Chart(task_counts).mark_bar(color='#1E3A8A', cornerRadiusTopLeft=6, cornerRadiusTopRight=6).encode(
                x=alt.X('task_type', sort='-y', title='Task Type'),
                y=alt.Y('ot_hours', title='Total Hours')
            ).properties(height=220)
            st.altair_chart(chart_task, use_container_width=True)

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
                                UPDATE ot_logs SET status = 'Approved', actual_output = ?, productivity = ?, verified_hours = ?, amount = ?, approved_by = ?, approved_at = ?
                                WHERE id = ?
                            """, (actual_out, prod, v_hrs, amt, user['name'], datetime.now().strftime("%Y-%m-%d %H:%M"), row['id']))
                            conn.commit()
                            conn.close()
                            st.success("Approved successfully!")
                            st.rerun()
                            
                        if col_btn2.button("Reject ❌", key=f"rej_{row['id']}"):
                            conn = get_connection()
                            cursor = conn.cursor()
                            cursor.execute("UPDATE ot_logs SET status = 'Rejected', approved_by = ?, approved_at = ? WHERE id = ?", (user['name'], datetime.now().strftime("%Y-%m-%d %H:%M"), row['id']))
                            conn.commit()
                            conn.close()
                            st.warning("Request rejected.")
                            st.rerun()

        st.markdown("### 📋 All Requests Log")
        st.dataframe(df[['date', 'employee_name', 'tl_name', 'task_type', 'ot_hours', 'actual_output', 'status', 'amount']], use_container_width=True)

# ==================== 4. REPORTS ENGINE ====================
elif st.session_state.current_view == "reports":
    st.markdown("""
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <h2 style="margin: 0; color: #1E3A8A;">📈 Advanced Reports Engine</h2>
            <div class="brand-logo">EXCIT<span>EL</span></div>
        </div>
    """, unsafe_allow_html=True)
    
    r_type = st.selectbox("Select Report Type", options=["Monthly Summary Report", "Detailed OT Log Report"])
    
    col1, col2 = st.columns(2)
    with col1:
        report_month = st.selectbox("Month", options=list(range(1, 13)), index=date.today().month - 1)
    with col2:
        report_year = st.selectbox("Year", options=[2025, 2026, 2027], index=1)
        
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM ot_logs", conn)
    conn.close()
    
    if not df.empty:
        df['date_dt'] = pd.to_datetime(df['date'])
        filtered_df = df[(df['date_dt'].dt.month == report_month) & (df['date_dt'].dt.year == report_year)]
        
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
            st.dataframe(filtered_df[['date', 'employee_name', 'emp_id', 'tl_name', 'task_type', 'ot_hours', 'status', 'amount']], use_container_width=True)
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                csv = filtered_df.to_csv(index=False).encode('utf-8')
                st.download_button("Download CSV 📥", csv, "detailed_ot_log.csv", "text/csv")
            with col_d2:
                pdf_data = generate_pdf_report(filtered_df, f"Detailed OT Log Report - {report_month}/{report_year}")
                st.download_button("Download PDF 📄", data=pdf_data, file_name="detailed_ot_log.pdf", mime="application/pdf")
    else:
        st.info("No records found.")

# ==================== 5. USER MANAGEMENT ====================
elif st.session_state.current_view == "admin":
    st.markdown("""
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <h2 style="margin: 0; color: #1E3A8A;">⚙️ Admin User Management</h2>
            <div class="brand-logo">EXCIT<span>EL</span></div>
        </div>
    """, unsafe_allow_html=True)
    
    with st.form("add_user_form"):
        st.markdown("### Add New User")
        new_name = st.text_input("Full Name")
        new_email = st.text_input("Google Email Address")
        new_role = st.selectbox("Role", options=["Employee", "TL", "Admin"])
        
        if st.form_submit_button("Add User ➕", type="primary"):
            if new_name and new_email:
                conn = get_connection()
                cursor = conn.cursor()
                try:
                    cursor.execute("INSERT INTO users VALUES (?, ?, ?)", (new_email, new_role, new_name))
                    conn.commit()
                    st.success(f"User {new_name} added successfully!")
                except Exception as e:
                    st.error(f"Error: {e}")
                finally:
                    conn.close()
            else:
                st.error("Please fill in both fields.")
                
    st.markdown("### Existing System Users")
    conn = get_connection()
    users_df = pd.read_sql("SELECT * FROM users", conn)
    conn.close()
    st.dataframe(users_df, use_container_width=True)