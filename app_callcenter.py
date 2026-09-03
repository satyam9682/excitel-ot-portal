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
import requests
from io import StringIO

# ==================== CONFIGURATION ====================
VERSION = "2.0.0 - Mobile Ready"
APP_NAME = "Excitel OT Portal - Call Center"
SALT_SECRET = "Excitel_Secure_Salt_2026"
OT_RATE_PER_HOUR = 100.0

# Performance
CACHE_TTL = 300
MAX_CONNECTIONS = 20

# ==================== THEME CONFIG ====================
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
headless = true
""")

# ==================== DATABASE CONNECTION ====================
@st.cache_resource
def get_db_pool():
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
    pool = get_db_pool()
    if pool:
        try:
            return pool.getconn()
        except:
            get_db_pool.clear()
            return get_db_pool().getconn()
    return None

def release_connection(conn):
    if conn and get_db_pool():
        try:
            get_db_pool().putconn(conn)
        except:
            pass

# ==================== CRYPTOGRAPHIC UTILITIES ====================
def hash_password(password: str) -> str:
    return hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        SALT_SECRET.encode('utf-8'),
        100000
    ).hex()

def generate_otp(length: int = 6) -> str:
    return ''.join([str(random.randint(0, 9)) for _ in range(length)])

# ==================== DATABASE SCHEMA ====================
def init_db():
    """Initialize database with enhanced schema for all new features"""
    conn = get_connection()
    if not conn:
        return
    
    try:
        cursor = conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                email TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('Employee', 'TL', 'Admin')),
                emp_id TEXT UNIQUE,
                tl_name TEXT,
                tl_id TEXT,
                location TEXT,
                phone TEXT,
                password_hash TEXT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
        ''')
        
        # OT logs - Core table (existing format preserved)
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
        
        # SMS notifications log
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sms_logs (
                id SERIAL PRIMARY KEY,
                recipient_phone TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'sent', 'failed')),
                provider TEXT,
                sent_at TIMESTAMP,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Slack notifications log
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS slack_logs (
                id SERIAL PRIMARY KEY,
                channel TEXT,
                message TEXT NOT NULL,
                status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'sent', 'failed')),
                sent_at TIMESTAMP,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Audit logs
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
        
        # Performance indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ot_logs_employee ON ot_logs(employee_email)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ot_logs_status ON ot_logs(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ot_logs_date ON ot_logs(date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp)')
        
        # Default users
        default_pass_hash = hash_password("Password123")
        default_users = [
            ("admin@dl.excitel.in", "Excitel Admin", "Admin", "EBND00001", None, None, "Gurugram", "9876543210", default_pass_hash, True),
            ("ritu.mandal@dl.excitel.in", "Ritu Mandal", "TL", "EBND04635", "Nandini Puri", "TL01", "Gurugram", "9876543211", default_pass_hash, True),
            ("jamal.khan@dl.excitel.in", "Jamal Khan", "TL", "EBND04471", "Nandini Puri", "TL01", "Gurugram", "9876543212", default_pass_hash, True),
            ("abhishek.pandey@dl.excitel.in", "Abhishek Pandey", "TL", "EBND04472", "Nandini Puri", "TL01", "Gurugram", "9876543213", default_pass_hash, True),
            ("nandini.puri@dl.excitel.in", "Nandini Puri", "TL", "TL01", "Excitel Admin", "ADMIN", "Gurugram", "9876543214", default_pass_hash, True),
            ("basu.porwal@dl.excitel.in", "Basu Porwal", "Employee", "EBND04475", "Ritu Mandal", "EBND04635", "Gurugram", "9876543215", default_pass_hash, True),
            ("employee1@dl.excitel.in", "Employee One", "Employee", "EBND04476", "Ritu Mandal", "EBND04635", "Gurugram", "9876543216", default_pass_hash, True),
            ("employee2@dl.excitel.in", "Employee Two", "Employee", "EBND04477", "Jamal Khan", "EBND04471", "Gurugram", "9876543217", default_pass_hash, True)
        ]
        
        cursor.executemany("""
            INSERT INTO users (email, name, role, emp_id, tl_name, tl_id, location, phone, password_hash, is_active) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) 
            ON CONFLICT (email) DO UPDATE SET
                name = EXCLUDED.name,
                role = EXCLUDED.role,
                location = EXCLUDED.location,
                phone = EXCLUDED.phone,
                is_active = EXCLUDED.is_active
        """, default_users)
        
        conn.commit()
        print("Database initialized - v2.0 Mobile Ready")
        
    except Exception as e:
        print(f"Database error: {e}")
        if conn:
            conn.rollback()
    finally:
        release_connection(conn)

init_db()

# ==================== AUDIT LOGGING ====================
def record_audit(performer_email: str, performer_name: str, action: str, 
                 target_type: str = None, target_id: int = None, 
                 target_details: str = None):
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
        print(f"Audit Error: {e}")
    finally:
        release_connection(conn)

# ==================== EMAIL SYSTEM ====================
def send_email_notification(recipient_email: str, subject: str, body_html: str):
    if "smtp" not in st.secrets:
        print(f"Email queued: {subject}")
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
                <h2 style="color: #1E3A8A;">OT {status.title()}</h2>
                <p style="color: #64748B;">Dear {employee_name},</p>
                <div style="background: #F8FAFC; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <table style="width: 100%;">
                        <tr><td style="color: #64748B;">Date:</td><td style="font-weight: 600;">{ot_details.get('date', 'N/A')}</td></tr>
                        <tr><td style="color: #64748B;">OT Hours:</td><td style="font-weight: 600;">{ot_details.get('ot_hours', 0)} hrs</td></tr>
                        <tr><td style="color: #64748B;">Amount:</td><td style="color: #10B981; font-weight: 700;">₹{ot_details.get('amount', 0):.2f}</td></tr>
                    </table>
                </div>
                {f"<p style='color: #EF4444; background: #FEF2F2; padding: 12px;'><b>Reason:</b> {ot_details.get('rejection_reason', '')}</p>" if not approved and ot_details.get('rejection_reason') else ''}
                <p style="color: #64748B;">Approved by: <b>{approver_name}</b></p>
            </div>
        </body>
    </html>
    """
    
    send_email_notification(employee_email, subject, body)

