import streamlit as st
import psycopg2
from psycopg2 import pool
import pandas as pd
from datetime import datetime, date, timedelta
import altair as alt
import os
import hashlib
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ==================== AUTOMATIC THEME CONFIG ====================
os.makedirs(".streamlit", exist_ok=True)
config_path = ".streamlit/config.toml"
if not os.path.exists(config_path):
    with open(config_path, "w") as f:
        f.write("""
[theme]
base="light"
primaryColor="#FF6B00"
backgroundColor="#F4F6FB"
secondaryBackgroundColor="#FFFFFF"
textColor="#0E2B5C"
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
            CREATE TABLE IF NOT EXISTS audit_logs (
                id SERIAL PRIMARY KEY,
                performer TEXT,
                action TEXT,
                target TEXT,
                timestamp TEXT,
                details TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS password_resets (
                id SERIAL PRIMARY KEY,
                email TEXT,
                otp_code TEXT,
                expires_at TIMESTAMP,
                attempts INTEGER DEFAULT 0,
                is_used BOOLEAN DEFAULT FALSE
            )
        ''')
        default_pass_hash = hash_password("Password123")
        default_users = [
            ("testuser@dl.excitel.in", "Excitel Admin", "Admin", "EBND00001", "Nandini Puri", "TL01", default_pass_hash),
            ("ritu.mandal@dl.excitel.in", "Ritu Mandal", "TL", "EBND04635", "Nandini Puri", "TL01", default_pass_hash),
            ("jamal.khan@dl.excitel.in", "Jamal Khan", "TL", "EBND04471", "Nandini Puri", "TL01", default_pass_hash),
            ("abhishek.pandey@dl.excitel.in", "Abhishek Pandey", "TL", "EBND04472", "Nandini Puri", "TL01", default_pass_hash),
            ("basu.porwal@dl.excitel.in", "Basu Porwal", "Employee", "EBND04475", "Excitel Admin", "TL02", default_pass_hash)
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

# ==================== EMAIL OTP DISPATCH ENGINE (SMART FALLBACK) ====================
def dispatch_otp_email(recipient_email, otp_code):
    """
    Sends live email if [smtp] secrets are configured in Streamlit.
    Returns (success: bool, method: str) where method is 'SMTP' or 'FALLBACK_EMULATED'
    """
    if "smtp" in st.secrets:
        try:
            smtp_server = st.secrets["smtp"]["server"]
            smtp_port = int(st.secrets["smtp"]["port"])
            sender_email = st.secrets["smtp"]["sender_email"]
            sender_password = st.secrets["smtp"]["sender_password"]
            
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"Excitel OT Portal - Verification Code: {otp_code}"
            msg["From"] = f"Excitel Security <{sender_email}>"
            msg["To"] = recipient_email
            
            html_body = f"""
            <html>
                <body style="font-family: 'Segoe UI', Arial, sans-serif; background-color: #F4F6FB; margin: 0; padding: 20px;">
                    <div style="max-width: 500px; margin: 0 auto; background: #FFFFFF; border-radius: 12px; border-top: 5px solid #FF6B00; padding: 30px; box-shadow: 0 4px 12px rgba(0,0,0,0.08);">
                        <h2 style="color: #0E2B5C; margin: 0 0 10px 0;">Password Reset Request</h2>
                        <p style="color: #605E5C; font-size: 14px;">Use the following One-Time Passcode (OTP) to reset your Excitel Overtime Portal access credentials:</p>
                        <div style="text-align: center; margin: 25px 0;">
                            <span style="font-size: 32px; font-weight: 800; color: #FF6B00; letter-spacing: 6px; background: #FFF4EC; padding: 10px 24px; border-radius: 8px; border: 1px dashed #FF6B00;">{otp_code}</span>
                        </div>
                        <p style="color: #605E5C; font-size: 12px;">This code is valid for <b>10 minutes</b>. If you did not request this code, please inform your system administrator immediately.</p>
                        <hr style="border: none; border-top: 1px solid #E5E7EB; margin: 20px 0;">
                        <p style="color: #94A3B8; font-size: 11px; text-align: center;">Excitel Broadband Private Limited — Automated Security Protocol</p>
                    </div>
                </body>
            </html>
            """
            msg.attach(MIMEText(html_body, "html"))
            
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(sender_email, sender_password)
                server.sendmail(sender_email, recipient_email, msg.as_string())
            return True, "SMTP"
        except Exception as e:
            print(f"SMTP Dispatch Error: {e}")
            return False, "SMTP_FAILED"
            
    # Fallback to dev emulation when no SMTP secrets exist yet
    return True, "FALLBACK_EMULATED"

# ==================== PAGE CONFIG & CSS STYLING ====================
st.set_page_config(page_title="Excitel OT Portal", page_icon="⚡", layout="wide")

st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Segoe+UI:wght@400;600;700;800&display=swap');
        
        html, body, .stApp {
            background-color: #F4F6FB !important;
            font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif !important;
            margin: 0 !important;
            padding: 0 !important;
        }
        
        header[data-testid="stHeader"], footer, #MainMenu {
            display: none !important;
        }
        
        .main, .block-container {
            padding-top: 0 !important;
            padding-left: 0 !important;
            padding-right: 0 !important;
            max-width: 100% !important;
        }

        .excitel-topbar {
            background: #FFFFFF;
            width: 100%;
            padding: 14px 48px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 5px solid #FF6B00;
            margin: 0 0 28px 0;
            box-shadow: 0 2px 8px rgba(0,0,0,0.04);
        }
        .brand-cluster {
            display: flex;
            align-items: center;
            gap: 20px;
        }
        .brand-title {
            font-size: 24px;
            font-weight: 800;
            color: #0E2B5C;
            letter-spacing: -0.5px;
            line-height: 1;
        }
        .brand-sub {
            font-size: 11px;
            color: #605E5C;
            letter-spacing: 0.2px;
            margin-top: 2px;
        }
        .topbar-badge {
            background: #FF6B00;
            color: #FFFFFF;
            font-weight: 800;
            font-size: 12px;
            padding: 5px 16px;
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
        
        .nav-pill-wrapper {
            background: #1F3A60;
            border-radius: 35px;
            padding: 6px 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin: 0 auto 24px auto;
            max-width: 1180px;
            box-shadow: 0 4px 16px rgba(0,0,0,0.12);
        }
        .nav-user-label {
            color: #FFFFFF;
            font-weight: 700;
            font-size: 14px;
            display: flex;
            align-items: center;
            gap: 8px;
            padding-left: 12px;
        }

        .workspace-card {
            background: #FFFFFF;
            border-radius: 20px;
            border-top: 5px solid #FF6B00;
            padding: 34px 44px;
            max-width: 1180px;
            margin: 0 auto 30px auto;
            box-shadow: 0 8px 30px rgba(0,0,0,0.06);
        }

        div[data-testid="stForm"] {
            background: #FFFFFF !important;
            border: 1px solid #E2E8F0 !important;
            border-top: 5px solid #FF6B00 !important;
            border-radius: 20px !important;
            padding: 38px 42px !important;
            box-shadow: 0 12px 35px rgba(0,0,0,0.07) !important;
            margin: 0 auto !important;
        }

        /* High-Contrast Corporate Form Fields */
        div[data-baseweb="input"],
        div[data-baseweb="base-input"],
        div[data-testid="stTextInputRootElement"],
        div[data-testid="stTextInput"] > div > div,
        div[data-testid="stPasswordInput"] > div > div,
        div[data-baseweb="select"] > div,
        div[data-testid="stDateInput"] > div > div,
        div[data-testid="stTimeInput"] > div > div,
        div[data-testid="stNumberInput"] > div > div {
            border: 1.5px solid #CBD5E1 !important;
            border-radius: 8px !important;
            background-color: #F8FAFC !important;
            transition: all 0.2s ease-in-out !important;
        }

        input {
            color: #0E2B5C !important;
            font-size: 14px !important;
            font-weight: 500 !important;
        }
        input::placeholder {
            color: #94A3B8 !important;
            font-size: 13px !important;
        }

        div[data-baseweb="input"]:focus-within,
        div[data-baseweb="base-input"]:focus-within,
        div[data-testid="stTextInputRootElement"]:focus-within,
        div[data-testid="stTextInput"] > div > div:focus-within,
        div[data-testid="stPasswordInput"] > div > div:focus-within,
        div[data-baseweb="select"] > div:focus-within,
        div[data-testid="stDateInput"] > div > div:focus-within,
        div[data-testid="stTimeInput"] > div > div:focus-within,
        div[data-testid="stNumberInput"] > div > div:focus-within {
            border-color: #FF6B00 !important;
            background-color: #FFFFFF !important;
            box-shadow: 0 0 0 3px rgba(255, 107, 0, 0.18) !important;
        }

        div[data-testid="stWidgetLabel"] label p {
            color: #0E2B5C !important;
            font-weight: 700 !important;
            font-size: 12px !important;
            letter-spacing: 0.4px !important;
            text-transform: uppercase !important;
        }

        div[data-testid="stFormSubmitButton"] > button,
        .stButton > button {
            background: #FF6B00 !important;
            color: #FFFFFF !important;
            border: none !important;
            border-radius: 8px !important;
            font-size: 14px !important;
            font-weight: 700 !important;
            padding: 10px 20px !important;
            box-shadow: 0 4px 14px rgba(255, 107, 0, 0.28) !important;
            transition: background 0.2s ease, transform 0.1s ease !important;
            width: 100% !important;
        }

        div[data-testid="stFormSubmitButton"] > button:hover,
        .stButton > button:hover {
            background: #E05D00 !important;
            box-shadow: 0 6px 18px rgba(224, 93, 0, 0.35) !important;
        }

        .kpi-grid {
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 16px;
            margin-bottom: 25px;
        }
        .kpi-box {
            background: #FFFFFF;
            border-radius: 14px;
            border: 1px solid #E5E7EB;
            padding: 16px 8px;
            text-align: center;
            box-shadow: 0 2px 8px rgba(0,0,0,0.03);
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
        }
        .kpi-val {
            font-size: 26px;
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

        .proxy-container {
            border: 2px dashed #2563EB;
            border-radius: 12px;
            padding: 14px 18px;
            background: #F8FAFF;
            margin-bottom: 20px;
        }
    </style>
""", unsafe_allow_html=True)

