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
import json
import io
from fpdf import FPDF
from typing import Optional, List, Dict

# ==================== CONFIGURATION & CONSTANTS ====================
VERSION = "1.0.0 - Call Center Edition"
APP_NAME = "Excitel OT Portal - Call Center"
SALT_SECRET = "Excitel_Secure_Salt_2026"
OT_RATE_PER_HOUR = 100.0  # Fixed rate for call center

# Performance settings
CACHE_TTL = 300  # 5 minutes
MAX_CONNECTIONS = 20

# ==================== AUTOMATIC THEME CONFIG ====================
os.makedirs(".streamlit", exist_ok=True)
config_path = ".streamlit/config.toml"
if not os.path.exists(config_path):
    with open(config_path, "w") as f:
        f.write("""
[theme]
base="light"
primaryColor="#FF6B00"
backgroundColor="#F4F7FC"
secondaryBackgroundColor="#FFFFFF"
textColor="#1E3A8A"
font="sans serif"

[server]
maxUploadSize = 50
enableXsrfProtection = true
enableCORS = false
""")

# ==================== DATABASE CONNECTION POOLING ====================
@st.cache_resource
def get_db_pool():
    """Connection pool optimized for call center operations"""
    try:
        db_url = st.secrets["database"]["url"]
        return psycopg2.pool.SimpleConnectionPool(
            minconn=2,
            maxconn=MAX_CONNECTIONS,
            dsn=db_url,
            connect_timeout=10
        )
    except Exception as e:
        st.error(f"Database connection failed: {str(e)}")
        return None

def get_connection():
    """Get connection with retry logic"""
    pool = get_db_pool()
    if pool:
        try:
            return pool.getconn()
        except:
            get_db_pool.clear()
            return get_db_pool().getconn()
    return None

def release_connection(conn):
    """Safely release connection back to pool"""
    if conn and get_db_pool():
        try:
            get_db_pool().putconn(conn)
        except:
            pass

# ==================== CACHING UTILITIES ====================
@st.cache_data(ttl=CACHE_TTL)
def get_cached_data(query: str, params: tuple = None):
    """Cache frequently accessed data"""
    conn = get_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor()
        cursor.execute(query, params or ())
        return cursor.fetchall()
    except Exception as e:
        print(f"Cache error: {e}")
        return None
    finally:
        release_connection(conn)

# ==================== CRYPTOGRAPHIC UTILITIES ====================
def hash_password(password: str) -> str:
    """Hash password with PBKDF2-SHA256"""
    return hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        SALT_SECRET.encode('utf-8'),
        100000
    ).hex()

def generate_otp(length: int = 6) -> str:
    """Generate secure OTP"""
    return ''.join([str(random.randint(0, 9)) for _ in range(length)])

# ==================== DATABASE SCHEMA & INITIALIZATION ====================
def init_db():
    """Initialize database with SIMPLIFIED call center schema"""
    conn = get_connection()
    if not conn:
        return
    
    try:
        cursor = conn.cursor()
        
        # Users table (simplified)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                email TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('Employee', 'TL', 'Admin')),
                emp_id TEXT UNIQUE,
                tl_name TEXT,
                tl_id TEXT,
                location TEXT,
                password_hash TEXT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
        ''')
        
        # SIMPLIFIED OT logs - Single level approval only
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ot_logs (
                id SERIAL PRIMARY KEY,
                date DATE NOT NULL,
                employee_email TEXT REFERENCES users(email),
                employee_name TEXT NOT NULL,
                emp_id TEXT NOT NULL,
                shift_start TIME,
                shift_end TIME,
                ot_start TIME,
                ot_end TIME,
                ot_hours REAL NOT NULL,
                task_type TEXT,
                task_description TEXT,
                status TEXT DEFAULT 'Pending' CHECK (status IN ('Pending', 'Approved', 'Rejected', 'Paid')),
                tl_name TEXT,
                actual_output REAL,
                standard_rate REAL DEFAULT 100.0,
                expected_output REAL,
                productivity REAL,
                verified_hours REAL,
                amount REAL,
                approved_by TEXT,
                approved_at TIMESTAMP,
                rejection_reason TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Audit logs (simplified)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_logs (
                id SERIAL PRIMARY KEY,
                performer_email TEXT,
                performer_name TEXT,
                action TEXT NOT NULL,
                target_type TEXT,
                target_id INTEGER,
                target_details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Password resets
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS password_resets (
                id SERIAL PRIMARY KEY,
                email TEXT NOT NULL,
                otp_code TEXT NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                attempts INTEGER DEFAULT 0,
                is_used BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create performance indexes
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_ot_logs_employee ON ot_logs(employee_email)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_ot_logs_status ON ot_logs(status)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_ot_logs_date ON ot_logs(date)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp)
        ''')
        
        # Insert default users (Call Center optimized)
        default_pass_hash = hash_password("Password123")
        default_users = [
            ("admin@dl.excitel.in", "Excitel Admin", "Admin", "EBND00001", None, None, "Gurugram", default_pass_hash, True),
            ("ritu.mandal@dl.excitel.in", "Ritu Mandal", "TL", "EBND04635", "Nandini Puri", "TL01", "Gurugram", default_pass_hash, True),
            ("jamal.khan@dl.excitel.in", "Jamal Khan", "TL", "EBND04471", "Nandini Puri", "TL01", "Gurugram", default_pass_hash, True),
            ("abhishek.pandey@dl.excitel.in", "Abhishek Pandey", "TL", "EBND04472", "Nandini Puri", "TL01", "Gurugram", default_pass_hash, True),
            ("nandini.puri@dl.excitel.in", "Nandini Puri", "TL", "TL01", "Excitel Admin", "ADMIN", "Gurugram", default_pass_hash, True),
            ("basu.porwal@dl.excitel.in", "Basu Porwal", "Employee", "EBND04475", "Ritu Mandal", "EBND04635", "Gurugram", default_pass_hash, True),
            ("employee1@dl.excitel.in", "Employee One", "Employee", "EBND04476", "Ritu Mandal", "EBND04635", "Gurugram", default_pass_hash, True),
            ("employee2@dl.excitel.in", "Employee Two", "Employee", "EBND04477", "Jamal Khan", "EBND04471", "Gurugram", default_pass_hash, True)
        ]
        
        cursor.executemany("""
            INSERT INTO users (email, name, role, emp_id, tl_name, tl_id, location, password_hash, is_active) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) 
            ON CONFLICT (email) DO UPDATE SET
                name = EXCLUDED.name,
                role = EXCLUDED.role,
                location = EXCLUDED.location,
                is_active = EXCLUDED.is_active
        """, default_users)
        
        conn.commit()
        print("Database initialized successfully - Call Center Edition")
        
    except Exception as e:
        print(f"Database initialization error: {e}")
        if conn:
            conn.rollback()
    finally:
        release_connection(conn)