# ==================== SMS NOTIFICATIONS (MSG91/Twilio) ====================
def send_sms_notification(phone: str, message: str):
    """Send SMS via MSG91 or Twilio"""
    if "sms" not in st.secrets:
        print(f"SMS queued: {message}")
        return
    
    try:
        provider = st.secrets["sms"].get("provider", "msg91")
        
        if provider == "msg91":
            # MSG91 API
            auth_key = st.secrets["sms"]["msg91_auth_key"]
            url = "https://api.msg91.com/api/sendotp.php"
            params = {
                "otp": message[:6],  # MSG91 OTP format
                "mobile": phone,
                "authkey": auth_key
            }
            response = requests.get(url, params=params, timeout=5)
            
        elif provider == "twilio":
            # Twilio API
            account_sid = st.secrets["sms"]["twilio_account_sid"]
            auth_token = st.secrets["sms"]["twilio_auth_token"]
            from_number = st.secrets["sms"]["twilio_from"]
            
            from twilio.rest import Client
            client = Client(account_sid, auth_token)
            message = client.messages.create(
                body=message,
                from_=from_number,
                to=f"+91{phone}"
            )
        
        # Log SMS
        conn = get_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sms_logs (recipient_phone, message, status, provider, sent_at)
                VALUES (%s, %s, 'sent', %s, %s)
            """, (phone, message, provider, datetime.now()))
            conn.commit()
            release_connection(conn)
        
        print(f"SMS sent to {phone}")
        
    except Exception as e:
        print(f"SMS error: {e}")
        # Log failed SMS
        conn = get_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sms_logs (recipient_phone, message, status, error_message)
                VALUES (%s, %s, 'failed', %s)
            """, (phone, message, str(e)))
            conn.commit()
            release_connection(conn)

def send_ot_sms(employee_phone: str, employee_name: str, ot_details: Dict, approved: bool):
    """Send OT approval/rejection SMS"""
    if approved:
        message = f"Excitel OT: Your OT for {ot_details.get('date')} approved. Hours: {ot_details.get('ot_hours')} | Amount: ₹{ot_details.get('amount')}"
    else:
        message = f"Excitel OT: Your OT for {ot_details.get('date')} rejected. Reason: {ot_details.get('rejection_reason', 'N/A')}"
    
    send_sms_notification(employee_phone, message)

# ==================== SLACK INTEGRATION ====================
def send_slack_notification(message: str, channel: str = "#ot-notifications"):
    """Send Slack notification via webhook"""
    if "slack" not in st.secrets:
        print(f"Slack queued: {message}")
        return
    
    try:
        webhook_url = st.secrets["slack"]["webhook_url"]
        
        payload = {
            "channel": channel,
            "username": "OT Portal Bot",
            "icon_emoji": ":clock3:",
            "text": message
        }
        
        response = requests.post(webhook_url, json=payload, timeout=5)
        
        # Log Slack message
        conn = get_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO slack_logs (channel, message, status, sent_at)
                VALUES (%s, %s, 'sent', %s)
            """, (channel, message, datetime.now()))
            conn.commit()
            release_connection(conn)
        
        print(f"Slack sent to {channel}")
        
    except Exception as e:
        print(f"Slack error: {e}")
        conn = get_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO slack_logs (channel, message, status, error_message)
                VALUES (%s, %s, 'failed', %s)
            """, (channel, message, str(e)))
            conn.commit()
            release_connection(conn)

def send_ot_slack(employee_name: str, ot_details: Dict, approved: bool, approver: str = None):
    """Send OT notification to Slack"""
    if approved:
        emoji = "✅"
        color = "good"
    else:
        emoji = "❌"
        color = "danger"
    
    message = {
        "attachments": [
            {
                "color": color,
                "title": f"{emoji} OT { 'Approved' if approved else 'Rejected' }",
                "fields": [
                    {"title": "Employee", "value": employee_name, "short": True},
                    {"title": "Emp ID", "value": ot_details.get('emp_id', 'N/A'), "short": True},
                    {"title": "Date", "value": str(ot_details.get('date', 'N/A')), "short": True},
                    {"title": "OT Hours", "value": f"{ot_details.get('ot_hours', 0)} hrs", "short": True},
                    {"title": "Amount", "value": f"₹{ot_details.get('amount', 0):.2f}", "short": True},
                    {"title": "Task", "value": ot_details.get('task_type', 'N/A'), "short": True}
                ],
                "footer": f"Excitel OT Portal | Approved by: {approver}" if approver else "Excitel OT Portal"
            }
        ]
    }
    
    send_slack_notification(json.dumps(message))