# ==================== EMAIL OTP PASSWORD RESET MODAL ====================
@st.dialog("🔐 Self-Service Password Reset (Email OTP)")
def email_otp_password_reset_dialog():
    if "reset_stage" not in st.session_state:
        st.session_state.reset_stage = 1
    if "reset_target_email" not in st.session_state:
        st.session_state.reset_target_email = ""
    if "emulated_otp_display" not in st.session_state:
        st.session_state.emulated_otp_display = ""

    # STEP 1: REQUEST 6-DIGIT CODE
    if st.session_state.reset_stage == 1:
        st.markdown("<p style='font-size:13px; color:#605E5C;'>Enter your official email to receive a 6-digit verification code.</p>", unsafe_allow_html=True)
        with st.form("req_otp_form"):
            r_email = st.text_input("Official Email ID", placeholder="testuser@dl.excitel.in")
            st.markdown("<br>", unsafe_allow_html=True)
            send_otp_btn = st.form_submit_button("Send Verification Code 📩", use_container_width=True)

            if send_otp_btn:
                clean_email = r_email.strip().lower()
                if not clean_email:
                    st.error("Please enter your official email.")
                else:
                    conn = get_connection()
                    try:
                        cursor = conn.cursor()
                        cursor.execute("SELECT name FROM users WHERE email = %s", (clean_email,))
                        user_match = cursor.fetchone()
                        
                        if not user_match:
                            st.error("Email not found in registered directory.")
                        else:
                            generated_otp = f"{random.randint(100000, 999999)}"
                            expires_at = datetime.now() + timedelta(minutes=10)
                            
                            # Invalidate old unused OTPs
                            cursor.execute("UPDATE password_resets SET is_used = TRUE WHERE email = %s", (clean_email,))
                            cursor.execute("""
                                INSERT INTO password_resets (email, otp_code, expires_at, attempts, is_used)
                                VALUES (%s, %s, %s, 0, FALSE)
                            """, (clean_email, generated_otp, expires_at))
                            conn.commit()
                            
                            record_audit(clean_email, "OTP_REQUEST", clean_email, "Requested 6-digit recovery code")
                            
                            # Dispatch OTP
                            success, mode = dispatch_otp_email(clean_email, generated_otp)
                            st.session_state.reset_target_email = clean_email
                            st.session_state.reset_stage = 2
                            
                            if mode == "FALLBACK_EMULATED":
                                st.session_state.emulated_otp_display = generated_otp
                            st.rerun()
                    finally:
                        release_connection(conn)

    # STEP 2: VERIFY CODE & SET NEW PASSWORD
    elif st.session_state.reset_stage == 2:
        st.markdown(f"<p style='font-size:13px; color:#605E5C;'>Code sent to: <b>{st.session_state.reset_target_email}</b></p>", unsafe_allow_html=True)
        
        # Display emulated testing banner if SMTP secrets are not yet added
        if st.session_state.emulated_otp_display:
            st.info(f"🧪 **Test Mode Active (No SMTP Configured Yet):**\n\nYour 6-Digit OTP is: **`{st.session_state.emulated_otp_display}`** *(Valid for 10m)*")

        with st.form("verify_otp_form"):
            input_otp = st.text_input("6-Digit Verification Code", placeholder="e.g. 842109", max_chars=6)
            new_pwd = st.text_input("New Password", type="password", placeholder="Enter new password (min 6 characters)")
            conf_pwd = st.text_input("Confirm New Password", type="password", placeholder="Re-enter new password")
            st.markdown("<br>", unsafe_allow_html=True)
            verify_btn = st.form_submit_button("Verify & Change Password ✅", use_container_width=True)

            if verify_btn:
                if not input_otp or not new_pwd or not conf_pwd:
                    st.error("Please fill in all verification fields.")
                elif len(new_pwd) < 6:
                    st.error("New password must be at least 6 characters.")
                elif new_pwd != conf_pwd:
                    st.error("Passwords do not match.")
                else:
                    conn = get_connection()
                    try:
                        cursor = conn.cursor()
                        cursor.execute("""
                            SELECT id, otp_code, expires_at, attempts, is_used 
                            FROM password_resets 
                            WHERE email = %s AND is_used = FALSE 
                            ORDER BY id DESC LIMIT 1
                        """, (st.session_state.reset_target_email,))
                        reset_record = cursor.fetchone()
                        
                        if not reset_record:
                            st.error("No active reset session found. Please request a new code.")
                        else:
                            rec_id, valid_code, expires_at, attempts, is_used = reset_record
                            
                            if datetime.now() > expires_at:
                                st.error("❌ Verification code expired (10m limit). Please request a new code.")
                            elif attempts >= 3:
                                cursor.execute("UPDATE password_resets SET is_used = TRUE WHERE id = %s", (rec_id,))
                                conn.commit()
                                st.error("❌ Too many incorrect attempts. Code invalidated.")
                            elif input_otp.strip() != valid_code:
                                cursor.execute("UPDATE password_resets SET attempts = attempts + 1 WHERE id = %s", (rec_id,))
                                conn.commit()
                                st.error(f"❌ Invalid verification code. Attempts remaining: {2 - attempts}")
                            else:
                                # Successful verification: update password and invalidate OTP
                                new_hash = hash_password(new_pwd)
                                cursor.execute("UPDATE users SET password_hash = %s WHERE email = %s", (new_hash, st.session_state.reset_target_email))
                                cursor.execute("UPDATE password_resets SET is_used = TRUE WHERE id = %s", (rec_id,))
                                conn.commit()
                                
                                record_audit(st.session_state.reset_target_email, "FORGOT_PWD_RESET_SUCCESS", st.session_state.reset_target_email, "Self-service recovery completed")
                                
                                # Reset flow state
                                st.session_state.reset_stage = 1
                                st.session_state.reset_target_email = ""
                                st.session_state.emulated_otp_display = ""
                                st.success("Password reset successfully! Please sign in with your new password.")
                                st.rerun()
                    finally:
                        release_connection(conn)

        if st.button("⬅️ Request New Code", use_container_width=True):
            st.session_state.reset_stage = 1
            st.session_state.emulated_otp_display = ""
            st.rerun()