# Initialize DB on startup
init_db()

# ==================== AUDIT LOGGING ====================
def record_audit(performer_email: str, performer_name: str, action: str, 
                 target_type: str = None, target_id: int = None, 
                 target_details: str = None):
    """Simplified audit logging"""
    conn = get_connection()
    if not conn:
        return
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO audit_logs (performer_email, performer_name, action, target_type, target_id, target_details, timestamp)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (performer_email, performer_name, action, target_type, target_id, target_details, datetime.now()))
        conn.commit()
    except Exception as e:
        print(f"Audit Log Error: {e}")
    finally:
        release_connection(conn)

# ==================== EMAIL SYSTEM (Optional) ====================
def send_email_notification(recipient_email: str, subject: str, body_html: str):
    """Send email notification (optional - works without SMTP)"""
    if "smtp" not in st.secrets:
        print(f"Email queued (no SMTP): {subject} to {recipient_email}")
        return
    
    try:
        smtp_server = st.secrets["smtp"]["server"]
        smtp_port = int(st.secrets["smtp"]["port"])
        sender_email = st.secrets["smtp"]["sender_email"]
        sender_password = st.secrets["smtp"]["sender_password"]
        
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"Excitel OT Portal <{sender_email}>"
        msg["To"] = recipient_email
        msg.attach(MIMEText(body_html, "html"))
        
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
        
        print(f"Email sent: {subject}")
    except Exception as e:
        print(f"Email error: {e}")

def send_ot_approval_email(employee_email: str, employee_name: str, 
                          ot_details: Dict, approved: bool, approver_name: str):
    """Send OT approval/rejection email"""
    if approved:
        subject = f"✅ OT Approved - {ot_details.get('date', '')}"
        status = "approved"
        color = "#10B981"
    else:
        subject = f"❌ OT Rejected - {ot_details.get('date', '')}"
        status = "rejected"
        color = "#EF4444"
    
    body = f"""
    <html>
        <body style="font-family: Arial, sans-serif; background-color: #F4F7FC; padding: 20px;">
            <div style="max-width: 500px; margin: 0 auto; background: #FFFFFF; border-radius: 12px; border-top: 5px solid {color}; padding: 30px;">
                <h2 style="color: #1E3A8A; margin: 0 0 10px 0;">OT {status.title()}</h2>
                <p style="color: #64748B; font-size: 14px;">Dear {employee_name},</p>
                
                <div style="background: #F8FAFC; border-radius: 8px; padding: 20px; margin: 20px 0;">
                    <table style="width: 100%;">
                        <tr><td style="color: #64748B; font-size: 13px;">Date:</td><td style="color: #1E3A8A; font-weight: 600;">{ot_details.get('date', 'N/A')}</td></tr>
                        <tr><td style="color: #64748B; font-size: 13px;">OT Hours:</td><td style="color: #1E3A8A; font-weight: 600;">{ot_details.get('ot_hours', 0)} hrs</td></tr>
                        <tr><td style="color: #64748B; font-size: 13px;">Task:</td><td style="color: #1E3A8A;">{ot_details.get('task_type', 'N/A')}</td></tr>
                        <tr><td style="color: #64748B; font-size: 13px;">Amount:</td><td style="color: #10B981; font-weight: 700;">₹{ot_details.get('amount', 0):.2f}</td></tr>
                    </table>
                </div>
                
                {f"<p style='color: #EF4444; background: #FEF2F2; padding: 12px; border-radius: 6px;'><b>Rejection Reason:</b> {ot_details.get('rejection_reason', '')}</p>" if not approved and ot_details.get('rejection_reason') else ''}
                
                <p style="color: #64748B; font-size: 13px;">Approved by: <b>{approver_name}</b></p>
                
                <div style="border-top: 2px solid {color}; padding-top: 15px; margin-top: 20px;">
                    <p style="margin: 0; font-size: 12px; color: #94A3B8;">Excitel OT Portal | Automated Notification</p>
                </div>
            </div>
        </body>
    </html>
    """
    
    send_email_notification(employee_email, subject, body)

# ==================== PDF GENERATION ====================
class OTPDF(FPDF):
    """Custom PDF with Excitel branding"""
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.set_text_color(255, 107, 0)
        self.cell(0, 10, 'Excitel OT Portal - Call Center', 0, 1, 'C')
        self.ln(5)
    
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