# ==================== PDF GENERATION ====================
class OTPDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.set_text_color(255, 107, 0)
        self.cell(0, 10, 'Excitel OT Portal', 0, 1, 'C')
    
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

def generate_ot_pdf(ot_data: List[Dict], report_type: str = 'summary') -> bytes:
    pdf = OTPDF()
    pdf.add_page()
    pdf.set_font('Arial', '', 10)
    
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, f'OT Report - {report_type.title()}', 0, 1, 'C')
    
    columns = ['Date', 'Employee', 'Emp ID', 'OT Hours', 'Task', 'Status', 'Amount']
    col_widths = [25, 40, 20, 20, 40, 25, 20]
    
    pdf.set_font('Arial', 'B', 10)
    pdf.set_fill_color(255, 107, 0)
    pdf.set_text_color(255, 255, 255)
    
    for i, col in enumerate(columns):
        pdf.cell(col_widths[i], 10, col, 1, 0, 'C', True)
    pdf.ln()
    
    pdf.set_text_color(0, 0, 0)
    for i, row in enumerate(ot_data):
        pdf.set_fill_color(255 if i % 2 == 0 else 245)
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
    
    pdf.ln(10)
    pdf.set_font('Arial', 'B', 11)
    total_hours = sum(row.get('ot_hours', 0) for row in ot_data)
    total_amount = sum(row.get('amount', 0) for row in ot_data)
    pdf.cell(0, 10, f'Total: {total_hours:.2f} hrs | ₹{total_amount:.2f}', 0, 1, 'R')
    
    return pdf.output(dest='S').encode('latin-1')

# ==================== DATA EXPORT ====================
def export_to_excel(df: pd.DataFrame, sheet_name: str = 'OT') -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
        
        workbook = writer.book
        worksheet = writer.sheets[sheet_name]
        
        header_format = workbook.add_format({'bold': True, 'bg_color': '#FF6B00', 'font_color': 'white', 'border': 1})
        money_format = workbook.add_format({'num_format': '₹#,##0.00'})
        hour_format = workbook.add_format({'num_format': '0.00'})
        
        for col_num in range(len(df.columns)):
            worksheet.write(0, col_num, df.columns[col_num], header_format)
        
        for i, col in enumerate(df.columns):
            if 'amount' in col.lower():
                worksheet.set_column(i, i, None, money_format)
            elif 'hours' in col.lower():
                worksheet.set_column(i, i, None, hour_format)
    
    return output.getvalue()