# ==================== LOGGED-IN ADMIN/USER PASSWORD UPDATE MODAL ====================
@st.dialog("🔑 Password Management")
def authenticated_password_dialog(logged_in_user):
    st.markdown("<p style='font-size:13px; color:#605E5C;'>Update portal credentials with audit logging.</p>", unsafe_allow_html=True)
    
    conn = get_connection()
    try:
        users_df = pd.read_sql("SELECT email, name, role, password_hash FROM users", conn)
    finally:
        release_connection(conn)

    user_role = logged_in_user['role']
    
    with st.form("auth_pwd_modal_form"):
        if user_role == "Admin":
            target_email = st.selectbox("Select Account", options=users_df['email'].tolist(), index=users_df['email'].tolist().index(logged_in_user['email']))
        else:
            target_email = logged_in_user['email']
            st.text_input("Account Email", value=target_email, disabled=True)

        require_old = not (user_role == "Admin" and target_email != logged_in_user['email'])
        if require_old:
            curr_pass = st.text_input("Current Password", type="password", placeholder="Verify existing password")
            
        new_pass = st.text_input("New Password", type="password", placeholder="Min 6 characters")
        conf_pass = st.text_input("Confirm New Password", type="password", placeholder="Re-enter new password")
        
        st.markdown("<br>", unsafe_allow_html=True)
        save_btn = st.form_submit_button("Update Password 💾", use_container_width=True)
        
        if save_btn:
            if not new_pass or not conf_pass:
                st.error("Please fill in all fields.")
            elif len(new_pass) < 6:
                st.error("Password must be at least 6 characters.")
            elif new_pass != conf_pass:
                st.error("Passwords do not match.")
            else:
                user_rec = users_df[users_df['email'] == target_email]
                if user_rec.empty:
                    st.error("User record missing.")
                else:
                    if require_old:
                        cur_hash = user_rec.iloc[0]['password_hash']
                        if not ((cur_hash == hash_password(curr_pass)) or (cur_hash == hashlib.sha256(curr_pass.encode()).hexdigest())):
                            st.error("Current password incorrect.")
                            return
                    
                    new_hash = hash_password(new_pass)
                    conn = get_connection()
                    try:
                        cur = conn.cursor()
                        cur.execute("UPDATE users SET password_hash = %s WHERE email = %s", (new_hash, target_email))
                        conn.commit()
                        record_audit(logged_in_user['email'], "ADMIN_PASSWORD_CHANGE", target_email, "Credentials updated")
                        st.success("Password updated successfully!")
                        st.rerun()
                    finally:
                        release_connection(conn)

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
    st.markdown("""
        <div class="excitel-topbar">
            <div class="brand-cluster">
                <div>
                    <div class="brand-title">✴️ Excitel</div>
                    <div class="brand-sub">The world is home</div>
                </div>
            </div>
            <div class="topbar-badge">SECURE_AUTH</div>
        </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.15, 1])
    with col2:
        with st.form("login_form"):
            st.markdown("""
                <div style="text-align: center; margin-bottom: 24px;">
                    <div style="font-size: 26px; font-weight: 800; color: #0E2B5C;">EXCIT<span style="color:#FF6B00;">EL</span></div>
                    <div style="font-size: 16px; font-weight: 700; color: #0E2B5C; margin-top: 4px;">Overtime Tracking Portal</div>
                    <div style="font-size: 13px; color: #605E5C; margin-top: 4px;">Sign in with your official Excitel credentials</div>
                </div>
            """, unsafe_allow_html=True)
            
            login_email = st.text_input("Official Email ID", placeholder="e.g. testuser@dl.excitel.in")
            login_password = st.text_input("Password", type="password", placeholder="••••••••••••")
            st.markdown("<br>", unsafe_allow_html=True)
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
                        if db_pass_hash == hash_password(login_password) or db_pass_hash == hashlib.sha256(login_password.encode()).hexdigest():
                            st.session_state.authenticated = True
                            st.session_state.user_email = login_email.strip().lower()
                            st.session_state.user_name = db_name
                            st.session_state.user_role = db_role
                            st.session_state.current_view = "portal"
                            record_audit(st.session_state.user_email, "USER_LOGIN", "PORTAL", "Successful authentication")
                            st.rerun()
                        else:
                            st.error("❌ Incorrect password.")
                    else:
                        st.error("❌ Email not registered in the system.")

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔑 Forgot / Change Password via Email OTP", use_container_width=True):
            email_otp_password_reset_dialog()
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
    return {"email": st.session_state.user_email, "name": st.session_state.user_name, "role": st.session_state.user_role, "empId": "EBND00001", "tlName": "Unassigned", "tlId": ""}

user = get_logged_in_user()

# ==================== TOP BAR & LIVE CLOCK ====================
PAGE_BADGE_MAP = {
    "portal": "OT_FORM",
    "history": "ACTIONED_OT",
    "dashboard": "TL_DASHBOARD",
    "reports": "REPORTS_CALC",
    "admin": "ADMIN_PANEL"
}
current_badge = PAGE_BADGE_MAP.get(st.session_state.current_view, "OT_TRACKER")

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
            <div id="live-clock" style="font-size: 13px; font-weight: 700; color: #0E2B5C; min-width: 175px; text-align: right;"></div>
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
            const el = document.getElementById('live-clock');
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
    <div class="nav-pill-wrapper">
        <div class="nav-user-label">
            <span>🛡️</span> {user['name']} ({user['role']})
        </div>
    </div>
""", unsafe_allow_html=True)