def generate_ot_pdf(ot_data: List[Dict], report_type: str = 'summary') -> bytes:
    """Generate PDF report"""
    pdf = OTPDF()
    pdf.add_page()
    pdf.set_font('Arial', '', 10)
    
    # Title
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, f'OT Report - {report_type.title()}', 0, 1, 'C')
    pdf.ln(5)
    
    # Table header
    pdf.set_font('Arial', 'B', 10)
    pdf.set_fill_color(255, 107, 0)
    pdf.set_text_color(255, 255, 255)
    
    columns = ['Date', 'Employee', 'Emp ID', 'OT Hours', 'Task', 'Status', 'Amount']
    col_widths = [25, 40, 20, 20, 40, 25, 20]
    
    for i, col in enumerate(columns):
        pdf.cell(col_widths[i], 10, col, 1, 0, 'C', True)
    pdf.ln()
    
    # Table rows
    pdf.set_text_color(0, 0, 0)
    pdf.set_fill_color(245, 245, 245)
    
    for i, row in enumerate(ot_data):
        pdf.set_fill_color(255 if i % 2 == 0 else 245)
        pdf.set_font('Arial', '', 9)
        
        row_data = [
            str(row.get('date', ''))[:10],
            row.get('employee_name', '')[:20],
            row.get('emp_id', ''),
            f"{row.get('ot_hours', 0):.2f}",
            row.get('task_type', '')[:20],
            row.get('status', ''),
            f"₹{row.get('amount', 0):.2f}"
        ]
        
        for j, cell_data in enumerate(row_data):
            pdf.cell(col_widths[j], 8, cell_data, 1, 0, 'L', i % 2 == 0)
        pdf.ln()
    
    # Summary
    pdf.ln(10)
    pdf.set_font('Arial', 'B', 11)
    total_hours = sum(row.get('ot_hours', 0) for row in ot_data)
    total_amount = sum(row.get('amount', 0) for row in ot_data)
    pdf.cell(0, 10, f'Total Hours: {total_hours:.2f} | Total Amount: ₹{total_amount:.2f}', 0, 1, 'R')
    
    return pdf.output(dest='S').encode('latin-1')

# ==================== DATA EXPORT ====================
def export_to_excel(df: pd.DataFrame, sheet_name: str = 'OT Data') -> bytes:
    """Export to Excel"""
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
        
        workbook = writer.book
        worksheet = writer.sheets[sheet_name]
        
        # Formats
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#FF6B00',
            'font_color': 'white',
            'border': 1,
            'align': 'center'
        })
        
        money_format = workbook.add_format({'num_format': '₹#,##0.00'})
        hour_format = workbook.add_format({'num_format': '0.00'})
        
        # Apply formats
        for col_num, col_name in enumerate(df.columns):
            worksheet.write(0, col_num, col_name, header_format)
            
            if 'amount' in col_name.lower() or 'rate' in col_name.lower():
                for row_num in range(1, len(df) + 1):
                    worksheet.set_column(row_num, col_num, None, money_format)
            elif 'hours' in col_name.lower():
                for row_num in range(1, len(df) + 1):
                    worksheet.set_column(row_num, col_num, None, hour_format)
        
        # Auto-fit
        for i, col in enumerate(df.columns):
            max_length = max(df[col].astype(str).map(len).max(), len(col))
            worksheet.set_column(i, i, max_length + 2)
    
    return output.getvalue()

# ==================== ANALYTICS ====================
def get_dashboard_analytics(user_email: str = None, role: str = None, 
                           date_range: tuple = None) -> Dict:
    """Get dashboard analytics"""
    conn = get_connection()
    if not conn:
        return {}
    
    try:
        cursor = conn.cursor()
        
        # Build query
        base_query = "SELECT * FROM ot_logs WHERE 1=1"
        params = []
        
        if date_range and len(date_range) == 2:
            base_query += " AND date BETWEEN %s AND %s"
            params.extend(date_range)
        
        if role == 'Employee' and user_email:
            base_query += " AND employee_email = %s"
            params.append(user_email)
        elif role == 'TL':
            # Get TL's team
            cursor.execute("SELECT emp_id FROM users WHERE tl_id = (SELECT tl_id FROM users WHERE email = %s)", (user_email,))
            team_ids = [row[0] for row in cursor.fetchall()]
            if team_ids:
                base_query += f" AND emp_id IN ({','.join(['%s'] * len(team_ids))})"
                params.extend(team_ids)
        
        cursor.execute(base_query, params)
        columns = [desc[0] for desc in cursor.description]
        ot_data = [dict(zip(columns, row)) for row in cursor.fetchall()]
        df = pd.DataFrame(ot_data)
        
        if df.empty:
            return {'df': df, 'metrics': {}, 'charts': {}}
        
        # Metrics
        metrics = {
            'total_hours': df['ot_hours'].sum(),
            'total_amount': df['amount'].sum(),
            'total_records': len(df),
            'avg_hours': df['ot_hours'].mean(),
            'approval_rate': (df['status'] == 'Approved').sum() / len(df) * 100 if len(df) > 0 else 0,
            'pending_count': (df['status'] == 'Pending').sum()
        }
        
        # Charts
        charts = {
            'daily_trend': df.groupby('date')['ot_hours'].sum().reset_index(),
            'status_distribution': df['status'].value_counts().reset_index(),
            'employee_wise': df.groupby('employee_name')['ot_hours'].sum().nlargest(10).reset_index()
        }
        
        return {'df': df, 'metrics': metrics, 'charts': charts}
        
    except Exception as e:
        print(f"Analytics Error: {e}")
        return {'df': pd.DataFrame(), 'metrics': {}, 'charts': {}}
    finally:
        release_connection(conn)