# ==================== BULK OT IMPORT ====================
def process_bulk_ot_import(file, uploader_email: str, uploader_name: str) -> tuple:
    """Process bulk OT import from Excel/CSV"""
    try:
        # Read file
        if file.name.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
        
        # Validate columns
        required_cols = ['date', 'employee_name', 'emp_id', 'ot_start', 'ot_end', 'task_type']
        missing = [col for col in required_cols if col not in df.columns]
        if missing:
            return False, f"Missing columns: {missing}"
        
        conn = get_connection()
        if not conn:
            return False, "Database connection failed"
        
        cursor = conn.cursor()
        success_count = 0
        error_count = 0
        errors = []
        
        for idx, row in df.iterrows():
            try:
                # Parse date
                ot_date = pd.to_datetime(row['date']).date()
                
                # Parse times
                ot_start = pd.to_datetime(row['ot_start']).time() if row.get('ot_start') else None
                ot_end = pd.to_datetime(row['ot_end']).time() if row.get('ot_end') else None
                shift_start = pd.to_datetime(row['shift_start']).time() if row.get('shift_start') else None
                shift_end = pd.to_datetime(row['shift_end']).time() if row.get('shift_end') else None
                
                if not ot_start or not ot_end:
                    errors.append(f"Row {idx+1}: Missing OT times")
                    error_count += 1
                    continue
                
                # Calculate OT hours
                ot_start_dt = datetime.combine(ot_date, ot_start)
                ot_end_dt = datetime.combine(ot_date, ot_end)
                ot_hours = (ot_end_dt - ot_start_dt).seconds / 3600
                
                # Get employee email from emp_id
                cursor.execute("SELECT email, tl_name FROM users WHERE emp_id = %s", (row['emp_id'],))
                emp = cursor.fetchone()
                employee_email = emp[0] if emp else uploader_email
                tl_name = emp[1] if emp else ""
                
                # Calculate amount
                amount = ot_hours * OT_RATE_PER_HOUR
                
                # Insert OT
                cursor.execute("""
                    INSERT INTO ot_logs (
                        date, employee_email, employee_name, emp_id,
                        shift_start, shift_end, ot_start, ot_end, ot_hours,
                        task_type, task_description, status, tl_name,
                        standard_rate, verified_hours, amount
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    ot_date, employee_email, row['employee_name'], row['emp_id'],
                    shift_start, shift_end, ot_start, ot_end, ot_hours,
                    row.get('task_type', 'Other'), row.get('task_description', ''), 'Pending', tl_name,
                    OT_RATE_PER_HOUR, ot_hours, amount
                ))
                
                success_count += 1
                
            except Exception as e:
                errors.append(f"Row {idx+1}: {str(e)}")
                error_count += 1
        
        conn.commit()
        release_connection(conn)
        
        return True, f"Success: {success_count} | Errors: {error_count}", errors
        
    except Exception as e:
        return False, f"Error: {str(e)}"

# ==================== ANALYTICS ====================
def get_dashboard_analytics(user_email: str = None, role: str = None, 
                           date_range: tuple = None) -> Dict:
    conn = get_connection()
    if not conn:
        return {}
    
    try:
        cursor = conn.cursor()
        
        base_query = "SELECT * FROM ot_logs WHERE 1=1"
        params = []
        
        if date_range and len(date_range) == 2:
            base_query += " AND date BETWEEN %s AND %s"
            params.extend(date_range)
        
        if role == 'Employee' and user_email:
            base_query += " AND employee_email = %s"
            params.append(user_email)
        elif role == 'TL':
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
        
        metrics = {
            'total_hours': df['ot_hours'].sum(),
            'total_amount': df['amount'].sum(),
            'total_records': len(df),
            'avg_hours': df['ot_hours'].mean(),
            'approval_rate': (df['status'] == 'Approved').sum() / len(df) * 100 if len(df) > 0 else 0,
            'pending_count': (df['status'] == 'Pending').sum()
        }
        
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
    if 'user_phone' not in st.session_state:
        st.session_state.user_phone = None
    if 'page' not in st.session_state:
        st.session_state.page = 'login'

def login_user(email: str, password: str) -> tuple:
    conn = get_connection()
    if not conn:
        return False, "Database connection failed"
    
    try:
        cursor = conn.cursor()
        password_hash = hash_password(password)
        
        cursor.execute("""
            SELECT email, name, role, emp_id, tl_name, tl_id, location, phone, is_active
            FROM users
            WHERE email = %s AND password_hash = %s
        """, (email, password_hash))
        
        user = cursor.fetchone()
        
        if user:
            if not user[8]:
                return False, "Account deactivated"
            
            st.session_state.logged_in = True
            st.session_state.user_email = user[0]
            st.session_state.user_name = user[1]
            st.session_state.user_role = user[2]
            st.session_state.user_emp_id = user[3]
            st.session_state.user_phone = user[7]
            st.session_state.page = 'dashboard'
            
            cursor.execute("UPDATE users SET last_login = %s WHERE email = %s", (datetime.now(), email))
            conn.commit()
            
            record_audit(email, user[1], 'LOGIN')
            
            return True, "Login successful"
        else:
            return False, "Invalid credentials"
            
    except Exception as e:
        return False, f"Error: {str(e)}"
    finally:
        release_connection(conn)

def logout_user():
    if st.session_state.user_email:
        record_audit(st.session_state.user_email, st.session_state.user_name, 'LOGOUT')
    
    for key in list(st.session_state.keys()):
        if key.startswith('user_') or key in ['logged_in', 'page']:
            del st.session_state[key]
    
    st.session_state.logged_in = False
    st.session_state.page = 'login'

# ==================== MOBILE-FRIENDLY UI ====================
def render_mobile_nav():
    """Render mobile-friendly navigation"""
    with st.sidebar:
        st.markdown(f"""
            <div style="text-align: center; padding: 15px 0; border-bottom: 2px solid #E2E8F0;">
                <h2 style="color: #FF6B00; margin: 0; font-size: 20px;">Excitel OT</h2>
                <p style="color: #64748B; font-size: 11px; margin: 5px 0;">{st.session_state.user_name}</p>
                <p style="color: #94A3B8; font-size: 10px; margin: 0;">{st.session_state.user_role} | {st.session_state.user_emp_id}</p>
            </div>
        """, unsafe_allow_html=True)
        
        pages = {
            'dashboard': ('📊 Dashboard', ['Employee', 'TL', 'Admin']),
            'submit_ot': ('➕ Submit OT', ['Employee']),
            'my_ot': ('📋 My OT', ['Employee']),
            'approve_ot': ('✅ Approve', ['TL', 'Admin']),
            'bulk_import': ('📥 Bulk Import', ['TL', 'Admin']),
            'reports': ('📈 Reports', ['TL', 'Admin']),
            'exports': ('📤 Exports', ['TL', 'Admin']),
            'users': ('👥 Users', ['Admin']),
            'settings': ('⚙️ Settings', ['Employee', 'TL', 'Admin'])
        }
        
        for page_key, (label, roles) in pages.items():
            if st.session_state.user_role in roles:
                if st.button(label, key=page_key, use_container_width=True,
                            type='primary' if st.session_state.page == page_key else 'secondary'):
                    st.session_state.page = page_key
                    st.rerun()
        
        st.markdown("---")
        if st.button("🚪 Logout", use_container_width=True):
            logout_user()
            st.rerun()

# ==================== ROLE-SPECIFIC DASHBOARDS ====================
def render_employee_dashboard():
    """Employee-specific dashboard"""
    st.markdown(f"""
        <div style="background: linear-gradient(135deg, #FF6B00, #FF8C42); padding: 20px; border-radius: 12px; margin-bottom: 20px; color: white;">
            <h1 style="margin: 0;">📊 My Dashboard</h1>
            <p style="margin: 10px 0 0 0; opacity: 0.9;">Welcome, {st.session_state.user_name}!</p>
        </div>
    """, unsafe_allow_html=True)
    
    # Get employee's analytics
    analytics = get_dashboard_analytics(
        user_email=st.session_state.user_email,
        role='Employee'
    )
    
    df = analytics.get('df', pd.DataFrame())
    metrics = analytics.get('metrics', {})
    
    if not df.empty:
        # Personal metrics
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown(f"""
                <div style="background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); border-left: 4px solid #FF6B00;">
                    <p style="margin: 0; color: #64748B; font-size: 12px;">My OT Hours</p>
                    <h2 style="margin: 10px 0 0 0; color: #FF6B00;">{metrics.get('total_hours', 0):.2f}</h2>
                </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown(f"""
                <div style="background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); border-left: 4px solid #10B981;">
                    <p style="margin: 0; color: #64748B; font-size: 12px;">My Earnings</p>
                    <h2 style="margin: 10px 0 0 0; color: #10B981;">₹{metrics.get('total_amount', 0):,.2f}</h2>
                </div>
            """, unsafe_allow_html=True)
        
        with col3:
            st.markdown(f"""
                <div style="background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); border-left: 4px solid #3B82F6;">
                    <p style="margin: 0; color: #64748B; font-size: 12px;">Total Records</p>
                    <h2 style="margin: 10px 0 0 0; color: #3B82F6;">{metrics.get('total_records', 0)}</h2>
                </div>
            """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        # Recent OT
        st.subheader("📋 Recent OT")
        st.dataframe(df.head(5), use_container_width=True, hide_index=True)
        
        # Quick action
        if st.button("➕ Submit New OT", type="primary", use_container_width=True):
            st.session_state.page = 'submit_ot'
            st.rerun()
    
    else:
        st.info("No OT records yet. Submit your first OT!")
        if st.button("➕ Submit OT Now", type="primary"):
            st.session_state.page = 'submit_ot'
            st.rerun()

def render_tl_dashboard():
    """TL-specific dashboard with team overview"""
    st.markdown(f"""
        <div style="background: linear-gradient(135deg, #FF6B00, #FF8C42); padding: 20px; border-radius: 12px; margin-bottom: 20px; color: white;">
            <h1 style="margin: 0;">📊 Team Dashboard</h1>
            <p style="margin: 10px 0 0 0; opacity: 0.9;">Team Leader View - {st.session_state.user_name}</p>
        </div>
    """, unsafe_allow_html=True)
    
    # Get team analytics
    analytics = get_dashboard_analytics(
        user_email=st.session_state.user_email,
        role='TL'
    )
    
    df = analytics.get('df', pd.DataFrame())
    metrics = analytics.get('metrics', {})
    
    if not df.empty:
        # Team metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Team OT Hours", f"{metrics.get('total_hours', 0):.2f}")
        with col2:
            st.metric("Team Cost", f"₹{metrics.get('total_amount', 0):,.2f}")
        with col3:
            st.metric("Pending Approval", f"{metrics.get('pending_count', 0)}")
        with col4:
            st.metric("Approval Rate", f"{metrics.get('approval_rate', 0):.1f}%")
        
        st.markdown("---")
        
        # Charts
        charts = analytics.get('charts', {})
        
        col1, col2 = st.columns(2)
        
        with col1:
            if 'daily_trend' in charts and not charts['daily_trend'].empty:
                st.subheader("📈 Daily Trend")
                chart = alt.Chart(charts['daily_trend']).mark_line(point=True).encode(
                    x='date:T',
                    y='ot_hours:Q'
                ).properties(height=250)
                st.altair_chart(chart, use_container_width=True)
        
        with col2:
            if 'employee_wise' in charts and not charts['employee_wise'].empty:
                st.subheader("👥 Top Performers")
                chart = alt.Chart(charts['employee_wise']).mark_bar().encode(
                    x='ot_hours:Q',
                    y=alt.Y('employee_name:N', sort='-x')
                ).properties(height=250)
                st.altair_chart(chart, use_container_width=True)
        
        st.markdown("---")
        
        # Pending approvals
        st.subheader("⏳ Pending Approvals")
        pending = df[df['status'] == 'Pending']
        if not pending.empty:
            st.warning(f"{len(pending)} OT records pending approval")
            if st.button("✅ Go to Approvals", type="primary"):
                st.session_state.page = 'approve_ot'
                st.rerun()
        else:
            st.success("All caught up! No pending approvals.")
    
    else:
        st.info("No team OT records yet")

def render_admin_dashboard():
    """Admin dashboard with full overview"""
    st.markdown(f"""
        <div style="background: linear-gradient(135deg, #FF6B00, #FF8C42); padding: 20px; border-radius: 12px; margin-bottom: 20px; color: white;">
            <h1 style="margin: 0;">📊 Admin Dashboard</h1>
            <p style="margin: 10px 0 0 0; opacity: 0.9;">System Overview - {st.session_state.user_name}</p>
        </div>
    """, unsafe_allow_html=True)
    
    # Get all analytics
    analytics = get_dashboard_analytics()
    
    df = analytics.get('df', pd.DataFrame())
    metrics = analytics.get('metrics', {})
    
    if not df.empty:
        # System metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total OT Hours", f"{metrics.get('total_hours', 0):.2f}")
        with col2:
            st.metric("Total Cost", f"₹{metrics.get('total_amount', 0):,.2f}")
        with col3:
            st.metric("Total Records", f"{metrics.get('total_records', 0)}")
        with col4:
            st.metric("Pending", f"{metrics.get('pending_count', 0)}")
        
        st.markdown("---")
        
        # All charts
        charts = analytics.get('charts', {})
        
        col1, col2 = st.columns(2)
        
        with col1:
            if 'daily_trend' in charts:
                st.subheader("📈 Daily Trend")
                chart = alt.Chart(charts['daily_trend']).mark_area().encode(
                    x='date:T',
                    y='ot_hours:Q'
                ).properties(height=300)
                st.altair_chart(chart, use_container_width=True)
        
        with col2:
            if 'status_distribution' in charts:
                st.subheader("📊 Status Distribution")
                chart = alt.Chart(charts['status_distribution']).mark_bar().encode(
                    x='status:N',
                    y='count:Q',
                    color='status:N'
                ).properties(height=300)
                st.altair_chart(chart, use_container_width=True)
        
        st.markdown("---")
        st.subheader("📋 Recent Records")
        st.dataframe(df.head(10), use_container_width=True, hide_index=True)
    
    else:
        st.info("No OT records in system")

# ==================== MAIN APP ====================
def main():
    st.set_page_config(
        page_title="Excitel OT Portal",
        page_icon="⏰",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Mobile-responsive CSS
    st.markdown("""
        <style>
            @media (max-width: 768px) {
                .main > div {padding: 10px;}
                h1 {font-size: 24px;}
                h2 {font-size: 18px;}
            }
            .stButton > button {border-radius: 8px; font-weight: 600;}
            .metric-card {background: white; padding: 15px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.08);}
        </style>
    """, unsafe_allow_html=True)
    
    initialize_session_state()
    
    if not st.session_state.logged_in:
        render_login_page()
    else:
        render_mobile_nav()
        
        page = st.session_state.page
        
        if page == 'dashboard':
            # Role-specific dashboard
            if st.session_state.user_role == 'Employee':
                render_employee_dashboard()
            elif st.session_state.user_role == 'TL':
                render_tl_dashboard()
            elif st.session_state.user_role == 'Admin':
                render_admin_dashboard()
        elif page == 'submit_ot':
            render_submit_ot()
        elif page == 'my_ot':
            render_my_ot()
        elif page == 'approve_ot':
            render_approve_ot()
        elif page == 'bulk_import':
            render_bulk_import()
        elif page == 'reports':
            render_reports()
        elif page == 'exports':
            render_exports()
        elif page == 'users':
            render_user_management()
        elif page == 'settings':
            render_settings()

def render_login_page():
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.markdown("""
            <div style="background: linear-gradient(135deg, #FF6B00, #FF8C42); padding: 30px; border-radius: 12px; color: white;">
                <h1 style="margin: 0;">Excitel OT Portal</h1>
                <p style="margin: 10px 0 0 0; opacity: 0.9;">Call Center Overtime Tracking</p>
            </div>
        """, unsafe_allow_html=True)
        
        st.markdown("### Features")
        st.markdown("""
            - ✅ Single-level approval
            - 📧 Email + SMS notifications
            - 💬 Slack integration
            - 📥 Bulk OT import
            - 📊 Role-specific dashboards
            - 📱 Mobile-friendly
        """)
    
    with col2:
        st.markdown("### Login")
        email = st.text_input("Email", placeholder="email@dl.excitel.in")
        password = st.text_input("Password", type="password")
        
        if st.button("Sign In", type="primary", use_container_width=True):
            if email and password:
                success, message = login_user(email, password)
                if success:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)
            else:
                st.error("Enter email and password")
        
        st.markdown("---")
        st.code("TL: ritu.mandal@dl.excitel.in\nPass: Password123", language="text")

def render_submit_ot():
    """OT submission - Existing format preserved"""
    st.markdown(f"""
        <div style="background: linear-gradient(135deg, #FF6B00, #FF8C42); padding: 20px; border-radius: 12px; margin-bottom: 20px; color: white;">
            <h1 style="margin: 0;">➕ Submit OT</h1>
            <p style="margin: 10px 0 0 0; opacity: 0.9;">₹100/hour</p>
        </div>
    """, unsafe_allow_html=True)
    
    with st.form("submit_ot"):
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
            task_description = st.text_area("Description")
            actual_output = st.number_input("Output (calls/tickets)", min_value=0.0, step=1.0)
        
        submitted = st.form_submit_button("Submit OT", type="primary", use_container_width=True)
        
        if submitted:
            if not all([ot_date, shift_start, shift_end, ot_start, ot_end]):
                st.error("Fill all fields")
            else:
                ot_start_dt = datetime.combine(ot_date, ot_start)
                ot_end_dt = datetime.combine(ot_date, ot_end)
                ot_hours = (ot_end_dt - ot_start_dt).seconds / 3600
                
                amount = ot_hours * OT_RATE_PER_HOUR
                
                conn = get_connection()
                if conn:
                    try:
                        cursor = conn.cursor()
                        cursor.execute("""
                            INSERT INTO ot_logs (
                                date, employee_email, employee_name, emp_id,
                                shift_start, shift_end, ot_start, ot_end, ot_hours,
                                task_type, task_description, status, tl_name,
                                standard_rate, verified_hours, amount
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            RETURNING id
                        """, (
                            ot_date, st.session_state.user_email, st.session_state.user_name,
                            st.session_state.user_emp_id,
                            shift_start, shift_end, ot_start, ot_end, ot_hours,
                            task_type, task_description, 'Pending', '',
                            OT_RATE_PER_HOUR, ot_hours, amount
                        ))
                        
                        ot_id = cursor.fetchone()[0]
                        conn.commit()
                        
                        record_audit(st.session_state.user_email, st.session_state.user_name, 'SUBMIT_OT', 'ot_logs', ot_id)
                        
                        # Notify TL via Slack
                        ot_details = {
                            'emp_id': st.session_state.user_emp_id,
                            'date': str(ot_date),
                            'ot_hours': ot_hours,
                            'task_type': task_type,
                            'amount': amount
                        }
                        send_ot_slack(st.session_state.user_name, ot_details, False)
                        
                        st.success("OT submitted!")
                        st.session_state.page = 'my_ot'
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"Error: {str(e)}")
                    finally:
                        release_connection(conn)

def render_my_ot():
    st.markdown(f"""
        <div style="background: linear-gradient(135deg, #FF6B00, #FF8C42); padding: 20px; border-radius: 12px; margin-bottom: 20px; color: white;">
            <h1 style="margin: 0;">📋 My OT Records</h1>
        </div>
    """, unsafe_allow_html=True)
    
    conn = get_connection()
    if conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM ot_logs WHERE employee_email = %s ORDER BY date DESC LIMIT 50
        """, (st.session_state.user_email,))
        columns = [desc[0] for desc in cursor.description]
        records = [dict(zip(columns, row)) for row in cursor.fetchall()]
        release_connection(conn)
        
        if records:
            df = pd.DataFrame(records)
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            if st.button("📥 Export to Excel"):
                excel_data = export_to_excel(df, "My_OT")
                st.download_button("⬇️ Download", data=excel_data, file_name=f"my_ot.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        else:
            st.info("No records")

def render_approve_ot():
    st.markdown(f"""
        <div style="background: linear-gradient(135deg, #FF6B00, #FF8C42); padding: 20px; border-radius: 12px; margin-bottom: 20px; color: white;">
            <h1 style="margin: 0;">✅ Approve OT</h1>
        </div>
    """, unsafe_allow_html=True)
    
    conn = get_connection()
    if conn:
        cursor = conn.cursor()
        
        if st.session_state.user_role == 'TL':
            cursor.execute("SELECT emp_id FROM users WHERE tl_id = (SELECT tl_id FROM users WHERE email = %s)", (st.session_state.user_email,))
            team_ids = [row[0] for row in cursor.fetchall()]
            if team_ids:
                query = f"SELECT * FROM ot_logs WHERE emp_id IN ({','.join(['%s']*len(team_ids))}) AND status = 'Pending'"
                cursor.execute(query, team_ids)
            else:
                st.info("No team")
                release_connection(conn)
                return
        else:
            cursor.execute("SELECT * FROM ot_logs WHERE status = 'Pending'")
        
        columns = [desc[0] for desc in cursor.description]
        pending = [dict(zip(columns, row)) for row in cursor.fetchall()]
        release_connection(conn)
        
        if pending:
            st.subheader(f"Pending ({len(pending)})")
            
            for ot in pending:
                with st.expander(f"{ot['employee_name']} - {ot['date']} - {ot['ot_hours']} hrs"):
                    st.write(f"**Task:** {ot['task_type']}")
                    st.write(f"**Amount:** ₹{ot['amount']:.2f}")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        verified = st.number_input("Verified Hours", value=ot['ot_hours'], min_value=0.0, key=f"v_{ot['id']}")
                    with col2:
                        if st.button("✅ Approve", type="primary", key=f"a_{ot['id']}", use_container_width=True):
                            update_ot_status(ot['id'], verified, 'approve')
                    
                    reason = st.text_input("Rejection Reason", key=f"r_{ot['id']}")
                    if st.button("❌ Reject", key=f"j_{ot['id']}", use_container_width=True):
                        if reason:
                            update_ot_status(ot['id'], 0, 'reject', reason)
                        else:
                            st.error("Enter reason")
        else:
            st.success("No pending approvals!")

def update_ot_status(ot_id: int, verified_hours: float, action: str, reason: str = None):
    conn = get_connection()
    if not conn:
        return
    
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM ot_logs WHERE id = %s", (ot_id,))
    columns = [desc[0] for desc in cursor.description]
    ot = dict(zip(columns, cursor.fetchone()))
    
    if action == 'approve':
        new_status = 'Approved'
        amount = verified_hours * OT_RATE_PER_HOUR
        cursor.execute("""
            UPDATE ot_logs SET status=%s, verified_hours=%s, amount=%s, approved_by=%s, approved_at=%s WHERE id=%s
        """, (new_status, verified_hours, amount, st.session_state.user_name, datetime.now(), ot_id))
        
        # Send notifications
        send_ot_approval_email(ot['employee_email'], ot['employee_name'], 
                             {'date': ot['date'], 'ot_hours': verified_hours, 'amount': amount}, True, st.session_state.user_name)
        
        # Send SMS
        cursor.execute("SELECT phone FROM users WHERE email = %s", (ot['employee_email'],))
        phone = cursor.fetchone()
        if phone:
            send_ot_sms(phone[0], ot['employee_name'], {'date': ot['date'], 'ot_hours': verified_hours, 'amount': amount}, True)
        
        # Send Slack
        send_ot_slack(ot['employee_name'], {'emp_id': ot['emp_id'], 'date': ot['date'], 'ot_hours': verified_hours, 'amount': amount}, True, st.session_state.user_name)
        
    else:
        cursor.execute("""
            UPDATE ot_logs SET status=%s, rejection_reason=%s WHERE id=%s
        """, ('Rejected', reason, ot_id))
        
        send_ot_approval_email(ot['employee_email'], ot['employee_name'], 
                             {'date': ot['date'], 'ot_hours': ot['ot_hours'], 'rejection_reason': reason}, False, st.session_state.user_name)
        
        cursor.execute("SELECT phone FROM users WHERE email = %s", (ot['employee_email'],))
        phone = cursor.fetchone()
        if phone:
            send_ot_sms(phone[0], ot['employee_name'], {'date': ot['date'], 'rejection_reason': reason}, False)
    
    conn.commit()
    release_connection(conn)
    
    record_audit(st.session_state.user_email, st.session_state.user_name, f'{action.upper()}_OT', 'ot_logs', ot_id)
    st.success(f"OT {action}ed!")
    st.rerun()

def render_bulk_import():
    """Bulk OT import from Excel/CSV"""
    st.markdown(f"""
        <div style="background: linear-gradient(135deg, #FF6B00, #FF8C42); padding: 20px; border-radius: 12px; margin-bottom: 20px; color: white;">
            <h1 style="margin: 0;">📥 Bulk OT Import</h1>
            <p style="margin: 10px 0 0 0; opacity: 0.9;">Import multiple OT records at once</p>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown("### Upload Format")
    st.markdown("""
    **Required columns:** date, employee_name, emp_id, ot_start, ot_end, task_type
    
    **Optional columns:** shift_start, shift_end, task_description, actual_output
    
    **Example:**
    ```
    date,employee_name,emp_id,ot_start,ot_end,task_type,shift_start,shift_end
    2026-09-04,John Doe,EBND04476,18:00,21:00,Customer Escalation,09:00,18:00
    ```
    """)
    
    uploaded_file = st.file_uploader("Upload Excel/CSV", type=['xlsx', 'csv'])
    
    if uploaded_file:
        if st.button("Process Import", type="primary", use_container_width=True):
            success, message = process_bulk_ot_import(uploaded_file, st.session_state.user_email, st.session_state.user_name)
            
            if success:
                st.success(f"✅ {message}")
                
                # Send Slack notification
                send_slack_notification(f"📥 Bulk OT Import: {message} by {st.session_state.user_name}")
            else:
                st.error(f"❌ {message}")

def render_reports():
    st.markdown(f"""
        <div style="background: linear-gradient(135deg, #FF6B00, #FF8C42); padding: 20px; border-radius: 12px; margin-bottom: 20px; color: white;">
            <h1 style="margin: 0;">📈 Reports</h1>
        </div>
    """, unsafe_allow_html=True)
    
    analytics = get_dashboard_analytics()
    df = analytics.get('df', pd.DataFrame())
    metrics = analytics.get('metrics', {})
    
    if not df.empty:
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Hours", f"{metrics.get('total_hours', 0):.2f}")
        col2.metric("Total Cost", f"₹{metrics.get('total_amount', 0):,.2f}")
        col3.metric("Records", f"{metrics.get('total_records', 0)}")
        
        st.markdown("---")
        st.subheader("📊 Daily Trend")
        charts = analytics.get('charts', {})
        if 'daily_trend' in charts:
            chart = alt.Chart(charts['daily_trend']).mark_area().encode(x='date:T', y='ot_hours:Q').properties(height=350)
            st.altair_chart(chart, use_container_width=True)
        
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No data")

def render_exports():
    st.markdown(f"""
        <div style="background: linear-gradient(135deg, #FF6B00, #FF8C42); padding: 20px; border-radius: 12px; margin-bottom: 20px; color: white;">
            <h1 style="margin: 0;">📤 Exports</h1>
        </div>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    with col1:
        format = st.selectbox("Format", ["Excel", "PDF"])
        date_from = st.date_input("From", value=date.today() - timedelta(days=30))
    with col2:
        date_to = st.date_input("To", value=date.today())
    
    conn = get_connection()
    if conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ot_logs WHERE date BETWEEN %s AND %s", (date_from, date_to))
        columns = [desc[0] for desc in cursor.description]
        records = [dict(zip(columns, row)) for row in cursor.fetchall()]
        release_connection(conn)
        
        if records:
            df = pd.DataFrame(records)
            st.info(f"{len(records)} records")
            
            if format == "Excel":
                data = export_to_excel(df)
                st.download_button("⬇️ Excel", data=data, file_name="ot_export.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            else:
                data = generate_ot_pdf(records)
                st.download_button("⬇️ PDF", data=data, file_name="ot_export.pdf", mime="application/pdf")

def render_user_management():
    st.markdown(f"""
        <div style="background: linear-gradient(135deg, #FF6B00, #FF8C42); padding: 20px; border-radius: 12px; margin-bottom: 20px; color: white;">
            <h1 style="margin: 0;">👥 Users</h1>
        </div>
    """, unsafe_allow_html=True)
    
    conn = get_connection()
    if conn:
        cursor = conn.cursor()
        cursor.execute("SELECT email, name, role, emp_id, location, phone FROM users ORDER BY name")
        columns = [desc[0] for desc in cursor.description]
        users = [dict(zip(columns, row)) for row in cursor.fetchall()]
        release_connection(conn)
        
        st.dataframe(pd.DataFrame(users), use_container_width=True, hide_index=True)

def render_settings():
    st.markdown(f"""
        <div style="background: linear-gradient(135deg, #FF6B00, #FF8C42); padding: 20px; border-radius: 12px; margin-bottom: 20px; color: white;">
            <h1 style="margin: 0;">⚙️ Settings</h1>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown(f"""
    **Name:** {st.session_state.user_name}  
    **Email:** {st.session_state.user_email}  
    **Role:** {st.session_state.user_role}  
    **Emp ID:** {st.session_state.user_emp_id}
    """)

if __name__ == "__main__":
    main()