nav_cols = st.columns([1, 1, 1, 1, 1, 0.9, 0.8])

with nav_cols[0]:
    if st.button("📄 OT Form", key="nav_form", use_container_width=True):
        st.session_state.current_view = "portal"
        st.rerun()

with nav_cols[1]:
    if st.button("🕒 History", key="nav_hist", use_container_width=True):
        st.session_state.current_view = "history"
        st.rerun()

if user['role'] in ["TL", "Admin"]:
    with nav_cols[2]:
        if st.button("📊 Dashboard", key="nav_dash", use_container_width=True):
            st.session_state.current_view = "dashboard"
            st.rerun()

if user['role'] in ["TL", "Admin"]:
    with nav_cols[3]:
        if st.button("📈 Reports", key="nav_rep", use_container_width=True):
            st.session_state.current_view = "reports"
            st.rerun()

if user['role'] == "Admin":
    with nav_cols[4]:
        if st.button("👥 Admin", key="nav_adm", use_container_width=True):
            st.session_state.current_view = "admin"
            st.rerun()

with nav_cols[5]:
    if st.button("🔑 Password", key="nav_pwd", use_container_width=True):
        authenticated_password_dialog(user)

with nav_cols[6]:
    if st.button("🚪 Logout", key="nav_out", use_container_width=True):
        record_audit(user['email'], "USER_LOGOUT", "PORTAL", "Manual sign out")
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
        return 'background-color: #E6F8F0; color: #00A86B; font-weight: 800; border-radius: 14px; text-align: center;'
    elif val == 'REJECTED':
        return 'background-color: #FDE8E8; color: #E03E3E; font-weight: 800; border-radius: 14px; text-align: center;'
    elif val == 'PENDING':
        return 'background-color: #FEF3C7; color: #D97706; font-weight: 800; border-radius: 14px; text-align: center;'
    return ''