# ==================== SESSION STATE ====================
def initialize_session_state():
    """Initialize session state"""
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    if 'user_email' not in st.session_state:
        st.session_state.user_email = None
    if 'user_name' not in st.session_state:
        st.session_state.user_name = None
    if 'user_role' not in st.session_state:
        st.session_state.user_role = None
    if 'user_emp_id' not in st.session_state:
        st.session_state.user_emp_id = None
    if 'page' not in st.session_state:
        st.session_state.page = 'login'

def login_user(email: str, password: str) -> tuple:
    """Authenticate user"""
    conn = get_connection()
    if not conn:
        return False, "Database connection failed"
    
    try:
        cursor = conn.cursor()
        password_hash = hash_password(password)
        
        cursor.execute("""
            SELECT email, name, role, emp_id, tl_name, tl_id, location, is_active
            FROM users
            WHERE email = %s AND password_hash = %s
        """, (email, password_hash))
        
        user = cursor.fetchone()
        
        if user:
            if not user[7]:  # is_active
                return False, "Account deactivated. Contact admin."
            
            st.session_state.logged_in = True
            st.session_state.user_email = user[0]
            st.session_state.user_name = user[1]
            st.session_state.user_role = user[2]
            st.session_state.user_emp_id = user[3]
            st.session_state.page = 'dashboard'
            
            cursor.execute("UPDATE users SET last_login = %s WHERE email = %s", (datetime.now(), email))
            conn.commit()
            
            record_audit(email, user[1], 'LOGIN', 'user', None, f"Role: {user[2]}")
            
            return True, "Login successful"
        else:
            return False, "Invalid email or password"
            
    except Exception as e:
        print(f"Login Error: {e}")
        return False, f"Login error: {str(e)}"
    finally:
        release_connection(conn)

def logout_user():
    """Logout user"""
    if st.session_state.user_email:
        record_audit(st.session_state.user_email, st.session_state.user_name, 'LOGOUT', 'user', None, None)
    
    for key in list(st.session_state.keys()):
        if key.startswith('user_') or key == 'logged_in' or key == 'page':
            del st.session_state[key]
    
    st.session_state.logged_in = False
    st.session_state.page = 'login'

# ==================== UI COMPONENTS ====================
def render_sidebar():
    """Render sidebar navigation"""
    with st.sidebar:
        st.markdown(f"""
            <div style="text-align: center; padding: 20px 0; border-bottom: 2px solid #E2E8F0;">
                <h2 style="color: #FF6B00; margin: 0;">Excitel OT Portal</h2>
                <p style="color: #64748B; font-size: 12px; margin: 5px 0;">{st.session_state.get('user_name', 'Guest')}</p>
                <p style="color: #94A3B8; font-size: 11px; margin: 0;">{st.session_state.get('user_role', '')} | {st.session_state.get('user_emp_id', '')}</p>
            </div>
        """, unsafe_allow_html=True)
        
        st.markdown("### Navigation")
        
        pages = {
            'dashboard': ('📊 Dashboard', ['Employee', 'TL', 'Admin']),
            'submit_ot': ('➕ Submit OT', ['Employee']),
            'my_ot': ('📋 My OT Records', ['Employee']),
            'approve_ot': ('✅ Approve OT', ['TL', 'Admin']),
            'reports': ('📈 Reports', ['TL', 'Admin']),
            'exports': ('📥 Exports', ['TL', 'Admin']),
            'users': ('👥 Users', ['Admin']),
            'audit': ('🔍 Audit', ['Admin'])
        }
        
        for page_key, (label, allowed_roles) in pages.items():
            if st.session_state.user_role in allowed_roles:
                if st.button(label, key=page_key, use_container_width=True, 
                            type='primary' if st.session_state.page == page_key else 'secondary'):
                    st.session_state.page = page_key
                    st.rerun()
        
        st.markdown("---")
        
        if st.button("🚪 Logout", use_container_width=True, type='secondary'):
            logout_user()
            st.rerun()
        
        st.markdown("---")
        st.markdown(f"""
            <div style="text-align: center; color: #94A3B8; font-size: 10px;">
                Version {VERSION}<br>
                © 2026 Excitel Call Center
            </div>
        """, unsafe_allow_html=True)

# ==================== MAIN APP ====================
def main():
    """Main application"""
    st.set_page_config(
        page_title="Excitel OT Portal - Call Center",
        page_icon="⏰",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    initialize_session_state()
    
    # Custom CSS
    st.markdown("""
        <style>
            .main-header {
                background: linear-gradient(135deg, #FF6B00 0%, #FF8C42 100%);
                padding: 20px;
                border-radius: 12px;
                margin-bottom: 20px;
                color: white;
            }
            .metric-card {
                background: white;
                padding: 20px;
                border-radius: 12px;
                box-shadow: 0 4px 20px rgba(0,0,0,0.08);
                border-left: 4px solid #FF6B00;
            }
            .stButton > button {
                border-radius: 8px;
                font-weight: 600;
            }
        </style>
    """, unsafe_allow_html=True)
    
    # Render based on page
    if not st.session_state.logged_in:
        render_login_page()
    else:
        render_sidebar()
        
        page = st.session_state.page
        
        if page == 'dashboard':
            render_dashboard()
        elif page == 'submit_ot':
            render_submit_ot()
        elif page == 'my_ot':
            render_my_ot()
        elif page == 'approve_ot':
            render_approve_ot()
        elif page == 'reports':
            render_reports()
        elif page == 'exports':
            render_exports()
        elif page == 'users':
            render_user_management()
        elif page == 'audit':
            render_audit_logs()

def render_login_page():
    """Render login page"""
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.markdown("""
            <div class="main-header">
                <h1 style="margin: 0;">Welcome to Excitel OT Portal</h1>
                <p style="margin: 10px 0 0 0; opacity: 0.9;">Call Center Overtime Tracking</p>
            </div>
        """, unsafe_allow_html=True)
        
        st.markdown("### Features")
        st.markdown("""
            - ✅ Single-level approval (TL/Admin)
            - 📧 Email notifications
            - 📊 Real-time analytics
            - 📥 Excel/PDF export
            - 🔍 Audit trails
            - ₹100/hour fixed rate
        """)
    
    with col2:
        st.markdown("### Login")
        
        email = st.text_input("Email Address", placeholder="your.email@dl.excitel.in")
        password = st.text_input("Password", type="password", placeholder="Enter password")
        
        if st.button("Sign In", type="primary", use_container_width=True):
            if email and password:
                success, message = login_user(email, password)
                if success:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)
            else:
                st.error("Please enter both email and password")
        
        st.markdown("---")
        st.markdown("#### Demo Credentials")
        st.code("TL: ritu.mandal@dl.excitel.in\nPassword: Password123", language="text")