# ==================== 1. OT FORM PORTAL ====================
if st.session_state.current_view == "portal":
    st.markdown("""
        <div class="workspace-card">
            <div style="text-align: center; margin-bottom: 28px;">
                <div style="font-size: 26px; font-weight: 800; color: #0E2B5C;">EXCIT<span style="color:#FF6B00;">EL</span></div>
                <div style="font-size: 16px; font-weight: 700; color: #0E2B5C; margin-top: 4px;">OT Entry Portal</div>
            </div>
    """, unsafe_allow_html=True)
    
    target_name = user['name']
    target_emp_id = user['empId']
    target_tl = user['tlName']
    
    if user['role'] in ["TL", "Admin"]:
        st.markdown('<div class="proxy-container"><b>👥 SUBMIT ON BEHALF OF EMPLOYEE</b>', unsafe_allow_html=True)
        conn = get_connection()
        try:
            emp_df = pd.read_sql("SELECT name FROM users WHERE role = 'Employee'", conn)
        finally:
            release_connection(conn)
        selected_proxy = st.selectbox("", options=["Select Employee..."] + emp_df['name'].tolist(), label_visibility="collapsed")
        st.markdown('</div>', unsafe_allow_html=True)
        
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
        st.text_input("EMPLOYEE NAME", value=target_name, disabled=True)
        st.text_input("ASSIGNED TEAM LEADER & ID", value=f"{target_tl} ({user['tlId'] if user['tlId'] else '1009'})", disabled=True)
    with col2:
        st.text_input("EMPLOYEE ID", value=target_emp_id, disabled=True)
        req_date = st.date_input("DATE", value=date.today())
        
    col3, col4 = st.columns(2)
    with col3:
        shift_start = st.time_input("SHIFT START TIME", value=datetime.strptime("09:00", "%H:%M").time())
        ot_start = st.time_input("OT START TIME", value=datetime.strptime("18:00", "%H:%M").time())
    with col4:
        shift_end = st.time_input("SHIFT END TIME", value=datetime.strptime("18:00", "%H:%M").time())
        ot_end = st.time_input("OT END TIME", value=datetime.strptime("21:00", "%H:%M").time())
        
    task_type = st.selectbox("TASK TYPE", options=['Select Task...', 'Calls', 'Backend', 'Tickets', 'Complaints', 'Email'])
    
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🚀 Submit OT Request", type="primary", use_container_width=True):
        if task_type == 'Select Task...':
            st.error("Please select a valid Task Type.")
        else:
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
                st.error("❌ Shift Overlap: Overtime hours cannot overlap regular shift timings.")
            elif ot_hours <= 0:
                st.error("❌ Time Error: OT End time must be after Start time.")
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
                        conn.commit()
                        record_audit(user['email'], "SUBMIT_OT", target_name, f"Logged {ot_hours}h on {req_date_str}")
                        st.success(f"✅ OT Request successfully submitted for {target_name} ({ot_hours} hrs)!")
                finally:
                    release_connection(conn)

    st.markdown("</div>", unsafe_allow_html=True)

# ==================== 2. HISTORY TAB ====================
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
        total_reqs = len(df)
        approved_reqs = len(df[df['status'] == 'Approved'])
        rejected_reqs = len(df[df['status'] == 'Rejected'])
        approved_hours = df[df['status'] == 'Approved']['verified_hours'].sum()
        total_payout = df[df['status'] == 'Approved']['amount'].sum()
        
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
    st.markdown("""
        <div class="workspace-card">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;">
                <div style="font-size:20px; font-weight:800; color:#0E2B5C;">📊 TL Approval Dashboard & Analytics</div>
                <div style="font-size:22px; font-weight:800; color:#0E2B5C;">EXCIT<span style="color:#FF6B00;">EL</span></div>
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
        st.info("No overtime claims currently registered.")
    else:
        total_ot_hours = df['ot_hours'].sum()
        total_ot_cost = df[df['status'] == 'Approved']['amount'].sum()
        pending_count = len(df[df['status'] == 'Pending'])
        approved_count = len(df[df['status'] == 'Approved'])
        
        st.markdown(f"""
            <div style="display:grid; grid-template-columns:repeat(4, 1fr); gap:16px; margin-bottom:25px;">
                <div class="kpi-box" style="border-radius:12px; border:1px solid #E5E7EB; padding:18px;">
                    <div style="font-size:26px; font-weight:800; color:#0E2B5C;">{total_ot_hours:.1f}</div>
                    <div style="font-size:11px; font-weight:700; color:#605E5C; margin-top:4px;">OT HOURS</div>
                </div>
                <div class="kpi-box" style="border-radius:12px; border:1px solid #E5E7EB; padding:18px;">
                    <div style="font-size:26px; font-weight:800; color:#0E2B5C;">₹{total_ot_cost:.0f}</div>
                    <div style="font-size:11px; font-weight:700; color:#605E5C; margin-top:4px;">OT COST</div>
                </div>
                <div class="kpi-box" style="border-radius:12px; border:1px solid #E5E7EB; padding:18px;">
                    <div style="font-size:26px; font-weight:800; color:#0E2B5C;">{pending_count}</div>
                    <div style="font-size:11px; font-weight:700; color:#605E5C; margin-top:4px;">PENDING</div>
                </div>
                <div class="kpi-box" style="border-radius:12px; border:1px solid #E5E7EB; padding:18px;">
                    <div style="font-size:26px; font-weight:800; color:#0E2B5C;">{approved_count}</div>
                    <div style="font-size:11px; font-weight:700; color:#605E5C; margin-top:4px;">APPROVED</div>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        ch1, ch2, ch3 = st.columns(3)
        with ch1:
            st.markdown("<div style='font-size:12px; font-weight:700; color:#0E2B5C; text-align:center;'>📊 STATUS BREAKDOWN</div>", unsafe_allow_html=True)
            status_df = df['status'].value_counts().reset_index()
            status_df.columns = ['Status', 'Count']
            pie = alt.Chart(status_df).mark_arc(innerRadius=42).encode(
                theta="Count:Q",
                color=alt.Color("Status:N", scale=alt.Scale(domain=['Pending', 'Approved', 'Rejected'], range=['#F59E0B', '#10B981', '#EF4444']))
            ).properties(height=190)
            st.altair_chart(pie, use_container_width=True)
            
        with ch2:
            st.markdown("<div style='font-size:12px; font-weight:700; color:#0E2B5C; text-align:center;'>⚡ TASK-WISE OT HOURS</div>", unsafe_allow_html=True)
            task_df = df.groupby('task_type')['ot_hours'].sum().reset_index()
            bar = alt.Chart(task_df).mark_bar(color='#1F3A60', cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
                x=alt.X('task_type:N', title=None),
                y=alt.Y('ot_hours:Q', title=None)
            ).properties(height=190)
            st.altair_chart(bar, use_container_width=True)
            
        with ch3:
            st.markdown("<div style='font-size:12px; font-weight:700; color:#0E2B5C; text-align:center;'>🎯 PRODUCTIVITY COMPLIANCE</div>", unsafe_allow_html=True)
            comp_count = len(df[df['productivity'] >= 0.70])
            low_count = len(df[df['productivity'] < 0.70])
            comp_df = pd.DataFrame({'Compliance': ['Compliant (≥70%)', 'Low (<70%)'], 'Count': [comp_count, low_count]})
            comp_pie = alt.Chart(comp_df).mark_arc(innerRadius=42).encode(
                theta="Count:Q",
                color=alt.Color("Compliance:N", scale=alt.Scale(domain=['Compliant (≥70%)', 'Low (<70%)'], range=['#10B981', '#EF4444']))
            ).properties(height=190)
            st.altair_chart(comp_pie, use_container_width=True)

        st.markdown("<hr style='border:none; border-top:1px solid #E5E7EB; margin:20px 0;'>", unsafe_allow_html=True)
        
        f_c1, f_c2, f_c3, f_c4, f_c5, f_c6 = st.columns(6)
        with f_c1:
            emp_filt = st.selectbox("EMPLOYEE", options=["Select Employee"] + sorted(df['employee_name'].unique().tolist()))
        with f_c2:
            tl_filt = st.selectbox("TEAM LEADER (TL)", options=["Select TL"] + sorted(df['tl_name'].unique().tolist()))
        with f_c3:
            task_filt = st.selectbox("TASK TYPE", options=["Select Task"] + sorted(df['task_type'].unique().tolist()))
        with f_c4:
            status_filt = st.selectbox("STATUS", options=["Select Status", "Pending", "Approved", "Rejected"])
        with f_c5:
            from_d = st.date_input("FROM DATE", value=date(date.today().year, date.today().month, 1))
        with f_c6:
            to_d = st.date_input("TO DATE", value=date.today())
            
        filtered_df = df.copy()
        filtered_df['date_dt'] = pd.to_datetime(filtered_df['date']).dt.date
        filtered_df = filtered_df[(filtered_df['date_dt'] >= from_d) & (filtered_df['date_dt'] <= to_d)]
        if emp_filt != "Select Employee":
            filtered_df = filtered_df[filtered_df['employee_name'] == emp_filt]
        if tl_filt != "Select TL":
            filtered_df = filtered_df[filtered_df['tl_name'] == tl_filt]
        if task_filt != "Select Task":
            filtered_df = filtered_df[filtered_df['task_type'] == task_filt]
        if status_filt != "Select Status":
            filtered_df = filtered_df[filtered_df['status'] == status_filt]

        st.markdown("### 📋 Claims Verification & Master Table")
        
        pending_rows = filtered_df[filtered_df['status'] == 'Pending']
        if not pending_rows.empty:
            for idx, p_row in pending_rows.iterrows():
                p_c1, p_c2, p_c3, p_c4, p_c5, p_c6 = st.columns([2.5, 1.5, 1.5, 2, 1.5, 1.5])
                with p_c1:
                    st.markdown(f"**{p_row['employee_name']}**<br><span style='font-size:12px; color:#605E5C;'>{p_row['date']} | {p_row['task_type']} ({p_row['ot_hours']}h)</span>", unsafe_allow_html=True)
                with p_c2:
                    st.write(f"Target: **{p_row['expected_output']:.0f}**")
                with p_c3:
                    user_actual = st.number_input("Actual", min_value=1.0, value=float(p_row['expected_output']), key=f"dash_out_{p_row['id']}", label_visibility="collapsed")
                with p_c4:
                    dash_rej_reason = st.text_input("Reason", placeholder="Rejection note...", key=f"dash_rej_{p_row['id']}", label_visibility="collapsed")
                with p_c5:
                    if st.button("Approve", key=f"app_d_{p_row['id']}", type="primary"):
                        if p_row['employee_name'] == user['name']:
                            st.error("Self-approval blocked.")
                        else:
                            exp = p_row['expected_output']
                            prod = (user_actual / exp) if exp > 0 else 0
                            v_hrs = p_row['ot_hours'] if prod >= 0.7 else (p_row['ot_hours'] * 0.5 if prod >= 0.5 else 0)
                            amt = v_hrs * 120
                            conn = get_connection()
                            try:
                                cur = conn.cursor()
                                cur.execute("""
                                    UPDATE ot_logs SET status='Approved', actual_output=%s, productivity=%s, verified_hours=%s, amount=%s, approved_by=%s, approved_at=%s WHERE id=%s
                                """, (user_actual, prod, v_hrs, amt, user['name'], datetime.now().strftime("%Y-%m-%d %H:%M"), p_row['id']))
                                conn.commit()
                                record_audit(user['email'], "APPROVE_OT", p_row['employee_name'], f"Approved claim #{p_row['id']}")
                            finally:
                                release_connection(conn)
                            st.rerun()
                with p_c6:
                    if st.button("Reject", key=f"rej_d_{p_row['id']}"):
                        if not dash_rej_reason.strip():
                            st.error("Rejection reason required.")
                        else:
                            exp = p_row['expected_output']
                            prod = (user_actual / exp) if exp > 0 else 0
                            conn = get_connection()
                            try:
                                cur = conn.cursor()
                                cur.execute("""
                                    UPDATE ot_logs SET status='Rejected', actual_output=%s, productivity=%s, verified_hours=0, amount=0, approved_by=%s, approved_at=%s, rejection_reason=%s WHERE id=%s
                                """, (user_actual, prod, user['name'], datetime.now().strftime("%Y-%m-%d %H:%M"), dash_rej_reason.strip(), p_row['id']))
                                conn.commit()
                                record_audit(user['email'], "REJECT_OT", p_row['employee_name'], f"Reason: {dash_rej_reason.strip()}")
                            finally:
                                release_connection(conn)
                            st.rerun()
                st.markdown("<hr style='border:none; border-top:1px dashed #E5E7EB; margin:10px 0;'>", unsafe_allow_html=True)
        
        d_table = filtered_df.copy()
        d_table['formatted_date'] = pd.to_datetime(d_table['date']).dt.strftime('%d-%b-%Y')
        d_table['hours_num'] = d_table['ot_hours'].apply(lambda x: int(x) if x.is_integer() else x)
        d_table['target_num'] = d_table['expected_output'].astype(int)
        d_table['actual_num'] = d_table['actual_output'].astype(int)
        d_table['prod_pct'] = (d_table['productivity'] * 100).round(0).astype(int).astype(str) + '%'
        d_table['amount_fmt'] = d_table['amount'].apply(lambda x: f"₹{x:.0f}")
        d_table['status_upper'] = d_table['status'].str.upper()
        d_table['action_status'] = d_table['status'].apply(lambda s: "DONE" if s in ["Approved", "Rejected"] else "PENDING")
        
        master_cols = d_table[['formatted_date', 'employee_name', 'tl_name', 'task_type', 'hours_num', 'target_num', 'actual_num', 'prod_pct', 'amount_fmt', 'status_upper', 'action_status']].copy()
        master_cols.columns = ['DATE', 'EMPLOYEE', 'TL', 'TASK', 'HOURS', 'TARGET', 'ACTUAL', 'PROD%', 'AMOUNT', 'STATUS', 'ACTION']
        
        styled_master = master_cols.style.map(color_productivity_and_status, subset=['PROD%', 'STATUS'])
        st.dataframe(styled_master, use_container_width=True, hide_index=True)

    st.markdown("</div>", unsafe_allow_html=True)

# ==================== 4. REPORTS ENGINE ====================
elif st.session_state.current_view == "reports":
    st.markdown("""
        <div class="workspace-card">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:24px;">
                <div style="font-size:20px; font-weight:800; color:#0E2B5C;">📄 Advanced Reports Engine</div>
                <div style="font-size:22px; font-weight:800; color:#0E2B5C;">EXCIT<span style="color:#FF6B00;">EL</span></div>
            </div>
    """, unsafe_allow_html=True)
    
    r_col1, r_col2, r_col3, r_col4, r_col5, r_col6 = st.columns([2, 1.8, 1.8, 1.5, 1.3, 1.3])
    with r_col1:
        report_type = st.selectbox("SELECT REPORT TYPE", options=["Monthly Summary Report", "Detailed OT Log Report"])
    with r_col2:
        filter_mode = st.selectbox("FILTER MODE", options=["Month / Year", "Custom Date Range"])
    with r_col3:
        rep_month = st.selectbox("MONTH", options=["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], index=8)
        month_int = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"].index(rep_month) + 1
    with r_col4:
        rep_year = st.selectbox("YEAR", options=[2025, 2026, 2027], index=1)
    with r_col5:
        st.markdown("<br>", unsafe_allow_html=True)
        gen_btn = st.button("🔍 Generate", type="primary", use_container_width=True)
    with r_col6:
        st.markdown("<br>", unsafe_allow_html=True)
        export_btn = st.button("📥 Export CSV", use_container_width=True)

    conn = get_connection()
    try:
        r_query = "SELECT * FROM ot_logs"
        if user['role'] == 'TL':
            r_query += f" WHERE tl_name = '{user['name']}'"
        raw_rep_df = pd.read_sql(r_query, conn)
    finally:
        release_connection(conn)
        
    if not raw_rep_df.empty:
        raw_rep_df['date_dt'] = pd.to_datetime(raw_rep_df['date'])
        filtered_rep = raw_rep_df[(raw_rep_df['date_dt'].dt.month == month_int) & (raw_rep_df['date_dt'].dt.year == rep_year)]
        
        tot_emp = filtered_rep['employee_name'].nunique()
        tot_hrs = filtered_rep['ot_hours'].sum()
        tot_payout = filtered_rep[filtered_rep['status'] == 'Approved']['amount'].sum()
        
        st.markdown(f"""
            <div style="background:#1F3A60; border-radius:12px; padding:18px 24px; display:grid; grid-template-columns:repeat(3, 1fr); text-align:center; color:#FFFFFF; margin:22px 0;">
                <div>
                    <div style="font-size:11px; font-weight:700; letter-spacing:0.5px; opacity:0.8;">TOTAL EMPLOYEES</div>
                    <div style="font-size:26px; font-weight:800; margin-top:4px;">{tot_emp}</div>
                </div>
                <div>
                    <div style="font-size:11px; font-weight:700; letter-spacing:0.5px; opacity:0.8;">TOTAL HOURS</div>
                    <div style="font-size:26px; font-weight:800; margin-top:4px;">{tot_hrs:.1f}</div>
                </div>
                <div>
                    <div style="font-size:11px; font-weight:700; letter-spacing:0.5px; opacity:0.8;">TOTAL PAYOUT</div>
                    <div style="font-size:26px; font-weight:800; margin-top:4px;">₹{tot_payout:.0f}</div>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        if report_type == "Monthly Summary Report":
            summary_view = filtered_rep.groupby(['employee_name', 'emp_id']).agg(
                ot_days=('date', 'count'),
                total_hours=('ot_hours', 'sum'),
                approved_hours=('verified_hours', 'sum'),
                total_amount=('amount', 'sum')
            ).reset_index()
            
            summary_view.columns = ['EMPLOYEE NAME', 'ID', 'OT DAYS', 'TOTAL HOURS', 'APPROVED HRS', 'AMOUNT PAID']
            summary_view['AMOUNT PAID'] = summary_view['AMOUNT PAID'].apply(lambda x: f"₹{x:.0f}")
            st.dataframe(summary_view, use_container_width=True, hide_index=True)
            
            if export_btn:
                csv_bytes = summary_view.to_csv(index=False).encode('utf-8')
                st.download_button("Download Monthly Report CSV", data=csv_bytes, file_name=f"Excitel_Monthly_Report_{rep_month}_{rep_year}.csv", mime="text/csv")
        else:
            det_view = filtered_rep[['date', 'employee_name', 'emp_id', 'tl_name', 'task_type', 'ot_hours', 'expected_output', 'actual_output', 'productivity', 'status', 'amount']].copy()
            det_view['date'] = pd.to_datetime(det_view['date']).dt.strftime('%d-%b-%Y')
            det_view['productivity'] = (det_view['productivity'] * 100).round(0).astype(int).astype(str) + '%'
            det_view['amount'] = det_view['amount'].apply(lambda x: f"₹{x:.0f}")
            det_view.columns = ['DATE', 'EMPLOYEE NAME', 'EMP ID', 'TL NAME', 'TASK TYPE', 'OT HOURS', 'TARGET', 'ACTUAL', 'PROD %', 'STATUS', 'AMOUNT PAID']
            
            styled_det = det_view.style.map(color_productivity_and_status, subset=['PROD %', 'STATUS'])
            st.dataframe(styled_det, use_container_width=True, hide_index=True)
            
            if export_btn:
                csv_bytes = det_view.to_csv(index=False).encode('utf-8')
                st.download_button("Download Detailed Report CSV", data=csv_bytes, file_name=f"Excitel_Detailed_Report_{rep_month}_{rep_year}.csv", mime="text/csv")
    else:
        st.info("No records match the requested period.")

    st.markdown("</div>", unsafe_allow_html=True)

# ==================== 5. ADMIN PANEL ====================
elif st.session_state.current_view == "admin":
    st.markdown("""
        <div class="workspace-card">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:24px;">
                <div style="font-size:20px; font-weight:800; color:#0E2B5C;">👥 User Management</div>
                <div style="font-size:22px; font-weight:800; color:#0E2B5C;">EXCIT<span style="color:#FF6B00;">EL</span></div>
            </div>
    """, unsafe_allow_html=True)
    
    if user['role'] != "Admin":
        st.error("Restricted to system administrators.")
    else:
        with st.form("admin_create_form"):
            u_c1, u_c2, u_c3, u_c4 = st.columns([2.5, 3, 2, 1.8])
            with u_c1:
                new_name = st.text_input("FULL NAME", placeholder="e.g. John Doe")
            with u_c2:
                new_email = st.text_input("GOOGLE EMAIL ADDRESS", placeholder="testuser@dl.excitel.in")
            with u_c3:
                new_role = st.selectbox("SYSTEM ROLE", options=["Employee", "TL", "Admin"])
            with u_c4:
                st.markdown("<br>", unsafe_allow_html=True)
                create_btn = st.form_submit_button("+ Add User", type="primary", use_container_width=True)
                
            if create_btn:
                if not new_name or not new_email:
                    st.error("Please provide both name and email.")
                else:
                    conn = get_connection()
                    try:
                        cur = conn.cursor()
                        cur.execute("""
                            INSERT INTO users (email, name, role, emp_id, tl_name, tl_id, password_hash)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (email) DO UPDATE SET name=EXCLUDED.name, role=EXCLUDED.role
                        """, (new_email.strip().lower(), new_name.strip(), new_role, "EBND" + str(datetime.now().microsecond)[:5], "Excitel Admin", "TL01", hash_password("Password123")))
                        conn.commit()
                        record_audit(user['email'], "CREATE_USER", new_email.strip().lower(), f"Created role {new_role}")
                        st.success(f"User {new_name} added successfully!")
                        st.rerun()
                    finally:
                        release_connection(conn)

        st.markdown("<br>", unsafe_allow_html=True)
        
        conn = get_connection()
        try:
            users_list = pd.read_sql("SELECT name, email, role FROM users ORDER BY name ASC", conn)
        finally:
            release_connection(conn)
            
        for _, u_row in users_list.iterrows():
            row_c1, row_c2, row_c3, row_c4 = st.columns([2.5, 3, 2, 1.8])
            with row_c1:
                st.write(f"**{u_row['name']}**")
            with row_c2:
                st.write(u_row['email'])
            with row_c3:
                role_bg = "#FEE2E2" if u_row['role'] == "Admin" else ("#FEF3C7" if u_row['role'] == "TL" else "#E0F2FE")
                role_color = "#991B1B" if u_row['role'] == "Admin" else ("#92400E" if u_row['role'] == "TL" else "#0369A1")
                st.markdown(f"<span style='background:{role_bg}; color:{role_color}; padding:4px 12px; border-radius:12px; font-weight:700; font-size:11px;'>{u_row['role'].upper()}</span>", unsafe_allow_html=True)
            with row_c4:
                if st.button("🗑️ Remove", key=f"del_u_{u_row['email']}", use_container_width=True):
                    same_role_count = len(users_list[users_list['role'] == u_row['role']])
                    
                    if same_role_count <= 1:
                        st.error(f"❌ Role Lock: Cannot delete {u_row['name']}. They are the only remaining '{u_row['role']}' in the system. Assign/transfer this role first.")
                    elif u_row['email'] == user['email']:
                        st.error("❌ Action Blocked: You cannot delete your own active Admin account. Transfer administrative rights to another user first.")
                    else:
                        conn = get_connection()
                        try:
                            cur = conn.cursor()
                            cur.execute("DELETE FROM users WHERE email = %s", (u_row['email'],))
                            conn.commit()
                            record_audit(user['email'], "DELETE_USER", u_row['email'], f"Deleted {u_row['role']} profile")
                            st.rerun()
                        finally:
                            release_connection(conn)
            st.markdown("<hr style='border:none; border-top:1px solid #F0F2F9; margin:8px 0;'>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

# ==================== FOOTER ====================
st.markdown("""
    <div style="text-align:center; padding:20px 0; color:#605E5C; font-size:12px; font-weight:600;">
        © Excitel Broadband Private Limited — Enterprise Overtime Tracking Protocol
    </div>
""", unsafe_allow_html=True)