def render_dashboard():
    """Render dashboard"""
    st.markdown(f"""
        <div class="main-header">
            <h1 style="margin: 0;">📊 Dashboard</h1>
            <p style="margin: 10px 0 0 0; opacity: 0.9;">Welcome back, {st.session_state.user_name}!</p>
        </div>
    """, unsafe_allow_html=True)
    
    # Get analytics
    analytics = get_dashboard_analytics(
        user_email=st.session_state.user_email,
        role=st.session_state.user_role
    )
    
    df = analytics.get('df', pd.DataFrame())
    metrics = analytics.get('metrics', {})
    
    if not df.empty:
        # Key metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown(f"""
                <div class="metric-card">
                    <p style="margin: 0; color: #64748B; font-size: 12px;">Total OT Hours</p>
                    <h2 style="margin: 10px 0 0 0; color: #FF6B00;">{metrics.get('total_hours', 0):.2f}</h2>
                </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown(f"""
                <div class="metric-card">
                    <p style="margin: 0; color: #64748B; font-size: 12px;">Total Amount</p>
                    <h2 style="margin: 10px 0 0 0; color: #10B981;">₹{metrics.get('total_amount', 0):,.2f}</h2>
                </div>
            """, unsafe_allow_html=True)
        
        with col3:
            st.markdown(f"""
                <div class="metric-card">
                    <p style="margin: 0; color: #64748B; font-size: 12px;">Total Records</p>
                    <h2 style="margin: 10px 0 0 0; color: #3B82F6;">{metrics.get('total_records', 0)}</h2>
                </div>
            """, unsafe_allow_html=True)
        
        with col4:
            st.markdown(f"""
                <div class="metric-card">
                    <p style="margin: 0; color: #64748B; font-size: 12px;">Pending Approval</p>
                    <h2 style="margin: 10px 0 0 0; color: #F59E0B;">{metrics.get('pending_count', 0)}</h2>
                </div>
            """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        # Charts
        charts = analytics.get('charts', {})
        
        col1, col2 = st.columns(2)
        
        with col1:
            if 'daily_trend' in charts and not charts['daily_trend'].empty:
                st.subheader("📈 Daily OT Trend")
                chart = alt.Chart(charts['daily_trend']).mark_line(point=True).encode(
                    x='date:T',
                    y='ot_hours:Q',
                    tooltip=['date', 'ot_hours']
                ).properties(height=300)
                st.altair_chart(chart, use_container_width=True)
        
        with col2:
            if 'status_distribution' in charts and not charts['status_distribution'].empty:
                st.subheader("📊 Status Distribution")
                chart = alt.Chart(charts['status_distribution']).mark_bar().encode(
                    x='status:N',
                    y='count:Q',
                    color='status:N',
                    tooltip=['status', 'count']
                ).properties(height=300)
                st.altair_chart(chart, use_container_width=True)
        
        # Recent records
        st.subheader("📋 Recent OT Records")
        st.dataframe(df.head(10), use_container_width=True, hide_index=True)
    
    else:
        st.info("No OT records found. Start by submitting OT records!")

def render_submit_ot():
    """Render OT submission - SIMPLIFIED for call center"""
    st.markdown(f"""
        <div class="main-header">
            <h1 style="margin: 0;">➕ Submit OT</h1>
            <p style="margin: 10px 0 0 0; opacity: 0.9;">Record your overtime (₹100/hour)</p>
        </div>
    """, unsafe_allow_html=True)
    
    with st.form("submit_ot_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            ot_date = st.date_input("Date", value=date.today())
            shift_start = st.time_input("Shift Start")
            shift_end = st.time_input("Shift End")
            ot_start = st.time_input("OT Start")
            ot_end = st.time_input("OT End")
        
        with col2:
            task_type = st.selectbox("Task Type", [
                "Customer Escalation", "Network Issue", "Server Maintenance",
                "System Upgrade", "Emergency Fix", "High Call Volume", "Other"
            ])
            task_description = st.text_area("Task Description", placeholder="Brief description")
            actual_output = st.number_input("Actual Output (calls/tickets)", min_value=0.0, step=1.0)
        
        submitted = st.form_submit_button("Submit OT", type="primary", use_container_width=True)
        
        if submitted:
            if not all([ot_date, shift_start, shift_end, ot_start, ot_end]):
                st.error("Please fill all fields")
            else:
                # Calculate OT hours
                ot_start_dt = datetime.combine(ot_date, ot_start)
                ot_end_dt = datetime.combine(ot_date, ot_end)
                ot_hours = (ot_end_dt - ot_start_dt).seconds / 3600
                
                # Fixed rate for call center
                standard_rate = OT_RATE_PER_HOUR
                expected_output = ot_hours * standard_rate
                productivity = (actual_output / expected_output * 100) if expected_output > 0 else 0
                amount = ot_hours * standard_rate
                
                conn = get_connection()
                if conn:
                    try:
                        cursor = conn.cursor()
                        cursor.execute("""
                            INSERT INTO ot_logs (
                                date, employee_email, employee_name, emp_id,
                                shift_start, shift_end, ot_start, ot_end, ot_hours,
                                task_type, task_description, status, tl_name,
                                actual_output, standard_rate, expected_output, productivity,
                                verified_hours, amount, created_at, updated_at
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            RETURNING id
                        """, (
                            ot_date, st.session_state.user_email, st.session_state.user_name,
                            st.session_state.user_emp_id,
                            shift_start, shift_end, ot_start, ot_end, ot_hours,
                            task_type, task_description, 'Pending', st.session_state.get('user_tl_name', ''),
                            actual_output, standard_rate, expected_output, productivity,
                            ot_hours, amount, datetime.now(), datetime.now()
                        ))
                        
                        ot_id = cursor.fetchone()[0]
                        conn.commit()
                        
                        record_audit(st.session_state.user_email, st.session_state.user_name, 
                                   'SUBMIT_OT', 'ot_logs', ot_id, f"Date: {ot_date}, Hours: {ot_hours}")
                        
                        # Notify TL (optional email)
                        conn2 = get_connection()
                        if conn2:
                            cursor2 = conn2.cursor()
                            cursor2.execute("SELECT email, name FROM users WHERE emp_id = (SELECT tl_id FROM users WHERE email = %s)", 
                                          (st.session_state.user_email,))
                            tl = cursor2.fetchone()
                            if tl:
                                ot_details = {
                                    'employee_name': st.session_state.user_name,
                                    'emp_id': st.session_state.user_emp_id,
                                    'date': str(ot_date),
                                    'ot_hours': ot_hours,
                                    'task_type': task_type,
                                    'amount': amount
                                }
                                send_ot_approval_email(tl[0], tl[1], ot_details, True, "System")  # Just notification
                            
                            release_connection(conn2)
                        
                        st.success("OT submitted successfully!")
                        st.session_state.page = 'my_ot'
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"Error: {str(e)}")
                    finally:
                        release_connection(conn)

def render_my_ot():
    """Render user's OT records"""
    st.markdown(f"""
        <div class="main-header">
            <h1 style="margin: 0;">📋 My OT Records</h1>
            <p style="margin: 10px 0 0 0; opacity: 0.9;">View your OT submissions</p>
        </div>
    """, unsafe_allow_html=True)
    
    # Filters
    col1, col2 = st.columns(2)
    
    with col1:
        status_filter = st.selectbox("Status", ["All", "Pending", "Approved", "Rejected", "Paid"])
    
    with col2:
        date_from = st.date_input("From", value=date.today() - timedelta(days=30))
        date_to = st.date_input("To", value=date.today())
    
    # Fetch records
    conn = get_connection()
    if conn:
        try:
            cursor = conn.cursor()
            
            query = """
                SELECT * FROM ot_logs 
                WHERE employee_email = %s AND date BETWEEN %s AND %s
            """
            params = [st.session_state.user_email, date_from, date_to]
            
            if status_filter != "All":
                query += " AND status = %s"
                params.append(status_filter)
            
            query += " ORDER BY date DESC"
            
            cursor.execute(query, params)
            columns = [desc[0] for desc in cursor.description]
            records = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            if records:
                df = pd.DataFrame(records)
                
                # Display key info
                total_hours = df['ot_hours'].sum()
                total_amount = df['amount'].sum()
                approved_count = (df['status'] == 'Approved').sum()
                
                col1, col2, col3 = st.columns(3)
                col1.metric("Total Hours", f"{total_hours:.2f}")
                col2.metric("Total Amount", f"₹{total_amount:,.2f}")
                col3.metric("Approved", f"{approved_count}")
                
                st.markdown("---")
                st.dataframe(df, use_container_width=True, hide_index=True)
                
                # Export
                if st.button("📥 Export to Excel", use_container_width=True):
                    excel_data = export_to_excel(df, "My_OT")
                    st.download_button(
                        label="⬇️ Download Excel",
                        data=excel_data,
                        file_name=f"my_ot_{st.session_state.user_emp_id}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
            else:
                st.info("No OT records found")
                
        except Exception as e:
            st.error(f"Error: {str(e)}")
        finally:
            release_connection(conn)

def render_approve_ot():
    """Render OT approval - SINGLE LEVEL (TL/Admin only)"""
    st.markdown(f"""
        <div class="main-header">
            <h1 style="margin: 0;">✅ Approve OT</h1>
            <p style="margin: 10px 0 0 0; opacity: 0.9;">Quick approval for call center OT</p>
        </div>
    """, unsafe_allow_html=True)
    
    # Get pending approvals
    conn = get_connection()
    if conn:
        try:
            cursor = conn.cursor()
            
            if st.session_state.user_role == 'TL':
                # Get TL's team
                cursor.execute("SELECT emp_id FROM users WHERE tl_id = (SELECT tl_id FROM users WHERE email = %s)", 
                             (st.session_state.user_email,))
                team_ids = [row[0] for row in cursor.fetchall()]
                
                if team_ids:
                    query = f"""
                        SELECT * FROM ot_logs 
                        WHERE emp_id IN ({','.join(['%s'] * len(team_ids))})
                        AND status = 'Pending'
                        ORDER BY date DESC
                    """
                    cursor.execute(query, team_ids)
                else:
                    st.info("No team members")
                    return
                    
            elif st.session_state.user_role == 'Admin':
                query = """
                    SELECT * FROM ot_logs 
                    WHERE status = 'Pending'
                    ORDER BY date DESC
                """
                cursor.execute(query)
            else:
                st.info("Access denied")
                return
            
            columns = [desc[0] for desc in cursor.description]
            pending_ot = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            if pending_ot:
                st.subheader(f"Pending Approvals ({len(pending_ot)})")
                
                for ot in pending_ot:
                    with st.expander(f"{ot['employee_name']} ({ot['emp_id']}) - {ot['date']} - {ot['ot_hours']} hrs - ₹{ot['amount']:.2f}"):
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.markdown(f"""
                                **Shift:** {ot['shift_start']} - {ot['shift_end']}<br>
                                **OT:** {ot['ot_start']} - {ot['ot_end']}<br>
                                **Task:** {ot['task_type']}
                            """, unsafe_allow_html=True)
                        
                        with col2:
                            st.markdown(f"""
                                **Productivity:** {ot.get('productivity', 0):.1f}%<br>
                                **Actual Output:** {ot.get('actual_output', 0)}<br>
                                **Amount:** ₹{ot.get('amount', 0):.2f}
                            """, unsafe_allow_html=True)
                        
                        # Quick approval
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            verified_hours = st.number_input("Verified Hours", 
                                                           value=ot['ot_hours'], 
                                                           min_value=0.0,
                                                           max_value=ot['ot_hours'],
                                                           key=f"verified_{ot['id']}")
                        
                        with col2:
                            if st.button("✅ Approve", type="primary", key=f"approve_{ot['id']}", use_container_width=True):
                                update_ot_status(ot['id'], verified_hours, 'approve')
                        
                        # Rejection
                        rejection_reason = st.text_input("Rejection Reason (if rejecting)", 
                                                       key=f"reject_reason_{ot['id']}")
                        if st.button("❌ Reject", type="secondary", key=f"reject_{ot['id']}", use_container_width=True):
                            if rejection_reason:
                                update_ot_status(ot['id'], 0, 'reject', rejection_reason)
                            else:
                                st.error("Please provide rejection reason")
            
            else:
                st.success("🎉 No pending approvals! All caught up.")
                
        except Exception as e:
            st.error(f"Error: {str(e)}")
        finally:
            release_connection(conn)

def update_ot_status(ot_id: int, verified_hours: float, action: str, rejection_reason: str = None):
    """Update OT status - SINGLE LEVEL APPROVAL"""
    conn = get_connection()
    if not conn:
        return
    
    try:
        cursor = conn.cursor()
        
        # Get OT record
        cursor.execute("SELECT * FROM ot_logs WHERE id = %s", (ot_id,))
        columns = [desc[0] for desc in cursor.description]
        ot = dict(zip(columns, cursor.fetchone()))
        
        if action == 'approve':
            new_status = 'Approved'
            new_amount = verified_hours * OT_RATE_PER_HOUR
            
            cursor.execute("""
                UPDATE ot_logs SET 
                    status = %s,
                    verified_hours = %s,
                    amount = %s,
                    approved_by = %s,
                    approved_at = %s,
                    updated_at = %s
                WHERE id = %s
            """, (new_status, verified_hours, new_amount, st.session_state.user_name, datetime.now(), datetime.now(), ot_id))
            
            # Send approval email
            ot_details = {
                'employee_name': ot['employee_name'],
                'emp_id': ot['emp_id'],
                'date': str(ot['date']),
                'ot_hours': verified_hours,
                'task_type': ot['task_type'],
                'amount': new_amount
            }
            send_ot_approval_email(ot['employee_email'], ot['employee_name'], ot_details, True, st.session_state.user_name)
            
        elif action == 'reject':
            new_status = 'Rejected'
            
            cursor.execute("""
                UPDATE ot_logs SET 
                    status = %s,
                    rejection_reason = %s,
                    updated_at = %s
                WHERE id = %s
            """, (new_status, rejection_reason, datetime.now(), ot_id))
            
            # Send rejection email
            ot_details = {
                'employee_name': ot['employee_name'],
                'emp_id': ot['emp_id'],
                'date': str(ot['date']),
                'ot_hours': ot['ot_hours'],
                'task_type': ot['task_type'],
                'amount': ot['amount'],
                'rejection_reason': rejection_reason
            }
            send_ot_approval_email(ot['employee_email'], ot['employee_name'], ot_details, False, st.session_state.user_name)
        
        conn.commit()
        
        record_audit(st.session_state.user_email, st.session_state.user_name,
                    f'{action.upper()}_OT', 'ot_logs', ot_id, 
                    f"Status: {new_status}")
        
        st.success(f"OT {action}ed successfully!")
        st.rerun()
        
    except Exception as e:
        st.error(f"Error: {str(e)}")
        conn.rollback()
    finally:
        release_connection(conn)

def render_reports():
    """Render reports - SIMPLIFIED"""
    st.markdown(f"""
        <div class="main-header">
            <h1 style="margin: 0;">📈 Reports</h1>
            <p style="margin: 10px 0 0 0; opacity: 0.9;">OT analytics for call center</p>
        </div>
    """, unsafe_allow_html=True)
    
    # Filters
    col1, col2 = st.columns(2)
    
    with col1:
        date_from = st.date_input("From", value=date.today() - timedelta(days=30))
    
    with col2:
        date_to = st.date_input("To", value=date.today())
    
    # Get analytics
    analytics = get_dashboard_analytics(
        date_range=(date_from, date_to)
    )
    
    df = analytics.get('df', pd.DataFrame())
    metrics = analytics.get('metrics', {})
    
    if not df.empty:
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Hours", f"{metrics.get('total_hours', 0):.2f}")
        col2.metric("Total Cost", f"₹{metrics.get('total_amount', 0):,.2f}")
        col3.metric("Records", f"{metrics.get('total_records', 0)}")
        
        st.markdown("---")
        
        # Charts
        charts = analytics.get('charts', {})
        
        col1, col2 = st.columns(2)
        
        with col1:
            if 'daily_trend' in charts and not charts['daily_trend'].empty:
                st.subheader("📊 Daily Trend")
                chart = alt.Chart(charts['daily_trend']).mark_area().encode(
                    x='date:T',
                    y='ot_hours:Q',
                    tooltip=['date', 'ot_hours']
                ).properties(height=350)
                st.altair_chart(chart, use_container_width=True)
        
        with col2:
            if 'employee_wise' in charts and not charts['employee_wise'].empty:
                st.subheader("👥 Top Employees")
                chart = alt.Chart(charts['employee_wise']).mark_bar().encode(
                    x='ot_hours:Q',
                    y=alt.Y('employee_name:N', sort='-x'),
                    color='ot_hours:Q',
                    tooltip=['employee_name', 'ot_hours']
                ).properties(height=350)
                st.altair_chart(chart, use_container_width=True)
        
        st.markdown("---")
        st.subheader("📋 Detailed Data")
        st.dataframe(df, use_container_width=True, hide_index=True)
    
    else:
        st.info("No data for selected period")

def render_exports():
    """Render exports - SIMPLIFIED"""
    st.markdown(f"""
        <div class="main-header">
            <h1 style="margin: 0;">📥 Exports</h1>
            <p style="margin: 10px 0 0 0; opacity: 0.9;">Export OT data</p>
        </div>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        export_format = st.selectbox("Format", ["Excel", "PDF"])
        date_from = st.date_input("From", value=date.today() - timedelta(days=30))
    
    with col2:
        date_to = st.date_input("To", value=date.today())
    
    # Fetch data
    conn = get_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM ot_logs 
                WHERE date BETWEEN %s AND %s
                ORDER BY date DESC
            """, (date_from, date_to))
            
            columns = [desc[0] for desc in cursor.description]
            records = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            if records:
                df = pd.DataFrame(records)
                st.info(f"Found {len(records)} records")
                
                if export_format == "Excel":
                    excel_data = export_to_excel(df, "OT_Export")
                    st.download_button(
                        label="⬇️ Download Excel",
                        data=excel_data,
                        file_name=f"ot_export_{date_from}_{date_to}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                
                elif export_format == "PDF":
                    pdf_data = generate_ot_pdf(records, "export")
                    st.download_button(
                        label="⬇️ Download PDF",
                        data=pdf_data,
                        file_name=f"ot_export_{date_from}_{date_to}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
            else:
                st.warning("No records found")
                
        except Exception as e:
            st.error(f"Error: {str(e)}")
        finally:
            release_connection(conn)

def render_user_management():
    """Render user management - Admin only"""
    st.markdown(f"""
        <div class="main-header">
            <h1 style="margin: 0;">👥 User Management</h1>
            <p style="margin: 10px 0 0 0; opacity: 0.9;">Manage users</p>
        </div>
    """, unsafe_allow_html=True)
    
    conn = get_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT email, name, role, emp_id, tl_name, location, is_active, created_at FROM users ORDER BY role, name")
            columns = [desc[0] for desc in cursor.description]
            users = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            st.dataframe(pd.DataFrame(users), use_container_width=True, hide_index=True)
            
            # Add user
            st.subheader("➕ Add User")
            
            with st.form("add_user"):
                col1, col2 = st.columns(2)
                
                with col1:
                    new_email = st.text_input("Email")
                    new_name = st.text_input("Name")
                    new_role = st.selectbox("Role", ["Employee", "TL", "Admin"])
                    new_emp_id = st.text_input("Employee ID")
                
                with col2:
                    new_tl_name = st.text_input("TL Name")
                    new_tl_id = st.text_input("TL ID")
                    new_location = st.text_input("Location", value="Gurugram")
                
                if st.form_submit_button("Add User", type="primary", use_container_width=True):
                    if all([new_email, new_name, new_role, new_emp_id]):
                        try:
                            password_hash = hash_password("Password123")
                            cursor.execute("""
                                INSERT INTO users (email, name, role, emp_id, tl_name, tl_id, location, password_hash)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            """, (new_email, new_name, new_role, new_emp_id, new_tl_name, new_tl_id, new_location, password_hash))
                            conn.commit()
                            
                            record_audit(st.session_state.user_email, st.session_state.user_name,
                                       'CREATE_USER', 'users', None, f"Email: {new_email}")
                            
                            st.success(f"User {new_name} added!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {str(e)}")
                    else:
                        st.error("Fill all required fields")
            
        except Exception as e:
            st.error(f"Error: {str(e)}")
        finally:
            release_connection(conn)

def render_audit_logs():
    """Render audit logs - Admin only"""
    st.markdown(f"""
        <div class="main-header">
            <h1 style="margin: 0;">🔍 Audit Logs</h1>
            <p style="margin: 10px 0 0 0; opacity: 0.9;">System activity</p>
        </div>
    """, unsafe_allow_html=True)
    
    conn = get_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT 500")
            columns = [desc[0] for desc in cursor.description]
            logs = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            st.dataframe(pd.DataFrame(logs), use_container_width=True, hide_index=True)
            
        except Exception as e:
            st.error(f"Error: {str(e)}")
        finally:
            release_connection(conn)

if __name__ == "__main__":
    main()
