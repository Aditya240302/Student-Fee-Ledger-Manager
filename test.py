APP_NAME = "School Fee & Ledger Manager"
APP_VERSION = "2.0.0"

import re
import hashlib # Standard library for hashing
import sys
import os
import uuid
import tkcalendar
import tkinter as tk
from tkinter import simpledialog
from cryptography.fernet import Fernet
from tkinter import ttk
from tkinter import messagebox, ttk, font
import sqlite3
import os
import shutil
from datetime import datetime
from tkcalendar import DateEntry
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from tkinter import simpledialog
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
purpose_items = []
siblings = []
sibling_mode = False

# --- DATABASE SETUP ---
DB_NAME = 'school_data.db'
BACKUP_DIR = os.path.join(BASE_DIR, 'database_backups')
# You should store this key securely, not hardcoded in production
BACKUP_KEY = b'g7_QhZ5jFZXM93tz3LZmFajPPVITk3D7sd3iWHzLLOU='
RECEIPT_DIR = os.path.join(BASE_DIR, 'receipts')
FAMILY_REPORT_DIR = os.path.join(BASE_DIR, 'family_reports')

def ensure_app_folders():
    for folder in [BACKUP_DIR, RECEIPT_DIR, FAMILY_REPORT_DIR]:
        os.makedirs(folder, exist_ok=True)

conn = sqlite3.connect(DB_NAME)
c = conn.cursor()

# ---- TEACHER MASTER TABLE ----
c.execute("""
CREATE TABLE IF NOT EXISTS teachers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    designation TEXT,
    phone TEXT,
    join_date TEXT,
    base_salary REAL NOT NULL,
    active_status TEXT DEFAULT 'ACTIVE'
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS salary_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    salary_id INTEGER,
    teacher_id INTEGER,
    pay_amount REAL,
    pay_date TEXT,
    payment_mode TEXT,
    note TEXT,
    FOREIGN KEY(salary_id) REFERENCES salary_payments(id),
    FOREIGN KEY(teacher_id) REFERENCES teachers(id)
)
""")

# ---- SALARY PAYMENT TABLE ----
c.execute("""
CREATE TABLE IF NOT EXISTS salary_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_id INTEGER,
    month INTEGER,
    year INTEGER,
    base_salary REAL,
    payable_salary REAL,
    paid_amount REAL,
    pending_amount REAL,
    payment_mode TEXT,
    payment_date TEXT,
    remarks TEXT,
    receipt_no TEXT,
    FOREIGN KEY (teacher_id) REFERENCES teachers(id)
)
""")

conn.commit()
conn.close()

conn = sqlite3.connect(DB_NAME)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS teacher_salary_calc(
    teacher_id INTEGER,
    month INTEGER,
    year INTEGER,
    calculated_salary REAL,
    PRIMARY KEY (teacher_id, month, year)
)
""")

conn.commit()
conn.close()

def safe_add_recovery_columns():
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()

        # Get existing columns
        c.execute("PRAGMA table_info(teacher_referral)")
        cols = [row[1] for row in c.fetchall()]

        # ------- Add recovery_applied -------
        if "recovery_applied" not in cols:
            c.execute("""
                ALTER TABLE teacher_referral
                ADD COLUMN recovery_applied INTEGER DEFAULT 0
            """)

        # ------- Add recovery_salary_id -------
        if "recovery_salary_id" not in cols:
            c.execute("""
                ALTER TABLE teacher_referral
                ADD COLUMN recovery_salary_id INTEGER
            """)

        conn.commit()
        conn.close()

    except Exception as e:
        print("Column Migration Error:", e)

def open_referral_history():
    win = tk.Toplevel()
    win.title("Teacher Referral History")
    win.geometry("800x500")
    win.grab_set()

    tk.Label(win, text="Referral History", font=("Arial", 14, "bold")).pack(pady=5)

    cols = ("Student", "Teacher", "Amount", "Status", "Paid Month")
    table = ttk.Treeview(win, columns=cols, show="headings", height=18)
    table.pack(fill="both", expand=True, padx=10, pady=10)

    for c in cols:
        table.heading(c, text=c)

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("""
        SELECT 
            s.name,
            t.name,
            r.share_amount,
            r.status,
            IFNULL(r.paid_month,'-')
        FROM teacher_referral r
        JOIN students s ON r.student_id = s.id
        JOIN teachers t ON r.teacher_id = t.id
        ORDER BY r.id DESC
    """)

    for row in c.fetchall():
        table.insert("", tk.END, values=row)

    conn.close()

def save_referrals(cursor, student_id, referral_text):
    if not referral_text:
        return

    teacher_names = [
        t.strip()
        for t in referral_text.split(",")
        if t.strip()
    ]

    for name in teacher_names:
        cursor.execute(
            "SELECT id FROM teachers WHERE LOWER(name)=LOWER(?)",
            (name,)
        )
        row = cursor.fetchone()

        if not row:
            print(f"[Referral skipped] Teacher not found: {name}")
            continue

        teacher_id = row[0]

        # Prevent duplicate referral
        cursor.execute("""
            SELECT COUNT(*) 
            FROM teacher_referral
            WHERE student_id=? AND teacher_id=?
        """, (student_id, teacher_id))

        if cursor.fetchone()[0] == 0:
            cursor.execute("""
                INSERT INTO teacher_referral
                (student_id, teacher_id, status, share_amount)
                VALUES (?, ?, 'PENDING', 0)
            """, (student_id, teacher_id))

def validate_referral_teachers(referral_text):
    if not referral_text.strip():
        return True, []   # No referral is allowed

    names = [n.strip() for n in referral_text.split(",") if n.strip()]

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    invalid = []

    for name in names:
        c.execute("SELECT COUNT(*) FROM teachers WHERE LOWER(name)=LOWER(?)", (name,))
        if c.fetchone()[0] == 0:
            invalid.append(name)

    conn.close()

    if invalid:
        return False, invalid

    return True, []

def create_family_wallet_table():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS family_accounts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            family_id TEXT UNIQUE,
            credit_wallet REAL DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()

import sqlite3

def fix_family_id_column():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # 1️⃣ Check current type
    c.execute("PRAGMA table_info(students)")
    cols = c.fetchall()

    family_col = [col for col in cols if col[1] == "family_id"]
    if not family_col:
        print("family_id column not found")
        return

    col_type = family_col[0][2]

    if col_type.upper() == "TEXT":
        print("family_id already correct (TEXT)")
        conn.close()
        return

    print("Fixing family_id column from INTEGER → TEXT")

    # 2️⃣ Rename old table
    c.execute("ALTER TABLE students RENAME TO students_old")

    # 3️⃣ Recreate table correctly
    c.execute("""
    CREATE TABLE students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        student_class TEXT,
        purpose TEXT,
        total REAL,
        paid REAL,
        balance REAL,
        date_added TEXT,
        receipt_no TEXT,
        payment_mode TEXT,
        family_id TEXT,
        referral TEXT,
        receipt_batch_id TEXT,
        referral_amount REAL
    )
    """)

    # 4️⃣ Copy data
    c.execute("""
    INSERT INTO students
    SELECT
        id, name, student_class, purpose, total, paid, balance,
        date_added, receipt_no, payment_mode,
        CAST(family_id AS TEXT),
        referral, receipt_batch_id, referral_amount
    FROM students_old
    """)

    # 5️⃣ Drop old table
    c.execute("DROP TABLE students_old")

    conn.commit()
    conn.close()

    print("family_id successfully fixed to TEXT")

def init_db():
    ensure_app_folders()
        
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""CREATE TABLE IF NOT EXISTS school_expenses(
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      expense_date TEXT,
                      category TEXT,
                      description TEXT,
                      amount REAL,
                      entered_by TEXT,
                      entry_time TEXT)""")

    cursor.execute("""CREATE TABLE IF NOT EXISTS students (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      name TEXT,
                      student_class TEXT,
                      purpose TEXT,
                      total REAL,
                      paid REAL,
                      balance REAL,
                      date_added TEXT,
                      receipt_no TEXT,
                      payment_mode TEXT,
                      family_id INTEGER,
                      referral TEXT)""")
    
    cursor.execute ("""CREATE TABLE IF NOT EXISTS teacher_referral (
                       id INTEGER PRIMARY KEY AUTOINCREMENT,
                       student_id INTEGER,
                       teacher_id INTEGER,
                       share_amount REAL DEFAULT 0,
                       status TEXT DEFAULT 'PENDING',   -- PENDING / PAID / RECOVER_PENDING / RECOVERED
                       paid_month TEXT,
                       recovery_reason TEXT,

                       -- 🔐 Fraud Proof Safe Accounting
                       recovery_applied INTEGER DEFAULT 0,
                       recovery_salary_id INTEGER)""")

    # --- 1. STUDENTS TABLE ---
    # Included all columns (including family_id, receipt_no, payment_mode) directly
    cursor.execute("""CREATE TABLE IF NOT EXISTS students 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                       name TEXT, 
                       student_class TEXT, 
                       purpose TEXT,
                       total REAL, 
                       paid REAL, 
                       balance REAL, 
                       date_added TEXT,
                       receipt_no TEXT,
                       payment_mode TEXT,
                       family_id TEXT)""")

    # --- 2. ACTIVITY LOG TABLE ---
    cursor.execute("""CREATE TABLE IF NOT EXISTS activity_log 
                      (log_id INTEGER PRIMARY KEY AUTOINCREMENT, 
                       action_type TEXT, 
                       details TEXT, 
                       timestamp TEXT)""")

    # --- 3. NEW: USERS TABLE (Security Improvement) ---
    cursor.execute("""CREATE TABLE IF NOT EXISTS users 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                       username TEXT UNIQUE, 
                       password_hash TEXT, 
                       role TEXT)""")
    
    cursor.execute("""CREATE TABLE IF NOT EXISTS referral_recovery_history (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      teacher_id INTEGER,
                      referral_id INTEGER,
                      student_id INTEGER,
                      recovered_amount REAL,
                      month INTEGER,
                      year INTEGER,
                      salary_id INTEGER,
                      status TEXT,          
                      entry_time TEXT)""")

    # Check if any users exist; if not, create a default admin
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        # Securely hash 'admin123' using SHA-256
        default_password = "admin123"
        pw_hash = hashlib.sha256(default_password.encode()).hexdigest()
        
        cursor.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                       ("admin", pw_hash, "ADMIN"))
        print("Default admin account created.")

    conn.commit()
    conn.close()

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # ---- Add recovery_reason column if missing ----
    c.execute("PRAGMA table_info(teacher_referral)")
    cols = [col[1] for col in c.fetchall()]

    if "recovery_reason" not in cols:
        c.execute("ALTER TABLE teacher_referral ADD COLUMN recovery_reason TEXT")

    conn.commit()
    conn.close()

import sqlite3

DB_NAME = "school_data.db"

# ================= PROMOTION CONFIG =================

PROMOTION_MAP = {
    "pre-nur": "nur",
    "nur": "lkg",
    "lkg": "ukg",
    "ukg": "i",
    "i": "ii",
    "ii": "iii",
    "iii": "iv",
    "iv": "v",
    "v": "vi",
    "vi": "vii",
    "vii": "viii",
    "viii": "ix",
    "ix": "x"
}

def show_promotion_preview():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    preview = []

    for old_class, new_class in PROMOTION_MAP.items():
        c.execute("""
            SELECT COUNT(*)
            FROM students
            WHERE LOWER(TRIM(student_class)) = ?
        """, (old_class,))
        count = c.fetchone()[0]

        if count > 0:
            preview.append(f"{old_class.upper()} → {new_class.upper()} : {count} students")

    conn.close()

    if not preview:
        messagebox.showinfo("Promotion Preview", "No students eligible for promotion.")
        return False

    return messagebox.askyesno(
        "Promotion Preview",
        "The following promotions will occur:\n\n"
        + "\n".join(preview)
        + "\n\nProceed?"
    )

def update_purpose_display():
    global purpose_display
    text = ", ".join([f"{n}({a})" for n, a in purpose_items])
    purpose_display.config(text=text)

def ensure_academic_year_lock():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS academic_year_lock (
            year TEXT PRIMARY KEY,
            promoted INTEGER DEFAULT 0,
            promoted_on TEXT
        )
    """)
    conn.commit()
    conn.close()

def ensure_promotion_history():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS promotion_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            old_class TEXT,
            new_class TEXT,
            year TEXT,
            promoted_on TEXT
        )
    """)
    conn.commit()
    conn.close()

def ensure_expense_table():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS school_expenses(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            expense_date TEXT,
            category TEXT,
            description TEXT,
            amount REAL
        )
    """)
    conn.commit()
    conn.close()

def add_referral_bonus_column():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # Check existing columns
    c.execute("PRAGMA table_info(salary_payments)")
    columns = [col[1] for col in c.fetchall()]

    # Add column only if missing
    if "referral_bonus" not in columns:
        c.execute("""
            ALTER TABLE salary_payments
            ADD COLUMN referral_bonus REAL DEFAULT 0
        """)
        conn.commit()
        print("✅ referral_bonus column added to salary_payments")
    else:
        print("ℹ️ referral_bonus column already exists")

    conn.close()

def safe_referral_updates():
    import sqlite3
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # add referral column in students
    try:
        c.execute("ALTER TABLE students ADD COLUMN referral TEXT")
    except:
        pass

    # add missing referral flags
    try:
        c.execute("ALTER TABLE teacher_referral ADD COLUMN recovery_applied INTEGER DEFAULT 0")
    except:
        pass

    try:
        c.execute("ALTER TABLE teacher_referral ADD COLUMN recovery_salary_id INTEGER")
    except:
        pass

    conn.commit()
    conn.close()

def ensure_referral_column():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # Check existing columns
    c.execute("PRAGMA table_info(students)")
    columns = [col[1].lower() for col in c.fetchall()]

    # If referral_amount not present → create
    if "referral_amount" not in columns:
        c.execute("ALTER TABLE students ADD COLUMN referral_amount REAL DEFAULT 0")
        print("Referral Amount column added successfully.")
    else:
        print("Referral Amount column already exists.")

    conn.commit()
    conn.close()

def ensure_batch_column():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("PRAGMA table_info(students)")
    cols = [col[1].lower() for col in c.fetchall()]

    if "receipt_batch_id" not in cols:
        c.execute("ALTER TABLE students ADD COLUMN receipt_batch_id TEXT")

    conn.commit()
    conn.close()

def add_audit(action, details):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %I:%M %p")
    cursor.execute("INSERT INTO activity_log (action_type, details, timestamp) VALUES (?, ?, ?)", 
                    (action, details, now))
    conn.commit()
    conn.close()

def perform_backup(user_role):
    try:
        if not os.path.exists(BACKUP_DIR):
            os.makedirs(BACKUP_DIR)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Added .encrypted extension to distinguish files
        backup_filename = f"backup_{timestamp}_{user_role}.db.encrypted"
        backup_path = os.path.join(BACKUP_DIR, backup_filename)

        # 1. Read the current database file
        with open(DB_NAME, 'rb') as f:
            data = f.read()

        # 2. Encrypt the data using your key
        fernet = Fernet(BACKUP_KEY)
        encrypted_data = fernet.encrypt(data)

        # 3. Write the encrypted data to the backup folder
        with open(backup_path, 'wb') as f:
            f.write(encrypted_data)

        add_audit("SYSTEM_BACKUP", f"Encrypted auto-backup created: {backup_filename}")
        return True
    except Exception as e:
        print(f"Backup failed: {e}")
        return False

# ================= AUTO RECEIPT NUMBER =================
def get_next_receipt_no():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT receipt_no FROM students WHERE receipt_no IS NOT NULL AND receipt_no != '' ORDER BY id DESC LIMIT 1")
    last = c.fetchone()
    conn.close()

    if not last or last[0] in ("", "None", None):
        return "0001"

    try:
        num = int(last[0])
        return str(num + 1).zfill(4)
    except:
        return "0001"
    
def open_user_management():
    # Log when window is opened
    add_audit("USER MANAGEMENT", "Opened User Management Window")

    user_win = tk.Toplevel()
    user_win.title("User Management")
    user_win.geometry("500x500")
    user_win.configure(bg="#ecf0f1")

    # ---------- UI ----------
    tk.Label(user_win, text="Add New Staff Member",
             font=("Arial", 12, "bold"), bg="#ecf0f1").pack(pady=10)

    frame = tk.Frame(user_win, bg="#ecf0f1")
    frame.pack(pady=5)

    tk.Label(frame, text="Username:", bg="#ecf0f1").grid(row=0, column=0, padx=5, pady=5)
    new_user_entry = tk.Entry(frame)
    new_user_entry.grid(row=0, column=1)

    tk.Label(frame, text="Password:", bg="#ecf0f1").grid(row=1, column=0, padx=5, pady=5)
    new_pw_entry = tk.Entry(frame, show="*")
    new_pw_entry.grid(row=1, column=1)

    # ---------- ADD USER ----------
    def save_new_user():
        u = new_user_entry.get().strip()
        p = new_pw_entry.get()

        if not u or not p:
            messagebox.showwarning("Input Error", "Both fields are required",parent=user_win)
            return

        hashed_p = hashlib.sha256(p.encode()).hexdigest()

        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()

            cursor.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                           (u, hashed_p, "STAFF"))
            conn.commit()
            conn.close()

            # Audit Log
            add_audit("USER CREATED", f"User Added: {u} | Role: STAFF")

            messagebox.showinfo("Success", f"User {u} added successfully!",parent=user_win)
            new_user_entry.delete(0, tk.END)
            new_pw_entry.delete(0, tk.END)
            refresh_user_list()

        except sqlite3.IntegrityError:
            messagebox.showerror("Error", "Username already exists!",parent=user_win)

    tk.Button(user_win, text="Add User",
              command=save_new_user, bg="#27ae60", fg="white").pack(pady=10)

    # ---------- USER LIST ----------
    tk.Label(user_win, text="Existing Users",
             font=("Arial", 10, "bold"), bg="#ecf0f1").pack(pady=5)

    user_listbox = tk.Listbox(user_win, height=8, width=50)
    user_listbox.pack(pady=5, padx=10)

    def refresh_user_list():
        user_listbox.delete(0, tk.END)
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT username, role FROM users")
        for row in cursor.fetchall():
            user_listbox.insert(tk.END, f"{row[0]} - Role: {row[1]}")
        conn.close()

    refresh_user_list()

    def change_password():
        selected = user_listbox.curselection()
        if not selected:
            messagebox.showwarning("Select User", "Please select a user first.")
            return

        user_text = user_listbox.get(selected[0])
        username = user_text.split(" - ")[0].strip()

        if username.lower() == "admin":
            if not messagebox.askyesno(
                "Warning",
                "You are changing the ADMIN password.\n\nContinue?"
            ):
                return

        # Ask new password
        new_pw = simpledialog.askstring(
            "Change Password",
            f"Enter new password for '{username}':",
            show="*"
        )

        if not new_pw:
            return

        # Confirm password
        confirm_pw = simpledialog.askstring(
            "Confirm Password",
            "Re-enter new password:",
            show="*"
        )

        if new_pw != confirm_pw:
            messagebox.showerror("Mismatch", "Passwords do not match.")
            return

        # Hash password
        pw_hash = hashlib.sha256(new_pw.encode()).hexdigest()

        try:
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()

            c.execute(
                "UPDATE users SET password_hash=? WHERE username=?",
                (pw_hash, username)
            )

            conn.commit()
            conn.close()

            add_audit("PASSWORD_CHANGE", f"Password changed for user '{username}'")
            messagebox.showinfo("Success", f"Password updated for '{username}'")

            refresh_user_list()

        except Exception as e:
            messagebox.showerror("Error", str(e))

    # ---------- DELETE USER ----------
    def delete_user():
        try:
            selected = user_listbox.get(user_listbox.curselection())
            username = selected.split(" - ")[0]

            if username.lower() == "admin":
                messagebox.showerror("Error", "Admin cannot be deleted",parent=user_win)
                return

            # fetch role for audit
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("SELECT role FROM users WHERE username=?", (username,))
            role_row = cursor.fetchone()

            if not role_row:
                messagebox.showerror("Error", "User not found",parent=user_win)
                conn.close()
                return

            role = role_row[0]

            if not messagebox.askyesno("Confirm", f"Delete user '{username}'?"):
                conn.close()
                return

            cursor.execute("DELETE FROM users WHERE username=?", (username,))
            conn.commit()
            conn.close()

            # Audit Log
            add_audit("USER DELETED", f"User Removed: {username} | Role: {role}")

            refresh_user_list()
            messagebox.showinfo("Deleted", f"User '{username}' deleted successfully",parent=user_win)

        except:
            messagebox.showerror("Error", "Please select a user")

    tk.Button(user_win, text="Delete Selected User",
              bg="#c0392b", fg="white", command=delete_user).pack(pady=10)
    
    tk.Button(
        user_win,
        text="Change Password",
        bg="#2980B9",
        fg="white",
        command=change_password
    ).pack(pady=10)

import re

def show_financial_dashboard():
    import sqlite3
    import tkinter as tk
    import re

    dash_win = tk.Toplevel()
    dash_win.title("Financial Overview")
    dash_win.geometry("460x380")
    dash_win.configure(bg="#2c3e50")

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # ================================
    # 1️⃣ PAID (simple sum)
    # ================================
    cursor.execute("""
        SELECT IFNULL(SUM(paid),0)
        FROM students
        WHERE strftime('%Y-%m', date_added) = strftime('%Y-%m','now')
    """)
    paid_sum = cursor.fetchone()[0]

    # ================================
    # 2️⃣ EXPECTED (true fees only)
    # ================================
    cursor.execute("""
        SELECT purpose
        FROM students
        WHERE strftime('%Y-%m', date_added) = strftime('%Y-%m','now')
    """)

    rows = cursor.fetchall()
    expected = 0

    for (purpose,) in rows:
        if not purpose:
            continue

        items = purpose.split(",")

        for item in items:
            m = re.search(r"\(([\d.]+)\)", item)
            if not m:
                continue

            amount = float(m.group(1))
            name = item.lower()

            # Skip balance carry-forward
            if "balance" in name:
                continue

            expected += amount

    # ================================
    # 3️⃣ PENDING = LAST BALANCE PER FAMILY
    # ================================
    cursor.execute("""
        SELECT SUM(s.balance) FROM (
            SELECT family_id, MAX(id) AS last_id
            FROM students
            WHERE strftime('%Y-%m', date_added) = strftime('%Y-%m','now')
            GROUP BY family_id
        ) f
        JOIN students s ON s.id = f.last_id
    """)
    pending = cursor.fetchone()[0] or 0

    # ================================
    # 4️⃣ EXPENSES
    # ================================
    cursor.execute("""
        SELECT IFNULL(SUM(amount),0)
        FROM school_expenses
        WHERE strftime('%Y-%m', expense_date) = strftime('%Y-%m','now')
    """)
    monthly_expense = cursor.fetchone()[0]

    conn.close()

    # ================================
    # 5️⃣ NET COLLECTION
    # ================================
    net_collection = paid_sum - monthly_expense
    if net_collection < 0:
        net_collection = 0

    # ================================
    #  UI
    # ================================
    tk.Label(
        dash_win,
        text="School Financial Summary",
        font=("Arial", 14, "bold"),
        bg="#2c3e50",
        fg="#ecf0f1"
    ).pack(pady=15)

    stats_frame = tk.Frame(dash_win, bg="#34495e", padx=20, pady=20)
    stats_frame.pack(padx=20, fill="x")

    def add_stat(title, value, color):
        f = tk.Frame(stats_frame, bg="#34495e")
        f.pack(fill="x", pady=8)

        tk.Label(
            f, text=title,
            font=("Arial", 11, "bold"),
            bg="#34495e", fg=color
        ).pack(anchor="w")

        tk.Label(
            f, text=f"₹ {value:,.2f}",
            font=("Arial", 15, "bold"),
            bg="#34495e", fg=color
        ).pack(anchor="w")

    add_stat("EXPECTED (Fees)", expected, "#2ecc71")
    add_stat("PAID", paid_sum, "#3498db")
    add_stat("EXPENSES", monthly_expense, "#f39c12")
    add_stat("NET COLLECTION", net_collection, "#2ecc71")
    add_stat("PENDING (Family Dues)", pending, "#e74c3c")

    tk.Button(
        dash_win,
        text="Close",
        command=dash_win.destroy,
        bg="#95a5a6",
        width=10
    ).pack(pady=20)

def filter_by_family():
    global tree  # <--- Add this line
    # 1. Get the selected student from the table
    selected_item = tree.selection()
    if not selected_item:
        messagebox.showwarning("Selection Required", "Please click on a student in the table first to find their family.")
        return

    # 2. Extract the Family ID (Column index 3 in your Treeview)
    item_data = tree.item(selected_item)
    f_id = item_data['values'][3] 

    if not f_id:
        messagebox.showerror("Error", "No Family ID found for this student.")
        return

    # 3. Clear the table and show all members with that ID
    for item in tree.get_children():
        tree.delete(item)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Pulls all records matching that specific Family ID
    cursor.execute("SELECT id, name, student_class, family_id, purpose, total, paid, payment_mode, balance, date_added FROM students WHERE family_id = ?", (f_id,))
    rows = cursor.fetchall()
    
    for row in rows:
        # Apply red text if they still have a balance
        tag = ('due',) if row[8] > 0 else ()
        tree.insert("", tk.END, values=row, tags=tag)
    
    conn.close()
    add_audit("FILTER", f"Viewed Family Group: {f_id}")

# ================= MAIN APP ==================
def main_app(user_role):
    root = tk.Tk()
    root.title(f"School Fee & Ledger Manager - Pro [{user_role} MODE]")
    root.geometry("1400x950")
    
    selected_record_id = tk.StringVar()
    classes = ["Pre-Nur","Nur","LKG","UKG","I","II","III","IV","V","VI","VII","VIII","IX","X"]
    search_classes = classes
    months = ["January","February","March","April","May","June","July","August","September","October","November","December"]
    years = [str(y) for y in range(2020,2036)]
    global purpose_items, tree, summary_canvas
    purpose_items.clear()
    global current_family_id
    #referral_used_in_batch = False
    current_family_id = None

    def ask_other_purpose():
        popup = tk.Toplevel()
        popup.title("Other Item")
        popup.geometry("420x240")
        popup.grab_set()  # modal window

        tk.Label(
            popup,
            text="Enter Description",
            font=("Arial", 11, "bold")
        ).pack(pady=(15, 5))

        desc_entry = tk.Entry(popup, width=45)
        desc_entry.pack(pady=5)
        desc_entry.focus()

        tk.Label(
            popup,
            text="Enter Amount",
            font=("Arial", 11, "bold")
        ).pack(pady=(15, 5))

        amt_entry = tk.Entry(popup, width=20)
        amt_entry.pack(pady=5)

        def save_other():
            desc = desc_entry.get().strip()
            amt_text = amt_entry.get().strip()

            if not desc:
                messagebox.showerror(
                    "Required",
                    "Description cannot be empty",
                    parent=popup
                )
                return

            try:
                amount = float(amt_text)
                if amount < 0:
                    raise ValueError
            except:
                messagebox.showerror(
                    "Invalid Amount",
                    "Please enter a valid amount",
                    parent=popup
                )
                return

            # 🔥 ADD DIRECTLY TO PURPOSE ITEMS
            purpose_items.append((desc, amount))
            update_purpose_display()

            popup.destroy()

        tk.Button(
            popup,
            text="Add Item",
            bg="green",
            fg="white",
            width=12,
            command=save_other
        ).pack(pady=20)

    def promote_all_students():
        if user_role != "ADMIN":
            messagebox.showerror("Access Denied", "Only ADMIN can promote students.")
            return

        academic_year = f"{datetime.now().year}-{datetime.now().year + 1}"

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()

        # 🔒 Academic year lock
        c.execute("SELECT promoted FROM academic_year_lock WHERE year=?", (academic_year,))
        row = c.fetchone()
        if row and row[0] == 1:
            conn.close()
            messagebox.showerror(
                "Locked",
                f"Promotion already completed for Academic Year {academic_year}"
            )
            return

        # 📊 Preview
        if not show_promotion_preview():
            conn.close()
            return

        # 💾 Backup
        if not perform_backup(user_role):
            conn.close()
            messagebox.showerror("Backup Failed", "Promotion aborted.")
            return

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        promoted = 0

        # ✅ FETCH students ONCE (important!)
        c.execute("""
            SELECT id, student_class
            FROM students
        """)
        students = c.fetchall()

        for sid, current_class in students:

            norm_class = (current_class or "").strip().lower()

            if norm_class in PROMOTION_MAP:
                new_class = PROMOTION_MAP[norm_class]

                # Preserve display format (First letter capital)
                new_class_display = new_class.upper() if new_class in ["i","ii","iii","iv","v","vi","vii","viii","ix","x"] else new_class.capitalize()

                # save history (for undo)
                c.execute("""
                    INSERT INTO promotion_history
                    (student_id, old_class, new_class, year, promoted_on)
                    VALUES (?, ?, ?, ?, ?)
                """, (sid, current_class, new_class, academic_year, now))

                # update student
                c.execute("""
                    UPDATE students
                    SET student_class = ?
                    WHERE id = ?
                """, (new_class_display, sid))

                promoted += 1

        # 🔒 Lock the year
        c.execute("""
            INSERT OR REPLACE INTO academic_year_lock
            (year, promoted, promoted_on)
            VALUES (?, 1, ?)
        """, (academic_year, now))

        conn.commit()
        conn.close()

        refresh_table()

        messagebox.showinfo(
            "Promotion Successful",
            f"Students promoted: {promoted}\nAcademic Year: {academic_year}"
        )

    def open_expense_manager():
        win = tk.Toplevel()
        win.title("School Expenses")
        win.geometry("800x450")
        win.grab_set()

        # ---------- Top Entry Frame ----------
        top = tk.Frame(win)
        top.pack(pady=10)

        tk.Label(top, text="Date").grid(row=0, column=0)
        date = DateEntry(top, date_pattern="yyyy-mm-dd")
        date.grid(row=0, column=1)

        tk.Label(top, text="Category").grid(row=0, column=2)
        cat = ttk.Combobox(top, values=["Stationery","Chalk","Cleaning","Office","Electricity","Other"])
        cat.grid(row=0, column=3)

        tk.Label(top, text="Description").grid(row=0, column=4)
        desc = tk.Entry(top, width=20)
        desc.grid(row=0, column=5)

        tk.Label(top, text="Amount").grid(row=0, column=6)
        amt = tk.Entry(top, width=10)
        amt.grid(row=0, column=7)

        # ---------- Save ----------
        def save_expense():
            try:
                a = float(amt.get())
            except:
                messagebox.showerror("Invalid", "Enter valid amount")
                return

            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute("""
                INSERT INTO school_expenses
                (expense_date, category, description, amount, entered_by, entry_time)
                VALUES (?,?,?,?,?,?)
            """, (
                date.get(),
                cat.get(),
                desc.get(),
                a,
                logged_in_user,
                datetime.now().strftime("%Y-%m-%d %H:%M")
            ))
            conn.commit()
            conn.close()
            load_expenses()
            show_financial_dashboard()

        tk.Button(top, text="Add Expense", bg="green", fg="white", command=save_expense).grid(row=0, column=8, padx=10)

        # ---------- Table ----------
        cols = ("ID","Date","Category","Description","Amount","By")
        table = ttk.Treeview(win, columns=cols, show="headings", height=15)
        table.pack(fill="both", expand=True, padx=10, pady=10)

        for c in cols:
            table.heading(c, text=c)

        # ---------- Load ----------
        def load_expenses():
            table.delete(*table.get_children())
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute("""
                SELECT id, expense_date, category, description, amount, entered_by
                FROM school_expenses
                ORDER BY id DESC
            """)
            for r in c.fetchall():
                table.insert("", tk.END, values=r)
            conn.close()

        load_expenses()

        # ---------- DELETE ----------
        def delete_expense():
            if user_role != "ADMIN":
                messagebox.showerror("Access Denied", "Only ADMIN can delete expenses")
                return

            sel = table.focus()
            if not sel:
                messagebox.showwarning("Select", "Select expense first")
                return

            data = table.item(sel)['values']
            eid = data[0]
            amt = data[4]

            if not messagebox.askyesno(
                "Confirm",
                f"Delete this expense?\nAmount: ₹{amt}"
            ):
                return

            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute("DELETE FROM school_expenses WHERE id=?", (eid,))
            conn.commit()
            conn.close()

            add_audit("EXPENSE_DELETE", f"Deleted Expense ID {eid} Amount ₹{amt}")
            load_expenses()
            show_financial_dashboard()

        tk.Button(win, text="Delete Selected Expense",
                  bg="red", fg="white",
                  command=delete_expense).pack(pady=10)

    def undo_last_promotion():
        if user_role != "ADMIN":
            messagebox.showerror(
                "Access Denied",
                "Only ADMIN can undo promotion."
            )
            return

        if not messagebox.askyesno(
            "Undo Promotion",
            "This will revert the LAST promotion.\n\nProceed?"
        ):
            return

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()

        c.execute("""
            SELECT DISTINCT year FROM promotion_history
            ORDER BY id DESC LIMIT 1
        """)
        row = c.fetchone()

        if not row:
            conn.close()
            messagebox.showinfo("Undo", "No promotion history found.")
            return

        year = row[0]

        c.execute("""
            SELECT student_id, old_class
            FROM promotion_history
            WHERE year=?
        """, (year,))
        rows = c.fetchall()

        for sid, old_class in rows:
            c.execute(
                "UPDATE students SET student_class=? WHERE id=?",
                (old_class, sid)
            )

        # Cleanup
        c.execute("DELETE FROM promotion_history WHERE year=?", (year,))
        c.execute("DELETE FROM academic_year_lock WHERE year=?", (year,))

        conn.commit()
        conn.close()

        refresh_table()
        messagebox.showinfo("Undo Complete", f"Promotion for {year} reverted.")

    def contains_admission(items):
        return any("admission" in n.lower() for n, _ in items)
    
    # def family_already_has_referral(family_id):
    #     conn = sqlite3.connect(DB_NAME)
    #     c = conn.cursor()

    #     c.execute("""
    #         SELECT COUNT(*) 
    #         FROM students 
    #         WHERE family_id = ? AND referral IS NOT NULL
    #     """, (family_id,))

    #     used = c.fetchone()[0] > 0

    #     conn.close()
    #     return used

    def all_students_have_admission(all_students):
        for s in all_students:
            items = s.get("items", [])
            if not any("admission" in str(n).lower() for n, _ in items):
                return False
        return True
    
    def refresh_referral_box():
        global purpose_items, current_family_id

        # 1. no admission in items → disable
        if not contains_admission(purpose_items):
            referral_entry.delete(0, tk.END)
            referral_entry.config(state="disabled", bg="#f0f0f0")
            return

        # # 2. admission exists BUT referral already used
        # if referral_used_in_batch:
        #     referral_entry.delete(0, tk.END)
        #     referral_entry.config(state="disabled", bg="#f0f0f0")
        #     return

        # 3. admission exists BUT family already used referral earlier
        # if current_family_id and family_already_has_referral(current_family_id):
        #     referral_entry.delete(0, tk.END)
        #     referral_entry.config(state="disabled", bg="#f0f0f0")
        #     return

        # 4. otherwise allow entering referral
        referral_entry.config(state="normal", bg="white")

    def open_referral_window():
        ref = tk.Toplevel()
        ref.title("Referral Management")
        ref.geometry("700x450")
        ref.grab_set()

        tk.Label(ref, text="Select Teacher",
                 font=("Arial",11,"bold")).pack(pady=5)

        teacher_box = ttk.Combobox(ref, width=50, state="readonly")
        teacher_box.pack(pady=5)

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT id, name FROM teachers WHERE active_status='ACTIVE'")
        data = c.fetchall()
        conn.close()

        teacher_box['values'] = [f"{i} - {n}" for i,n in data]

        # ---------- TABLE ----------
        cols = ("Student ID","Share Amount","Status")
        table = ttk.Treeview(ref, columns=cols, show="headings", height=8)
        table.pack(pady=10, fill="x")

        for c in cols:
            table.heading(c, text=c)

        # ---------- AMOUNT ENTRY ----------
        tk.Label(ref, text="Enter Total Referral Amount",
                 font=("Arial",11)).pack(pady=5)
    
        amount_entry = tk.Entry(ref, font=("Arial",12))
        amount_entry.pack(pady=5)


        def load_referral_table(event=None):
            table.delete(*table.get_children())

            if not teacher_box.get():
                return

            tid = int(teacher_box.get().split("-")[0])

            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()

            c.execute("""
                SELECT student_id, share_amount, status
                FROM teacher_referral
                WHERE teacher_id=? 
                ORDER BY status DESC
            """, (tid,))

            rows = c.fetchall()
            conn.close()

            for r in rows:
                table.insert("", tk.END, values=r)

        teacher_box.bind("<<ComboboxSelected>>", load_referral_table)

        def assign_amount():
            if not teacher_box.get():
                messagebox.showwarning("Select", "Select Teacher First")
                return

            try:
                total = float(amount_entry.get())   # Referral per student
            except:
                messagebox.showerror("Invalid", "Enter Valid Amount")
                return

            tid = int(teacher_box.get().split("-")[0])

            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()

            # SAFETY → Prevent double distribution
            c.execute("""
            SELECT COUNT(*) FROM teacher_referral
            WHERE teacher_id=? AND status='PENDING'
            AND (share_amount IS NULL OR share_amount=0)
            """, (tid,))
            pending_left = c.fetchone()[0]

            if pending_left == 0:
                conn.close()
                messagebox.showinfo(
                    "Done",
                    "Referral already distributed earlier.\nNothing to update."
                )
                return

            # Get all pending students for this teacher
            c.execute("""
                SELECT DISTINCT student_id
                FROM teacher_referral
                WHERE teacher_id=? AND status='PENDING'
            """, (tid,))
            students = [r[0] for r in c.fetchall()]

            if not students:
                conn.close()
                messagebox.showinfo("No Data", "No Pending Referral")
                return

            # Process EACH STUDENT separately
            for sid in students:

                # Count teachers for THIS student
                c.execute("""
                    SELECT COUNT(*)
                    FROM teacher_referral
                    WHERE student_id=? AND status='PENDING'
                """, (sid,))
                teacher_count = c.fetchone()[0]

                if teacher_count == 0:
                    continue

                # FINAL CORRECT SPLIT
                split_amount = total / teacher_count

                c.execute("""
                    UPDATE teacher_referral
                    SET share_amount=?
                    WHERE student_id=? AND status='PENDING'
                """, (split_amount, sid))

            conn.commit()
            conn.close()

            load_referral_table()

            messagebox.showinfo(
                "Updated",
                "Referral distributed PER STUDENT correctly."
            )
            
        def reset_referrals():
            if not messagebox.askyesno(
                "Confirm Reset",
                "This will clear all referral share amounts and return them to PENDING.\n\n"
                "Are you sure?"
            ):
                return

            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()

            c.execute("""
            UPDATE teacher_referral
            SET share_amount = 0,
                status='PENDING',
                paid_month=NULL,
                recovery_reason=NULL
            """)

            conn.commit()
            conn.close()

            load_referral_table()
            messagebox.showinfo("Reset Done", "All referral values reset successfully.")

        tk.Button(ref,
                  text="Save Referral Amount",
                  bg="green",
                  fg="white",
                  font=("Arial",11,"bold"),
                  command=assign_amount).pack(pady=10)
        
        tk.Button(ref,
                  text="RESET REFERRALS",
                  bg="red",
                  fg="white",
                  font=("Arial",11,"bold"),
                  command=reset_referrals
        ).pack(pady=10)
        
    def open_salary_module():

        def fetch_salary_for_payment(event=None):
            if not teacher_box.get() or not month_box.get() or not year_box.get():
                return

            tid = int(teacher_box.get().split("-")[0])
            month = int(month_box.get())
            year = int(year_box.get())

            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()

            # 1️⃣ Get calculated salary (from calculator tab)
            c.execute("""
                SELECT calculated_salary
                FROM teacher_salary_calc
                WHERE teacher_id=? AND month=? AND year=?
            """, (tid, month, year))
            row = c.fetchone()

            if row and row[0] is not None:
                base_salary = float(row[0])
            else:
                # fallback to teacher base salary
                c.execute("SELECT base_salary FROM teachers WHERE id=?", (tid,))
                base_salary = float(c.fetchone()[0])

            # 2️⃣ Referral bonus (pending)
            c.execute("""
                SELECT IFNULL(SUM(share_amount), 0)
                FROM teacher_referral
                WHERE teacher_id=? AND status='PENDING'
            """, (tid,))
            referral_bonus = float(c.fetchone()[0])

            # 3️⃣ Recovery pending (preview only)
            c.execute("""
                SELECT IFNULL(SUM(share_amount), 0)
                FROM teacher_referral
                WHERE teacher_id=? AND status='RECOVER_PENDING'
            """, (tid,))
            recovery_pending = float(c.fetchone()[0])

            conn.close()

            # 4️⃣ Calculate final payable
            total_earnings = base_salary + referral_bonus
            final_payable = max(0, total_earnings - recovery_pending)

            # 5️⃣ Populate UI
            base_entry.delete(0, tk.END)
            base_entry.insert(0, f"{final_payable:.2f}")

            paid_entry.delete(0, tk.END)
            paid_entry.insert(0, f"{final_payable:.2f}")

            pend_entry.delete(0, tk.END)
            pend_entry.insert(0, "0.00")

        def add_salary_audit(action, details):
            try:
                conn = sqlite3.connect(DB_NAME)
                c = conn.cursor()
                c.execute("""
                INSERT INTO activity_log (timestamp, action_type, details)
                VALUES (?, ?, ?)
                """, (
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    action,
                    details
                ))
                conn.commit()
                conn.close()
            except:
                pass

        win = tk.Toplevel(root)
        win.title("Teacher Salary Module - Phase 1")
        win.geometry("900x520")

        win.grab_set()
        # ✅ Allow Minimize + Maximize
        win.resizable(True, True)
        win.attributes("-toolwindow", False)
        win.state("normal")

        # ✅ Keep popup above main BUT allow normal buttons
        win.lift()
        win.attributes("-topmost", True)
        win.after(500, lambda: win.attributes("-topmost", False))

        add_salary_audit("OPEN_MODULE", "Teacher Salary Module Opened")

        # (DO NOT USE transient or overrideredirect)

        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True)

        # ================= TAB - SALARY CALCULATOR =================
        calc_frame = tk.Frame(nb, bg="white")
        nb.add(calc_frame, text="🧮 Salary Calculator")

        import calendar

        tk.Label(calc_frame, text="Select Teacher").grid(row=0, column=0, padx=10, pady=10)
        cal_teacher = ttk.Combobox(calc_frame, width=25, state="readonly")
        cal_teacher.grid(row=0, column=1)

        def load_cal_teachers():
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute("SELECT id,name FROM teachers WHERE active_status='ACTIVE'")
            data = c.fetchall()
            conn.close()
            cal_teacher["values"] = [f"{i}-{n}" for i,n in data]

        load_cal_teachers()

        tk.Label(calc_frame, text="Month").grid(row=1, column=0, padx=10)
        cal_month = ttk.Combobox(calc_frame, values=list(range(1,13)),
                         width=10, state="readonly")
        cal_month.grid(row=1, column=1)

        tk.Label(calc_frame, text="Year").grid(row=2, column=0, padx=10)
        cal_year = ttk.Combobox(calc_frame, values=[2024,2025,2026,2027],
                        width=10, state="readonly")
        cal_year.grid(row=2, column=1)

        # ---------- Base Salary ----------
        tk.Label(calc_frame, text="Base Salary").grid(row=3, column=0, pady=10)
        cal_base_show = tk.Label(calc_frame, text="₹ 0", font=("Arial",13,"bold"), fg="blue")
        cal_base_show.grid(row=3, column=1)

        # ---------- Holidays ----------
        tk.Label(calc_frame, text="Total Holidays Taken").grid(row=4, column=0, pady=10)
        cal_holidays = tk.Entry(calc_frame)
        cal_holidays.grid(row=4, column=1)

        # ---------- Half Days ----------
        tk.Label(calc_frame, text="Half Days").grid(row=5, column=0, pady=10)
        cal_half = tk.Entry(calc_frame)
        cal_half.grid(row=5, column=1)

        # ---------- Results ----------
        tk.Label(calc_frame, text="Per Day Salary", font=("Arial",11)).grid(row=6, column=0, pady=10)
        cal_perday = tk.Label(calc_frame, text="₹ 0", font=("Arial",12,"bold"), fg="purple")
        cal_perday.grid(row=6, column=1)

        tk.Label(calc_frame, text="Deduction", font=("Arial",11)).grid(row=7, column=0, pady=10)
        cal_deduct = tk.Label(calc_frame, text="₹ 0", font=("Arial",12,"bold"), fg="red")
        cal_deduct.grid(row=7, column=1)

        tk.Label(calc_frame, text="Final Payable Salary", font=("Arial",11,"bold")).grid(row=8, column=0, pady=10)
        cal_final = tk.Label(calc_frame, text="₹ 0", font=("Arial",13,"bold"), fg="green")
        cal_final.grid(row=8, column=1)

        def calculate_salary():
            if not cal_teacher.get() or not cal_month.get() or not cal_year.get():
                messagebox.showwarning("Required", "Select Teacher, Month & Year")
                return

            tid = int(cal_teacher.get().split("-")[0])
            m = int(cal_month.get())
            y = int(cal_year.get())

            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute("SELECT base_salary FROM teachers WHERE id=?", (tid,))
            base = float(c.fetchone()[0])
            conn.close()

            # Total days in month
            total_days = calendar.monthrange(y, m)[1]

            # Get holidays
            try:
                holidays = float(cal_holidays.get() or 0)
                half_days = float(cal_half.get() or 0)
            except:
                holidays = 0
                half_days = 0

            # Allow 1 free holiday
            effective_loss = max(0, holidays - 1) + (half_days * 0.5)

            per_day_salary = base / total_days
            deduction = per_day_salary * effective_loss
            final_salary = base - deduction

            if final_salary < 0:
                final_salary = 0

            cal_base_show.config(text=f"₹ {base:.2f}")
            cal_perday.config(text=f"₹ {per_day_salary:.2f}")
            cal_deduct.config(text=f"₹ {deduction:.2f}")
            cal_final.config(text=f"₹ {final_salary:.2f}")

            # -------- SAVE CALCULATED SALARY --------
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()

            c.execute("""
            INSERT OR REPLACE INTO teacher_salary_calc
            (teacher_id, month, year, calculated_salary)
            VALUES (?, ?, ?, ?)
            """, (tid, m, y, final_salary))

            conn.commit()
            conn.close()

            messagebox.showinfo(
                "Saved",
                f"Calculated Salary Saved\n\nMonth: {m}-{y}\nPayable: ₹{final_salary:.2f}"
            )

        tk.Button(calc_frame,
                  text="Calculate",
                  bg="green",
                  fg="white",
                  font=("Arial",11,"bold"),
                  command=calculate_salary
        ).grid(row=9, column=1, pady=15)

        tk.Button(calc_frame,
                  text="Clear",
                  bg="red",
                  fg="white",
                  command=lambda: (
                      cal_teacher.set(""),
                      cal_month.set(""),
                      cal_year.set(""),
                      cal_holidays.delete(0,tk.END),
                      cal_half.delete(0,tk.END),
                      cal_base_show.config(text="₹ 0"),
                      cal_perday.config(text="₹ 0"),
                      cal_deduct.config(text="₹ 0"),
                      cal_final.config(text="₹ 0")
                  )
        ).grid(row=9, column=0, pady=15)

        def stay_on_current_tab():
            try:
                idx = nb.index("current")
                win.after(50, lambda: nb.select(idx))
            except:
                pass

        def on_tab_change(event):
            try:
                selected_tab = event.widget.tab(event.widget.index("current"))["text"]
                if selected_tab == "Dashboard":
                    load_salary_dashboard()
            except:
                pass

        nb.bind("<<NotebookTabChanged>>", on_tab_change)   

        report_tab = ttk.Frame(nb)
        for i in range(10):
            report_tab.grid_columnconfigure(i, weight=1)

        # ---------- REPORT FILTERS ----------
        tk.Label(report_tab, text="Month").grid(row=0, column=0, padx=5, pady=5)
        rep_month = ttk.Combobox(
            report_tab,
            values=[1,2,3,4,5,6,7,8,9,10,11,12],
            width=12,
            state="readonly"
        )
        rep_month.grid(row=0, column=1, padx=5)

        tk.Label(report_tab, text="Year").grid(row=0, column=2, padx=5)
        rep_year = ttk.Combobox(report_tab, values=[y for y in range(2022, 2035)],
                                width=10, state="readonly")
        rep_year.grid(row=0, column=3, padx=5)

        tk.Label(report_tab, text="Teacher").grid(row=0, column=4, padx=5)
        rep_teacher = ttk.Combobox(report_tab, width=15, state="readonly")
        rep_teacher.grid(row=0, column=5, padx=5)

        tk.Label(report_tab, text="Status").grid(row=0, column=6, padx=5)

        rep_status = ttk.Combobox(report_tab,
                                  values=["All","Paid","Unpaid"],
                                  width=12,
                                state="readonly")
        rep_status.grid(row=0, column=7, padx=5)
        rep_status.set("All")

        rep_month.set("")
        rep_year.set("")
        rep_teacher.set("")
        rep_status.set("")   # only if you are still using Paid/Unpaid

        def load_report_teachers():
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute("SELECT name FROM teachers WHERE active_status='ACTIVE'")
            names = [r[0] for r in c.fetchall()]
            conn.close()
            rep_teacher['values'] = ["All"] + names
            rep_teacher.set("All")

        load_report_teachers()

        def load_salary_report():
            rep_table.delete(*rep_table.get_children())

            m = rep_month.get()
            y = rep_year.get()
            t = rep_teacher.get()
            s = rep_status.get()

            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()

            # ===================== PAID TEACHERS =====================
            if s == "Paid" or s == "All":

                query = """
                SELECT t.name,
                       s.month,
                       s.year,
                       s.payable_salary,
                       s.paid_amount,
                       s.pending_amount,
                       s.payment_date
                FROM salary_payments s
                JOIN teachers t ON s.teacher_id = t.id
                WHERE 1 = 1
                """

                params = []

                if m:
                    query += " AND s.month = ?"
                    params.append(m)

                if y:
                    query += " AND s.year = ?"
                    params.append(y)

                # Apply teacher filter ONLY when not All
                if t and t != "All":
                    query += " AND t.name = ?"
                    params.append(t)

                c.execute(query, params)
                paid_rows = c.fetchall()

                for r in paid_rows:
                    rep_table.insert("", tk.END, values=r)

                if s == "Paid":
                    conn.close()
                    if not paid_rows:
                        messagebox.showinfo("Report", "No Paid Teachers Found")
                    return

            # ===================== UNPAID TEACHERS =====================
            if s == "Unpaid":

                # require month + year
                if not m or not y:
                    messagebox.showwarning("Required",
                                           "Please select Month & Year to check Unpaid teachers")
                    conn.close()
                    return

                c.execute("""
                SELECT name
                FROM teachers
                WHERE active_status='ACTIVE'
                AND id NOT IN (
                    SELECT teacher_id
                    FROM salary_payments
                    WHERE month = ? AND year = ?
                )
                """, (m, y))

                unpaid_list = c.fetchall()

                for r in unpaid_list:
                    rep_table.insert("", tk.END,
                                     values=(r[0], m, y, "-", "-", "-", "NOT PAID"))

                conn.close()

                if not unpaid_list:
                    messagebox.showinfo("Report", "No Unpaid Teachers Found")
                return

            conn.close()

            if not rep_table.get_children():
                messagebox.showinfo("Report", "No Salary Records Found")

        tk.Button(report_tab, text="Show Report",
                  bg="#27ae60", fg="white",
                  command=lambda: load_salary_report()
                  ).grid(row=0, column=8, padx=5)
        
        # ---------- REPORT TABLE ----------
        rep_table = ttk.Treeview(report_tab,
                                 columns=("T","M","Y","Payable","Paid","Pending","Date"),
                                 show="headings", height=14)
        rep_table.grid(row=1, column=0, columnspan=7, padx=10, pady=10, sticky="nsew")

        for col in ("T","M","Y","Payable","Paid","Pending","Date"):
            rep_table.heading(col, text=col)

        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas

        def export_salary_pdf():
            rows = rep_table.get_children()
            if not rows:
                messagebox.showwarning("Empty", "No report data to export")
                return

            filename = f"Salary_Report_{datetime.now().strftime('%H%M%S')}.pdf"
            cpdf = canvas.Canvas(filename, pagesize=letter)

            y = 750
            cpdf.setFont("Helvetica-Bold", 16)
            cpdf.drawString(180, 780, "Teacher Salary Report")
            cpdf.setFont("Helvetica", 10)

            for r in rows:
                data = rep_table.item(r)['values']
                line = f"{data[0]} | {data[1]} {data[2]} | Payable:{data[3]}  Paid:{data[4]}  Pending:{data[5]}"
                cpdf.drawString(40, y, line)
                y -= 18

                if y < 80:
                    cpdf.showPage()
                    y = 760

            cpdf.save()
            messagebox.showinfo("Saved", f"PDF Saved as {filename}")

        tk.Button(report_tab, text="Export PDF",
                  bg="#2980b9", fg="white",
                  command=export_salary_pdf
                  ).grid(row=2, column=0, pady=5)

        dashboard_tab = ttk.Frame(nb)

        tk.Label(dashboard_tab, text="Month").grid(row=0, column=3, padx=10)
        dash_month = ttk.Combobox(
            dashboard_tab,
            values=[1,2,3,4,5,6,7,8,9,10,11,12],
            width=10,
            state="readonly"
        )
        dash_month.grid(row=0, column=4)

        tk.Label(dashboard_tab, text="Year").grid(row=1, column=3, padx=10)
        dash_year = ttk.Combobox(
            dashboard_tab,
            values=[2024,2025,2026,2027],
            width=10,
            state="readonly"
        )
        dash_year.grid(row=1, column=4)

        dash_month.set(datetime.now().month)
        dash_year.set(datetime.now().year)

        dash_total = tk.StringVar()
        dash_paid = tk.StringVar()
        dash_pending = tk.StringVar()
        dash_teachers_paid = tk.StringVar()
        dash_unpaid = tk.StringVar()

        tk.Label(dashboard_tab, text="Total Payable:", font=("Arial",12)).grid(row=0,column=0,pady=10)
        tk.Label(dashboard_tab, textvariable=dash_total, font=("Arial",12,"bold")).grid(row=0,column=1)

        tk.Label(dashboard_tab, text="Total Paid:", font=("Arial",12)).grid(row=1,column=0)
        tk.Label(dashboard_tab, textvariable=dash_paid, font=("Arial",12,"bold")).grid(row=1,column=1)

        tk.Label(dashboard_tab, text="Total Pending:", font=("Arial",12)).grid(row=2,column=0)
        tk.Label(dashboard_tab, textvariable=dash_pending, font=("Arial",12,"bold")).grid(row=2,column=1)

        tk.Label(dashboard_tab, text="Teachers Paid:", font=("Arial",12)).grid(row=3,column=0)
        tk.Label(dashboard_tab, textvariable=dash_teachers_paid, font=("Arial",12,"bold")).grid(row=3,column=1)

        tk.Label(dashboard_tab, text="Unpaid Teachers:", font=("Arial",12)).grid(row=4,column=0)
        tk.Label(dashboard_tab, textvariable=dash_unpaid, font=("Arial",12,"bold")).grid(row=4,column=1)

        def load_salary_dashboard():
            m = dash_month.get()
            y = dash_year.get()

            if not m or not y:
                messagebox.showwarning("Required", "Please select Month & Year")
                return

            m = int(m)
            y = int(y)

            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()

            # ---------- MONTH-WISE TOTALS ----------
            c.execute("""
                SELECT 
                    IFNULL(SUM(payable_salary),0),
                    IFNULL(SUM(paid_amount),0),
                    IFNULL(SUM(pending_amount),0)
                FROM salary_payments
                WHERE month = ? AND year = ?
            """, (m, y))
    
            res = c.fetchone()
            dash_total.set(res[0])
            dash_paid.set(res[1])
            dash_pending.set(res[2])

            # ---------- ACTIVE TEACHERS ----------
            c.execute("SELECT COUNT(*) FROM teachers WHERE active_status='ACTIVE'")
            total_active = c.fetchone()[0]

            # ---------- TEACHERS PAID ----------
            c.execute("""
                SELECT COUNT(DISTINCT teacher_id)
                FROM salary_payments
                WHERE month = ? AND year = ? AND pending_amount = 0
            """, (m, y))
            fully_paid = c.fetchone()[0]
            dash_teachers_paid.set(fully_paid)

            # ---------- UNPAID TEACHERS ----------
            c.execute("""
                SELECT COUNT(*) 
                FROM teachers
                WHERE active_status='ACTIVE'
                AND id NOT IN (
                    SELECT teacher_id 
                    FROM salary_payments
                    WHERE month = ? AND year = ?
                )
            """, (m, y))

            unpaid = c.fetchone()[0]
            dash_unpaid.set(unpaid)

            conn.close()
            dash_month.bind("<<ComboboxSelected>>", lambda e: load_salary_dashboard())
            dash_year.bind("<<ComboboxSelected>>", lambda e: load_salary_dashboard())

        nb.add(report_tab, text="Salary Reports")
        nb.add(dashboard_tab, text="Dashboard")
        load_salary_dashboard()

        # ================= TAB 1 - TEACHER MASTER =================
        master_frame = tk.Frame(nb, bg="white")
        nb.add(master_frame, text="👨‍🏫 Teacher Master")

        tk.Label(master_frame, text="Teacher Name").grid(row=0, column=0, padx=5, pady=5)
        t_name = tk.Entry(master_frame)
        t_name.grid(row=0, column=1)

        tk.Label(master_frame, text="Designation").grid(row=1, column=0, padx=5, pady=5)
        t_des = tk.Entry(master_frame)
        t_des.grid(row=1, column=1)

        tk.Label(master_frame, text="Phone").grid(row=2, column=0, padx=5, pady=5)
        t_phone = tk.Entry(master_frame)
        t_phone.grid(row=2, column=1)

        tk.Label(master_frame, text="Base Salary").grid(row=3, column=0, padx=5, pady=5)
        t_salary = tk.Entry(master_frame)
        t_salary.grid(row=3, column=1)

        def clear_teacher_fields():
            t_name.delete(0, tk.END)
            t_des.delete(0, tk.END)
            t_phone.delete(0, tk.END)
            t_salary.delete(0, tk.END)

        def delete_teacher():
            selected = teacher_table.focus()
            if not selected:
                messagebox.showwarning("Select", "Please select a teacher to delete")
                return

            data = teacher_table.item(selected)['values']
            tid = data[0]
            name = data[1]

            confirm = messagebox.askyesno(
                "Confirm Delete",
                f"Do you really want to remove {name}?\n\n"
                "Note: Salary Data Will NOT Be Deleted."
            )
    
            if not confirm:
                return

            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()

            c.execute("""
                UPDATE teachers
                SET active_status = 'INACTIVE'
                WHERE id = ?
            """, (tid,))

            conn.commit()
            conn.close()

            load_teachers()
            load_teacher_dropdown()   # refresh Pay Salary dropdown
            messagebox.showinfo("Removed", f"{name} removed successfully")

        def save_teacher():
            name = t_name.get().strip()
            sal = t_salary.get().strip()

            if name == "" or sal == "":
                messagebox.showerror("Error", "Name & Salary Required")
                stay_on_current_tab()
                return
        
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute("""
                INSERT INTO teachers(name, designation, phone, join_date, base_salary)
                VALUES(?,?,?,?,?)
            """, (
                name,
                t_des.get(),
                t_phone.get(),
                datetime.now().strftime("%Y-%m-%d"),
                float(sal)
            ))
            conn.commit()
            conn.close()

            load_teachers()
            load_teacher_dropdown()  # 🔥 refresh Pay Salary dropdown
            messagebox.showinfo("Success", "Teacher Added")
        
        def activate_teacher():
            selected = teacher_table.focus()
            if not selected:
                messagebox.showwarning("Select", "Please select a teacher")
                return

            data = teacher_table.item(selected)['values']
            tid = data[0]
            name = data[1]

            confirm = messagebox.askyesno(
                "Confirm Restore",
                f"Do you want to activate {name} again?"
            )
            if not confirm:
                return

            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute("UPDATE teachers SET active_status='ACTIVE' WHERE id=?", (tid,))
            conn.commit()
            conn.close()

            load_teachers(show_inactive=True)
            load_teacher_dropdown()
            messagebox.showinfo("Restored", f"{name} activated successfully")

        tk.Button(master_frame, text="Save Teacher", bg="green", fg="white",
                  command=save_teacher).grid(row=5, column=1, pady=10)
        
        tk.Button(master_frame, text="Delete Teacher",
                  bg="orange", fg="white",
                  command=lambda: delete_teacher()).grid(row=5, column=2, pady=5)

        tk.Button(master_frame, text="Clear All", bg="red", fg="white",
                  command=clear_teacher_fields).grid(row=5, column=3, pady=5)
        
        tk.Button(master_frame, text="Activate Teacher",
                  bg="purple", fg="white",
                  command=activate_teacher).grid(row=5, column=4, padx=5)

        tk.Button(master_frame, text="Show Inactive",
                  bg="blue", fg="white",
                command=lambda: load_teachers(show_inactive=True)
        ).grid(row=5, column=5, padx=5)

        tk.Button(master_frame, text="Show Active",
                  bg="green", fg="white",
                  command=lambda: load_teachers(show_inactive=False)
        ).grid(row=5, column=6, padx=5)

        # ---- Teacher Table ----
        teacher_table = ttk.Treeview(
            master_frame, columns=("ID","Name","Salary","Status"),
            show="headings", height=12
        )
        teacher_table.grid(row=6, column=0, columnspan=5, padx=10, pady=10)

        for col in ("ID","Name","Salary","Status"):
            teacher_table.heading(col, text=col)

        def load_teachers(show_inactive=False):
            teacher_table.delete(*teacher_table.get_children())

            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()

            if show_inactive:
                c.execute("SELECT id,name,base_salary,active_status FROM teachers WHERE active_status='INACTIVE'")
            else:
                c.execute("SELECT id,name,base_salary,active_status FROM teachers WHERE active_status='ACTIVE'")

            for r in c.fetchall():
                teacher_table.insert("", tk.END, values=r)

            conn.close()

        load_teachers()

        # ================= TAB 2 - SALARY PAYMENT =================
        pay_frame = tk.Frame(nb, bg="white")
        nb.add(pay_frame, text="💰 Pay Salary")

        tk.Label(pay_frame, text="Select Teacher").grid(row=0, column=0, padx=5, pady=5)
        teacher_box = ttk.Combobox(pay_frame, width=25, state="readonly")
        teacher_box.grid(row=0, column=1)

        def load_teacher_dropdown():
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute("SELECT id,name FROM teachers WHERE active_status='ACTIVE'")
            data = c.fetchall()
            conn.close()

            teacher_box["values"] = [f"{i}-{n}" for i,n in data]

        load_teacher_dropdown()

        tk.Label(pay_frame, text="Month").grid(row=1, column=0)
        month_box = ttk.Combobox(pay_frame, values=[1,2,3,4,5,6,7,8,9,10,11,12], width=8, state="readonly")
        month_box.grid(row=1, column=1)

        tk.Label(pay_frame, text="Year").grid(row=2, column=0)
        year_box = ttk.Combobox(pay_frame, values=[2024,2025,2026,2027], width=8, state="readonly")
        year_box.grid(row=2, column=1)

        teacher_box.bind("<<ComboboxSelected>>", fetch_salary_for_payment)
        month_box.bind("<<ComboboxSelected>>", fetch_salary_for_payment)
        year_box.bind("<<ComboboxSelected>>", fetch_salary_for_payment)

        tk.Label(pay_frame, text="Salary").grid(row=3, column=0)
        base_entry = tk.Entry(pay_frame)
        base_entry.grid(row=3, column=1)

        tk.Label(pay_frame, text="Paid Amount").grid(row=4, column=0)
        paid_entry = tk.Entry(pay_frame)
        paid_entry.grid(row=4, column=1)

        tk.Label(pay_frame, text="Pending").grid(row=5, column=0)
        pend_entry = tk.Entry(pay_frame)
        pend_entry.grid(row=5, column=1)

        tk.Label(pay_frame, text="Payment Date").grid(row=6, column=0)

        date_entry = DateEntry(
            pay_frame,
            width=18,
            background="darkblue",
            foreground="white",
            borderwidth=2,
            date_pattern="yyyy-mm-dd"
        )
        date_entry.grid(row=6, column=1)

        # Auto fill today by default
        date_entry.set_date(datetime.now())

        def calc_pending(*args):
            try:
                base = float(base_entry.get())
                paid = float(paid_entry.get())
                pend = base - paid
                if pend < 0: pend = 0
                pend_entry.delete(0, tk.END)
                pend_entry.insert(0, pend)
            except:
                pass

        paid_entry.bind("<KeyRelease>", calc_pending)

        def save_salary():
            if not teacher_box.get() or not month_box.get() or not year_box.get():
                messagebox.showerror("Error", "Fill All Fields")
                return

            try:
                tid = int(teacher_box.get().split("-")[0])
                month = int(month_box.get())
                year = int(year_box.get())
                
                # The displayed_base is the amount AFTER recovery (e.g. 1396.33)
                displayed_base = float(base_entry.get() or 0)
                paid = float(paid_entry.get() or 0)
                pend = float(pend_entry.get() or 0)
            except ValueError:
                messagebox.showerror("Error", "Please enter valid numeric values")
                return

            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()

            try:
                # 1. Prevent Double Payment
                c.execute("SELECT COUNT(*) FROM salary_payments WHERE teacher_id=? AND month=? AND year=?", (tid, month, year))
                if c.fetchone()[0] > 0:
                    messagebox.showerror("Stop", "Salary Already Paid For This Month")
                    conn.close()
                    return

                # 2. Get the actual debt rows
                c.execute("""
                    SELECT id, share_amount, student_id FROM teacher_referral
                    WHERE teacher_id=? AND status='RECOVER_PENDING'
                    ORDER BY id ASC
                """, (tid,))
                rows = c.fetchall()
                total_debt_available = sum([r[1] for r in rows]) if rows else 0.0

                # Fetch actual salary (calculated or base)
                c.execute("""
                    SELECT calculated_salary FROM teacher_salary_calc
                    WHERE teacher_id=? AND month=? AND year=?
                """, (tid, month, year))
                tmp = c.fetchone()
                if tmp and tmp[0] is not None:
                    actual_salary = float(tmp[0])
                else:
                    c.execute("SELECT base_salary FROM teachers WHERE id=?", (tid,))
                    base_row = c.fetchone()
                    actual_salary = float(base_row[0]) if base_row else 0.0

                # Referral bonus (pending payouts)
                c.execute("""
                    SELECT IFNULL(SUM(share_amount), 0)
                    FROM teacher_referral
                    WHERE teacher_id = ? AND status='PENDING'
                """, (tid,))
                referral_bonus = float(c.fetchone()[0])

                total_earnings = actual_salary + referral_bonus

                # displayed_base is the amount shown in UI (salary after recovery)
                # So the actual recover that UI expects = total_earnings - displayed_base
                calculated_recover_from_ui = max(0.0, round(total_earnings - displayed_base, 2))

                # Final recover_this_month is limited by available debt
                recover_this_month = min(total_debt_available, calculated_recover_from_ui)

                # original_base_salary is simply total_earnings (salary before recovery)
                original_base_salary = total_earnings
                final_payable = displayed_base

                # ✅ VALIDATIONS (RIGHT HERE)
                if displayed_base > total_earnings:
                    raise ValueError("Final payable salary cannot exceed total earnings")

                if round(paid + pend, 2) != round(final_payable, 2):
                    raise ValueError("Paid + Pending must equal final payable salary")

                # -------- Insert main salary record (use original_base_salary, final_payable) --------
                c.execute("""
                    INSERT INTO salary_payments
                    (teacher_id, month, year, base_salary, payable_salary, paid_amount, pending_amount, payment_mode, payment_date)
                    VALUES (?,?,?,?,?,?,?,?,?)
                """, (tid, month, year, round(original_base_salary,2), round(final_payable,2), paid, pend, "Cash", date_entry.get()))
                salary_record_id = c.lastrowid

                # -------- Now deduct recover_this_month from RECOVER_PENDING rows in order --------
                remaining_to_deduct = recover_this_month
                for rid, amount, sid in rows:
                    if remaining_to_deduct <= 0:
                        break

                    # ✅ THIS LINE WAS MISSING
                    amount_to_take = min(remaining_to_deduct, amount)

                    new_amount = round(amount - amount_to_take, 2)

                    if new_amount <= 0.01:
                        c.execute("""
                            UPDATE teacher_referral
                            SET share_amount = 0,
                                status='RECOVERED',
                                recovery_applied=1,
                                recovery_salary_id=?
                            WHERE id=?
                        """, (salary_record_id, rid))
                        hist_status = "FULL"
                    else:
                        c.execute("""
                            UPDATE teacher_referral
                            SET share_amount = ?
                            WHERE id=?
                        """, (new_amount, rid))
                        hist_status = "PARTIAL"

                    # Log to History: recovered_amount and status (PARTIAL/FULL)
                    c.execute("""
                        INSERT INTO referral_recovery_history 
                        (teacher_id, referral_id, student_id, recovered_amount, month, year, salary_id, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (tid, rid, sid, amount_to_take, month, year, salary_record_id, hist_status))

                    remaining_to_deduct = round(remaining_to_deduct - amount_to_take, 2)

                # 6. Mark Bonuses as Paid
                # ✅ Mark bonuses PAID ONLY if some salary was actually paid
                if paid > 0:
                    c.execute("""
                        UPDATE teacher_referral
                        SET status='PAID',
                            paid_month=?
                        WHERE teacher_id=?
                        AND status='PENDING'
                        AND IFNULL(share_amount,0) > 0
                    """, (f"{month}-{year}", tid))

                conn.commit()
                add_salary_audit("SALARY_PAID", f"Teacher:{tid} | Net:{final_payable} | Recovery:{recover_this_month}")
                messagebox.showinfo("Success", "Salary Saved Successfully")

            except Exception as e:
                conn.rollback()
                messagebox.showerror("Database Error", str(e))
            finally:
                conn.close()
                load_salary_history()
                load_salary_dashboard()

        def open_recovery_history():
            win = tk.Toplevel()
            win.title("Referral Recovery History")
            win.geometry("850x450") # Slightly wider for better visibility
            win.grab_set()

            # Columns to show the summary effectively
            cols = ("Teacher", "Student ID", "Recovered", "Status", "Applied Month", "Salary ID")
            table = ttk.Treeview(win, columns=cols, show="headings", height=15)
            table.pack(fill="both", expand=True, padx=10, pady=10)

            for col in cols:
                table.heading(col, text=col)
                table.column(col, width=120, anchor="center")

            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()

            c.execute("""
            SELECT 
                t.name,
                r.student_id,
                r.recovered_amount,
                r.status,
                r.month || '-' || r.year as period,
                r.salary_id
            FROM referral_recovery_history r
            LEFT JOIN teachers t ON r.teacher_id = t.id
            ORDER BY r.id DESC
            """)

            rows = c.fetchall()
            conn.close()

            for r in rows:
                table.insert("", tk.END, values=r)

        def clear_salary_fields():
            teacher_box.set("")
            month_box.set("")
            year_box.set("")
            base_entry.delete(0, tk.END)
            paid_entry.delete(0, tk.END)
            pend_entry.delete(0, tk.END)
            date_entry.set_date(datetime.now())

        tk.Button(pay_frame, text="Save Salary", bg="green", fg="white",
                  command=save_salary).grid(row=8, column=1, pady=10)
        
        tk.Button(pay_frame, text="Clear All", 
          bg="red", fg="white",
          command=lambda: clear_salary_fields()
          ).grid(row=8, column=4, pady=10, padx=10)
        
        tk.Button(pay_frame,
                  text="Referral Management",
                  bg="#8e44ad",
                  fg="white",
                  font=("Arial",11,"bold"),
                command=lambda: open_referral_window()
        ).grid(row=9, column=1, pady=10)

        tk.Button(pay_frame,
                  text="Referral History",
                  bg="#2c3e50",
                  fg="white",
                  font=("Arial",11,"bold"),
                  command=open_referral_history
        ).grid(row=10, column=1, pady=10)

        tk.Button(pay_frame,
                  text="Recovery History",
                  bg="#34495e",
                  fg="white",
                  font=("Arial",11,"bold"),
                  command=open_recovery_history
        ).grid(row=11, column=1, pady=10)
       
        # ================= TAB 3 - SALARY HISTORY =================
        hist_frame = tk.Frame(nb, bg="white")
        nb.add(hist_frame, text="📜 Salary History")

        salary_table = ttk.Treeview(
            hist_frame,
            columns=("ID","Teacher","Month","Year","Payable","Paid","Pending","Date"),
            show="headings", height=14
        )
        salary_table.pack(fill="both", padx=10, pady=10)

        payment_history = ttk.Treeview(
        hist_frame,
        columns=("Amount","Date","Mode","Note"),
        show="headings",
        height=8
        )
        payment_history.pack(fill="x", padx=10, pady=5)

        for h in ("Amount","Date","Mode","Note"):
            payment_history.heading(h, text=h)

        for c in ("ID","Teacher","Month","Year","Payable","Paid","Pending","Date"):
            salary_table.heading(c, text=c)
            salary_table.heading("Date", text="Payment Date")

        def delete_salary_record():
            selected = salary_table.focus()
            if not selected:
                messagebox.showwarning("Select", "Please select a salary record to delete")
                return

            data = salary_table.item(selected)['values']
            rec_id = data[0]
            teacher = data[1]
            month = data[2]
            year = data[3]

            confirm = messagebox.askyesno(
                "Confirm Delete",
                f"Do you really want to delete salary record?\n\n"
                f"Teacher: {teacher}\nMonth: {month}-{year}"
            )
            if not confirm:
                return

            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()

            # 🔹 Get teacher_id BEFORE deleting salary
            c.execute("SELECT teacher_id FROM salary_payments WHERE id=?", (rec_id,))
            row = c.fetchone()
            teacher_id = row[0] if row else None

            # 🔹 Delete partial payments first
            c.execute("DELETE FROM salary_transactions WHERE salary_id=?", (rec_id,))

            # 🔹 Delete salary record
            c.execute("DELETE FROM salary_payments WHERE id=?", (rec_id,))

            # 🔹 Restore referrals to PENDING (because salary removed)
            
            # -------- REFERRAL RECOVERY ROLLBACK SAFELY --------
            if teacher_id:

                # 1️⃣ Get all recovered referrals linked to this salary
                c.execute("""
                SELECT id FROM teacher_referral
                WHERE teacher_id=?
                AND status='RECOVERED'
                AND recovery_applied=1
                AND recovery_salary_id=?
                """, (teacher_id, rec_id))

                recovered = c.fetchall()

                # 2️⃣ If recovery was really deducted → restore to PENDING
                if recovered:
                    c.execute("""
                    UPDATE teacher_referral
                    SET status='RECOVER_PENDING',
                        paid_month=NULL,
                        recovery_applied=0,
                        recovery_salary_id=NULL
                    WHERE teacher_id=?
                    AND recovery_salary_id=?
                    """, (teacher_id, rec_id))

                # 3️⃣ If salary never had recovery — do nothing

            conn.commit()

            add_salary_audit(
                "SALARY_DELETED",
                f"Teacher:{teacher} | Month:{month} | Year:{year} | SalaryID:{rec_id}"
            )

            conn.close()

            load_salary_history()
            load_salary_dashboard()
            load_salary_report()

            nb.after(100, lambda: nb.select(hist_frame))

            messagebox.showinfo("Deleted", "Salary record deleted successfully")

        def load_salary_history():
            salary_table.delete(*salary_table.get_children())

            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute("""
                SELECT s.id, t.name, s.month, s.year,
                       s.payable_salary, s.paid_amount, s.pending_amount, s.payment_date
                FROM salary_payments s
                JOIN teachers t ON s.teacher_id = t.id
                ORDER BY s.id DESC
            """)

            for r in c.fetchall():
                salary_table.insert("", tk.END, values=r)

            conn.close()
        load_salary_history()    
        
        tk.Button(hist_frame, text="Pay Remaining Salary",
        bg="#27ae60", fg="white",
        command=lambda: pay_remaining()).pack(pady=5)

        tk.Button(
            hist_frame,
            text="Delete Salary Record",
            bg="red",
            fg="white",
            command=lambda: delete_salary_record()
        ).pack(pady=5)

        tk.Button(
            hist_frame,
            text="Delete Partial Payment",
            bg="orange",
            fg="white",
            command=lambda: delete_partial_payment()
        ).pack(pady=5)

        def load_payment_timeline():
            payment_history.delete(*payment_history.get_children())
    
            selected = salary_table.focus()
            if not selected:
                return

            data = salary_table.item(selected)['values']
            salary_id = data[0]

            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()

            c.execute("""
                SELECT pay_amount, pay_date, payment_mode, IFNULL(note,'')
                FROM salary_transactions
                WHERE salary_id = ?
                ORDER BY id ASC
            """, (salary_id,))

            for r in c.fetchall():
                payment_history.insert("", tk.END, values=r)

            conn.close()

        salary_table.bind("<<TreeviewSelect>>", lambda e: load_payment_timeline())

        def pay_remaining():
            selected = salary_table.focus()
            if not selected:
                messagebox.showwarning("Select", "Please select a record")
                return

            data = salary_table.item(selected)['values']
            rec_id = data[0]
            payable = float(data[4])
            paid = float(data[5])
            pending = float(data[6])

            if pending <= 0:
                messagebox.showinfo("Done", "No pending salary for this teacher")
                return

            # Ask how much user is paying now
            amount = simpledialog.askfloat(
                "Pay Remaining",
                f"Pending ₹{pending}\n\nEnter amount to pay:",
                minvalue=1.0
            )

            if amount is None:
                return

            if amount > pending:
                messagebox.showerror("Invalid", "Amount cannot be greater than pending")
                stay_on_current_tab()
                return

            new_paid = paid + amount
            new_pending = pending - amount

            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()

            c.execute("""
                UPDATE salary_payments
                SET paid_amount = ?, pending_amount = ?
                WHERE id = ?
            """, (new_paid, new_pending, rec_id))

            # fetch teacher id
            c.execute("SELECT teacher_id FROM salary_payments WHERE id = ?", (rec_id,))
            teacher_id = c.fetchone()[0]

            note = "Partial Payment"
            if new_pending == 0:
                note = "Salary Fully Paid"

            c.execute("""
            INSERT INTO salary_transactions
            (salary_id, teacher_id, pay_amount, pay_date, payment_mode, note)
            VALUES(?,?,?,?,?,?)
            """, (
                rec_id,
                teacher_id,
                amount,
                datetime.now().strftime("%Y-%m-%d"),
                "Cash",
                "Partial Payment"  
            ))

            conn.commit()
            conn.close()

            # =============== AUDIT LOG ===============
            if new_pending == 0:
                add_salary_audit(
                    "SALARY_FULLY_PAID",
                    f"Teacher:{data[1]} | Total Paid:{new_paid} | Month:{data[2]}-{data[3]}"
                )
            else:
                add_salary_audit(
                    "SALARY_PART_PAYMENT",
                    f"Teacher:{data[1]} | Amount:{amount} | Remaining:{new_pending} | SalaryID:{rec_id}"
                )
            # =========================================

            load_salary_history()
            load_salary_dashboard()
            load_salary_report()

            nb.after(100, lambda: nb.select(hist_frame))

            current_tab = nb.index("current")

            if new_pending == 0:
                messagebox.showinfo("Success", "Salary Fully Paid 🎉")
            else:
                messagebox.showinfo("Success", f"Payment Updated\nRemaining ₹{new_pending}")

            win.after(50, lambda: nb.select(current_tab))

        def delete_partial_payment():
            selected_salary = salary_table.focus()
            if not selected_salary:
                messagebox.showwarning("Select", "Please select a salary record first")
                return

            salary_data = salary_table.item(selected_salary)['values']
            salary_id = salary_data[0]

            selected_payment = payment_history.focus()
            if not selected_payment:
                messagebox.showwarning("Select", "Please select a partial payment to delete")
                return

            pay_data = payment_history.item(selected_payment)['values']
            pay_amount = float(pay_data[0])
            pay_date = pay_data[1]

            confirm = messagebox.askyesno(
                "Confirm Delete",
                f"Delete this partial payment?\n\n"
                f"Amount: ₹{pay_amount}\nDate: {pay_date}"
            )

            if not confirm:
                return

            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()

           # Find exact transaction row
            c.execute("""
                SELECT id FROM salary_transactions
                WHERE salary_id = ? AND pay_amount = ? AND pay_date = ?
                ORDER BY id ASC
                LIMIT 1
            """, (salary_id, pay_amount, pay_date))

            row = c.fetchone()
            if not row:
                conn.close()
                messagebox.showerror("Error", "Could not find this partial payment record")
                return

            txn_id = row[0]

            # Delete that transaction only
            c.execute("DELETE FROM salary_transactions WHERE id = ?", (txn_id,))

            # 2️⃣ update main salary record
            c.execute("""
                UPDATE salary_payments
                SET paid_amount = paid_amount - ?,
                    pending_amount = pending_amount + ?
                WHERE id = ?
            """, (pay_amount, pay_amount, salary_id))

            conn.commit()
            add_salary_audit(
                "SALARY_PART_PAYMENT_DELETED",
                f"SalaryID:{salary_id} | Amount:{pay_amount} | Date:{pay_date}"
            )

            conn.close()

            load_salary_history()
            load_salary_dashboard()
            load_salary_report()

            nb.after(100, lambda: nb.select(hist_frame))

            messagebox.showinfo("Deleted", "Partial payment removed successfully")

    def add_sibling():
        global siblings, purpose_items, sibling_mode, current_family_id

        if not sibling_mode:
            messagebox.showwarning("Sibling Mode", "Enable Sibling Mode first")
            return

        name = name_entry.get().strip()
        s_class = entry_class_box.get().strip()

        if not name or not purpose_items:
            messagebox.showwarning("Logic Error", "Enter Name and add items first!")
            return

        # 🔐 Generate family only ONCE
        if not current_family_id:
            current_family_id = str(uuid.uuid4())[:8]

        # ---- READ REFERRAL ----
        sibling_referral = referral_entry.get().strip() or None

        # 2. Package child with family_id
        new_sibling = {
            "name": name,
            "class": s_class,
            "items": list(purpose_items),
            "referral": sibling_referral,
            "family_id": current_family_id    # 🔥 FIX
        }

        # 3. Save
        siblings.append(new_sibling)

        # 4. Reset UI for next child
        purpose_items.clear()
        name_entry.delete(0, tk.END)
        purpose_var.set("")
        entry_class_box.set("")
        refresh_referral_box()
        referral_entry.delete(0, tk.END)
        referral_entry.config(state="disabled")

        # 5. Update UI
        update_sibling_status()
        update_family_total()

        messagebox.showinfo("Added", f"{name} added to the sibling group.")

    def remove_purpose_item():
        global purpose_items, siblings, sibling_mode

        # Use the list directly instead of trying to parse text from the screen
        if not purpose_items:
            messagebox.showinfo("No Items", "No purpose items to manage.")
            return

        popup = tk.Toplevel(root)
        popup.title("Manage Purpose Items")
        popup.geometry("450x400")
        popup.resizable(False, False)
        popup.transient(root)
        popup.grab_set()

        frame = tk.Frame(popup)
        frame.pack(pady=10, fill="both", expand=True)

        columns = ("Purpose", "Price")
        tv = ttk.Treeview(frame, columns=columns, show="headings", height=10)
        tv.pack(side="left", padx=5)

        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tv.yview)
        scrollbar.pack(side="right", fill="y")
        tv.configure(yscrollcommand=scrollbar.set)

        tv.heading("Purpose", text="Purpose")
        tv.heading("Price", text="Price (Rs.)")
        tv.column("Purpose", width=250)
        tv.column("Price", width=100, anchor="center")

        undo_stack = []

        def refresh_tree():
            tv.delete(*tv.get_children())
            for n, p in purpose_items:
                tv.insert("", "end", values=(n, f"{p:.2f}"))

        refresh_tree()


        # ---------- INTERNAL HELPER: SYNC CHANGES ----------
        def apply_changes():
            # Update the total calculation and UI preview
            update_family_total()
            refresh_tree()
            refresh_referral_box()

        # ---------- REMOVE SELECTED ----------
        def remove_selected():
            selected = tv.selection()
            if not selected:
                messagebox.showwarning("Select", "Please select an item to remove.")
                return
    
            idx = tv.index(selected[0])
            removed_item = purpose_items.pop(idx)

            undo_stack.append({
                "type": "single",
                "data": (idx, removed_item)
            })

            apply_changes()
            refresh_referral_box()
            messagebox.showinfo("Removed", "Item removed successfully.")

        # ---------- CLEAR ALL ----------
        def clear_all():
            if not purpose_items:
                return

            if messagebox.askyesno("Confirm", "Remove ALL items for this student?"):
        
                backup = [(i, it) for i, it in enumerate(purpose_items.copy())]

            undo_stack.append({
                "type": "all",
                "data": backup
            })

            purpose_items.clear()
            apply_changes()
            refresh_referral_box()

        def undo_delete():
            if not undo_stack:
                messagebox.showinfo("Undo", "Nothing to restore.")
                return

            action = undo_stack.pop()

            # Restore ALL
            if action["type"] == "all":
                for idx, item in sorted(action["data"], key=lambda x: x[0]):
                    purpose_items.insert(idx, item)

                messagebox.showinfo("Undo", "All cleared items restored successfully.")

            # Restore ONE
            elif action["type"] == "single":
                idx, item = action["data"]
                purpose_items.insert(idx, item)

                messagebox.showinfo("Undo", f"Restored: {item[0]}")

            apply_changes()
            refresh_referral_box()

        # ---------- BUTTONS ----------
        btn_frame = tk.Frame(popup)
        btn_frame.pack(pady=10)

        tk.Button(btn_frame, text="Remove Selected", bg="red", fg="white", 
                  width=15, command=remove_selected).grid(row=0, column=0, padx=5)
    
        tk.Button(btn_frame, text="Clear All", bg="orange", 
                  width=15, command=clear_all).grid(row=0, column=1, padx=5)
    
        tk.Button(btn_frame, text="Close", width=15, 
                  command=popup.destroy).grid(row=0, column=2, padx=5)
        
        tk.Button(btn_frame, text="Undo Delete", bg="#6C3483", fg="white",
          width=15,
          command=lambda: undo_delete()).grid(row=1, column=0, padx=5, pady=5)

    def logout():
        if messagebox.askyesno("Logout","Are you sure?"):
            perform_backup(user_role)
            add_audit("LOGOUT",f"{user_role} logged out.")
            root.destroy()
            show_login_screen()

    def update_total_from_string():
    
        import re
        text = purpose_var.get()
        # This regex finds numbers inside parentheses, e.g., (1500.00)
        prices = re.findall(r'\(([\d\.]+)\)', text)
        total_sum = sum(float(p) for p in prices)
    
        total_entry.delete(0, tk.END)
        total_entry.insert(0, f"{total_sum:.2f}")

    def on_closing():
        if messagebox.askyesno("Exit","Exit and backup data?"):
            perform_backup(user_role)
            root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_closing)

    def auto_calculate_total(*args):
        try:
            total_entry.delete(0, tk.END)
            total_entry.insert(0, calculate_sibling_total())
        except:
            total_entry.delete(0, tk.END)
            total_entry.insert(0, "0")

    def ask_month_dialog():
        win = tk.Toplevel(root)
        win.title("Select Month")
        win.geometry("250x150")
        win.grab_set()

        tk.Label(win, text="Select Month:", font=("Arial", 11)).pack(pady=8)

        months = [
            "January","February","March","April","May","June",
            "July","August","September","October","November","December"
        ]

        month_var = tk.StringVar()
        month_box = ttk.Combobox(win, textvariable=month_var, values=months, state="readonly", width=18)
        month_box.pack(pady=5)
        month_box.current(0)

        selected = {"value": None}

        def ok():
            selected["value"] = month_var.get()
            win.destroy()

        ttk.Button(win, text="OK", command=ok).pack(pady=5)

        win.wait_window()
        return selected["value"]

    def handle_referral_enable(event=None):
        purpose = purpose_var.get().lower()

        if "admission" in purpose:
            referral_entry.config(state="normal")
        else:
            referral_entry.delete(0, tk.END)
            referral_entry.config(state="disabled")
        refresh_referral_box()

    def handle_selection(event):
        global purpose_items, siblings, sibling_mode
        selected_item = purpose_entry.get()

        if selected_item == "Other":
            ask_other_purpose()
            return

        # 1. PREVENT DUPLICATE BALANCE CHECK (Only check current student)
        in_current = any(n.lower() == "balance" for n, _ in purpose_items)
    
        if selected_item == "Balance" and in_current:
            messagebox.showerror("Error", "Balance already added for this student!")
            return

        # 2. GET THE PRICE/AMOUNT
        if selected_item == "Balance":
            # We use your existing function to look up the balance from the DB
            price = fill_balance_if_needed(event)
            if price is None: 
                return 
            if price <= 0: 
                messagebox.showinfo("Info", "No outstanding balance found.")
                return
    
        elif selected_item == "Monthly Fee":
            month = ask_month_dialog()
            if not month: return
            price = simpledialog.askfloat("Monthly Fee", f"Enter Fee for {month}:", minvalue=0.0, parent=root)
            if price is None: return
            selected_item = f"Monthly Fee - {month}"
    
        else:
            price = simpledialog.askfloat("Price", f"Enter price for {selected_item}:", minvalue=0.0)
            if price is None: return

        # 3. ADD TO CURRENT ITEMS (This fixes the crash!)
        # Whether in sibling mode or normal mode, we add to purpose_items FIRST.
        purpose_items.append((selected_item, price))
        update_purpose_display()
        # 4. UPDATE THE DISPLAY
        # Show what is currently being added for the student on screen
        current_display = [f"{n} ({p:.2f})" for n, p in purpose_items]
        purpose_var.set(", ".join(current_display))

        # 5. RECALCULATE TOTALS
        # This calls your function that sums up the queue + current screen
        update_family_total()

    def resource_path():
        if hasattr(sys, "_MEIPASS"):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))

    #-------NEW_FAMILY_RECEIPT_LOGIC------------------
    def generate_thermal_receipt():
        if not selected_record_id.get():
            messagebox.showwarning("Select", "Select a record first.")
            return

        # ---- FETCH SELECTED RECORD ----
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()

        c.execute("""
            SELECT name, student_class, family_id, receipt_batch_id
            FROM students 
            WHERE id=?
        """, (selected_record_id.get(),))

        row = c.fetchone()

        if not row:
            conn.close()
            messagebox.showerror("Error", "Record not found!")
            return

        student_name, s_class, family_id, batch_id = row

        # ------------------------------------------------
        #  CASE-1 → NO FAMILY ID → PRINT NORMAL RECEIPT
        # ------------------------------------------------
        if not family_id or family_id == "None":
            conn.close()
            return generate_single_student_receipt()   # <-- your old function moved below

        # ------------------------------------------------
        #  CASE-2 → FAMILY RECEIPT
        # ------------------------------------------------
        c.execute("""
            SELECT id, name, student_class, purpose, total, paid, balance, payment_mode,
                   date_added, receipt_no
            FROM students
            WHERE family_id = ?
            AND receipt_batch_id = ?
            ORDER BY id
        """, (family_id, batch_id))

        records = c.fetchall()
        if not records:
            conn.close()
            messagebox.showerror("Error", "No family records found!")
            return
        unique_students = len({r[1] for r in records})   # r[1] = name column

        family_total = 0
        family_paid = 0

        for r in records:
            total = float(r[4] or 0)
            paid = float(r[5] or 0)
            family_total += total
            family_paid += paid

        # ------------------------------------------------
        #  GET FAMILY CREDIT WALLET
        # ------------------------------------------------
        c.execute("SELECT credit_wallet FROM family_accounts WHERE family_id=?", (family_id,))
        row = c.fetchone()
        family_credit = row[0] if row else 0

        # -------- FINAL PENDING BALANCE (ERP LOGIC) --------
        family_bal = float(records[-1][6] or 0)

        # -------- SHARED RECEIPT NUMBER ----------
        # Generate shared receipt number if missing
        family_receipt = None
        for r in records:
            if r[9] and r[9] != "None":
                family_receipt = r[9]
                break

        if not family_receipt:
            family_receipt = get_next_receipt_no()
            for r in records:
                c.execute("UPDATE students SET receipt_no=? WHERE id=?", (family_receipt, r[0]))
            conn.commit()

        conn.close()

        pay_mode = records[0][7] or "Cash"
        dt = datetime.now().strftime("%d/%m/%Y")
        tm = datetime.now().strftime("%I:%M %p")

        # --------- DYNAMIC HEIGHT ---------
        line_height = 16
        extra_height = len(records) * 70     # each student section height approx
        total_height = 500 + extra_height

        # ---------- SAVE IN RECEIPTS FOLDER ----------
        base_path = resource_path()

        RECEIPT_FOLDER = os.path.join(base_path, "Receipts")

        if not os.path.exists(RECEIPT_FOLDER):
             os.makedirs(RECEIPT_FOLDER)

        filename = os.path.join(
            RECEIPT_FOLDER,
            f"Receipt_{family_id}_{datetime.now().strftime('%H%M%S')}.pdf"
        )

        cpdf = canvas.Canvas(filename, pagesize=(216, total_height))

        y = total_height - 40

        # -------- HEADER --------
        logo = "logo.png"
        if os.path.exists(logo):
            logo_w = 120
            logo_h = 120
            cpdf.drawImage(logo, (216-logo_w)/2, y-120, width=logo_w, height=logo_h, mask='auto')
            y -= 120

        cpdf.setFont("Helvetica-Bold", 14)
        cpdf.drawCentredString(108, y, "RECEIPT")
        y -= 18
        cpdf.setFont("Helvetica", 9)
        cpdf.drawCentredString(108, y, "-------------------------------------------")
        y -= 20

        cpdf.drawString(20, y, f"Date: {dt}")
        cpdf.drawRightString(195, y, f"Time: {tm}")
        y -= 14

        cpdf.drawString(20, y, f"Family ID: {family_id}")
        y -= 14
        cpdf.drawString(20, y, f"Receipt No: {family_receipt}")
        y -= 14
        cpdf.drawString(20, y, f"Mode: {pay_mode}")
        y -= 18

        # -------- TABLE HEADER --------
        cpdf.setFont("Helvetica-Bold", 9)
        cpdf.drawString(20, y, "Student / Class")
        cpdf.drawRightString(195, y, "Totals")
        y -= 12
        cpdf.drawString(20, y, "-------------------------------------------")
        y -= 18

        cpdf.setFont("Helvetica", 9)

        # -------- EACH STUDENT --------
        for r in records:
            _, nm, cls, purpose, total, paid, bal, *_ = r

            cpdf.setFont("Helvetica-Bold", 9)
            cpdf.drawString(20, y, f"{nm} ({cls})")
            y -= 14
            cpdf.setFont("Helvetica", 9)

            # break purposes to lines
            raw_items = [i.strip() for i in purpose.split(",") if i.strip()]

            for item in raw_items:
                if "(" in item and ")" in item:
                    p = item.split("(")[0].strip()
                    amt = item.split("(")[1].replace(")", "").strip()
                else:
                    p = item
                    amt = "0.00"

                cpdf.drawString(25, y, f"- {p}")
                cpdf.drawRightString(195, y, f"{amt}")
                y -= 12

            cpdf.drawString(20, y, f"Total: {total:.2f}   Paid: {paid:.2f}   Bal: {bal:.2f}")
            y -= 18
            cpdf.drawString(20, y, "-------------------------------------------")
            y -= 18

        # -------- FAMILY TOTALS --------
        cpdf.setFont("Helvetica-Bold", 10)
        cpdf.drawString(20, y, f"TOTAL: Rs {family_total:.2f}")
        y -= 16

        cpdf.drawString(20, y, f"PAID TODAY: Rs {family_paid:.2f}")
        y -= 16

        cpdf.drawString(20, y, f"PENDING BALANCE: Rs {family_bal:.2f}")
        y -= 16

        # -------- SHOW CREDIT WALLET ONLY IF EXISTS --------
        if family_credit > 0:
            cpdf.setFillColorRGB(0, 0.6, 0)
            cpdf.drawString(20, y, f"ADVANCE CREDIT AVAILABLE: Rs {family_credit:.2f}")
            cpdf.setFillColorRGB(0, 0, 0)
            y -= 20

        y -= 20

        sig = "signature.png"
        if os.path.exists(sig):
            cpdf.drawImage(sig, 80, y, width=90, height=40, mask='auto')
            y -= 10

        cpdf.setFont("Helvetica", 8)
        cpdf.drawCentredString(108, y, "Authorised Signature")
        y -= 20

        cpdf.setFont("Helvetica-Oblique", 9)
        cpdf.drawCentredString(108, y, "Thank you for your payment!")

        cpdf.save()
        messagebox.showinfo("Saved", f"Family Receipt Saved:\n{filename}")

        try:
            add_audit(
                "RECEIPT",
                f"{user_role} PRINTED FAMILY RECEIPT | Family ID: {family_id} | "
                f"Students: {unique_students} | Total:{family_total} | "
                f"Paid:{family_paid} | Bal:{family_bal} | Credit:{family_credit}"
            )
        except:
            pass

    # ---------- RECEIPT PRINT ----------
    def generate_single_student_receipt():
        # paste YOUR OLD generate_thermal_receipt() code here
        if not selected_record_id.get():
            messagebox.showwarning("Select", "Select a record first.")
            return
        
        student_id = selected_record_id.get()

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()

        c.execute("""
            SELECT name, student_class, purpose, total, paid, balance,
                   payment_mode, receipt_no, receipt_batch_id
            FROM students
            WHERE id = ?
        """, (student_id,))

        # 🔥 Get true running balance for this student (ledger truth)
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("""
            SELECT balance
            FROM students
            WHERE name=? AND student_class=?
            ORDER BY id DESC
            LIMIT 1
        """, (name, s_class))

        row2 = c.fetchone()
        conn.close()

        true_balance = float(row2[0] or 0) if row2 else 0

        if not row:
            messagebox.showerror("Error", "Student record not found.")
            return

        name, s_class, purpose_str, total, paid, balance, pay_mode, receipt_no, batch_id = row

        # ensure receipt number
        if not receipt_no or receipt_no == "None":
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            receipt_no = get_next_receipt_no()
            c.execute("UPDATE students SET receipt_no=? WHERE id=?", (receipt_no, student_id))
            conn.commit()
            conn.close()

        try:
            balance = float(balance or 0)
            now = datetime.now()
            dt, tm = now.strftime("%d/%m/%Y"), now.strftime("%I:%M %p")
            filename = f"Receipt_{name}_{now.strftime('%H%M%S')}.pdf"

            # Dynamic Height Calculation based on number of items
            raw_items = [i.strip() for i in purpose_str.split(",") if i.strip()]
            row_height = 16                     # safer line spacing
            extra_height = len(raw_items) * row_height

            footer_space = 160                  # space for totals + signature + margin

            base_height = 420                   # base paper height
            total_height = base_height + extra_height + footer_space

            cpdf = canvas.Canvas(filename, pagesize=(216, total_height))

            # --- HEADER ---
            logo_path = "logo.png"
            y = total_height - 60

            if os.path.exists(logo_path):
                logo_w = 120
                logo_h = 120
                center_x = (216 - logo_w) / 2       # PERFECT CENTER FOR THERMAL WIDTH

                cpdf.drawImage(
                    logo_path,
                    center_x,
                    y - 120,
                    width=logo_w,
                    height=logo_h,
                    mask='auto'
                )

                y -= 110

            # Title
            cpdf.setFont("Helvetica-Bold", 14)
            cpdf.drawCentredString(108, y, "RECEIPT")
            y -= 10
            cpdf.setFont("Helvetica", 9)
            cpdf.drawCentredString(108, y, "-------------------------------------------")
            y -= 25


            # ---------- STUDENT INFO ----------
            cpdf.setFont("Helvetica-Bold", 9)
            cpdf.drawString(20, y, f"Date: {dt}")
            cpdf.drawRightString(195, y, f"Time: {tm}")
            y -= 15

            cpdf.drawString(20, y, f"Receipt No: {receipt_no}")
            y -= 15

            cpdf.drawString(20, y, f"Mode: {pay_mode or 'Cash'}")
            y -= 18

            cpdf.setFont("Helvetica", 10)
            cpdf.drawString(20, y, f"Student: {name}")
            y -= 15

            cpdf.drawString(20, y, f"Class: {s_class}")

            # ---------- ITEM TABLE ----------
            y -= 25
            cpdf.setFont("Helvetica-Bold", 9)
            cpdf.drawString(20, y, "S#")
            cpdf.drawString(50, y, "Item Description")
            cpdf.drawRightString(195, y, "Price")
            y -= 8
            cpdf.drawString(20, y, "-------------------------------------------")
            y -= 15

            cpdf.setFont("Helvetica", 9)

            for idx, raw_item in enumerate(raw_items, 1):
                if "(" in raw_item and ")" in raw_item:
                    name_part = raw_item.split("(")[0].strip()
                    price_part = raw_item.split("(")[1].replace(")", "").strip()
                else:
                    name_part = raw_item
                    price_part = "0.00"

                cpdf.drawString(20, y, f"{idx}.")
                cpdf.drawString(50, y, name_part)

                try:
                    cpdf.drawRightString(195, y, f"{float(price_part):.2f}")
                except:
                    cpdf.drawRightString(195, y, "0.00")

                y -= 14


            # ---------- TOTALS ----------
            cpdf.drawString(20, y, "-------------------------------------------")
            y -= 18

            cpdf.setFont("Helvetica-Bold", 10)
            cpdf.drawString(20, y, f"Total Amount: Rs. {total:.2f}")
            y -= 18

            cpdf.drawString(20, y, f"Amount Paid: Rs. {paid:.2f}")
            y -= 18

            cpdf.setFillColorRGB(1, 0, 0)
            cpdf.drawString(20, y, f"Balance: Rs. {true_balance:.2f}")
            cpdf.setFillColorRGB(0, 0, 0)
            y -= 40

            # ---------- SIGNATURE ----------
            sig = "signature.png"
            if os.path.exists(sig):
                cpdf.drawImage(sig, 90, y, width=90, height=40, mask='auto')
                y -= 10

            cpdf.setFont("Helvetica", 8)
            cpdf.drawCentredString(108, y, "Authorised Signature")
            y -= 25

            cpdf.setFont("Helvetica-Oblique", 9)
            cpdf.drawCentredString(108, y, "Thank you for your payment!")

            cpdf.save()
            messagebox.showinfo("Saved", f"Receipt Saved:\n{filename}")

        except Exception as e:
            messagebox.showerror("Error", f"Receipt failed\n{e}")


        # 1. This variable acts as a short-term memory
        global previous_text
        previous_text = ""
        purpose_items = []

    def capture_current_text(event):
        """Remembers what is in the box before the user picks a new item."""
        global previous_text
        previous_text = purpose_var.get()

    def handle_multi_select():
        current_val = purpose_var.get()
        # If the user just selected an item, and it's already in the string, 
        # we check if we need to add a comma for the next one.
        if current_val:
            # Check if the string already ends with a comma or is empty
            if not current_val.strip().endswith(","):
                purpose_var.set(current_val + ", ")
                # Move cursor to the end
                purpose_entry.icursor(tk.END)

    def calculate_sibling_total():
        global siblings, sibling_mode

        if not sibling_mode:
            # normal single student total
            return sum(price for _, price in purpose_items)

        total = 0
        for s in siblings:
            for _, price in s["items"]:
                total += price
        return total

    # --- SAVE DATA ---
    def save_data():

        global purpose_items, siblings, sibling_mode, name_entry, class_entry, paid_entry, purpose_var

        referral_text = referral_entry.get().strip()

        # 🔐 Validate referral teachers
        ok, invalid = validate_referral_teachers(referral_text)
        if not ok:
            messagebox.showerror(
                "Invalid Referral ❌",
                "These teachers do not exist in Teacher Master:\n\n" +
                "\n".join(invalid) +
                "\n\nPlease correct spelling or add them first."
            )
            return

        # 1. Get basic info
        name = name_entry.get().strip()
        s_class = entry_class_box.get().strip()

        # Validation
        if not siblings and (not name or not s_class):
            messagebox.showerror("Error", "Please enter Student Name and Class")
            return

        # 2. Prepare list of all students to save
        all_to_save = []

        # Add previously added siblings
        for s in siblings:
            all_to_save.append(s)

        # Add current student (if has items)
        if name and purpose_items:
            all_to_save.append({
                'name': name,
                'class': s_class,
                'items': list(purpose_items),
                'referral': referral_entry.get().strip() or None
            })

        # 🔐 SIBLING ADMISSION SAFETY
        if referral_text:
            if not all_students_have_admission(all_to_save):
                messagebox.showerror(
                    "Invalid Referral ❌",
                    "Referral can only be applied when ALL siblings have Admission.\n\n"
                    "One or more students are missing Admission."
                )
                return

        if not all_to_save:
            messagebox.showerror("Error", "No items added to save!")
            return

        # 3. Save to DB using WATERFALL logic
        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()

            # 🚫 Block ONLY true duplicate student (same name + class)
            cursor.execute("""
                SELECT COUNT(*) FROM (
                    SELECT LOWER(name) AS name, student_class
                    FROM students
                    GROUP BY LOWER(name), student_class
                )
                WHERE name = LOWER(?) AND student_class = ?
            """, (name_entry.get().strip(), entry_class_box.get().strip()))

            already_exists = cursor.fetchone()[0] > 0

            if already_exists:
                messagebox.showerror(
                    "Duplicate Student ❌",
                    f"Student '{name_entry.get().strip()}' already exists "
                    f"in Class '{entry_class_box.get().strip()}'.\n\n"
                    "Same name is allowed in different classes."
                )
                return
            
            # -------- FAMILY ID LOGIC (FIXED) ----------

            global current_family_id

            if sibling_mode:
                if not current_family_id:
                    messagebox.showerror(
                        "Sibling Error",
                        "Please add at least one sibling before saving.\n\n"
                        "Use the Add Sibling button."
                    )
                    conn.close()
                    return
                family_id = current_family_id
            else:
                family_id = str(uuid.uuid4())[:8]

            # --- PAYMENT VALIDATION ---
            paid_text = paid_entry.get().strip()
            payment_mode = payment_mode_box.get().strip()

            if paid_text == "" or payment_mode == "":
                messagebox.showerror("Error", "Please enter Paid Amount and select Payment Mode")
                return

            try:
                remaining_paid = float(paid_text)
                original_paid = remaining_paid   # keep original payment
            except ValueError:
                messagebox.showerror("Error", "Invalid Paid Amount")
                return
            
            # Referral Value (NEW)
            ref_value = referral_entry.get().strip()
            if ref_value == "":
                ref_value = None
       
            # We store the initial paid value for the final audit/receipt log
            total_paid_initial = remaining_paid
            receipt_batch_id = datetime.now().strftime("%Y%m%d%H%M%S")
            current_batch_id = str(uuid.uuid4())[:8]

            for i, student in enumerate(all_to_save):

                # Build merged purpose text FIRST
                # Check if the user used the 'Add Item' purpose list or just typed in the box
                p_text = ", ".join([f"{n} ({p})" for n, p in student['items']])
                purpose_lower = p_text.lower()

                # Detect if this is ONLY a balance payment
                is_balance_only = (
                    len(student['items']) == 1 and
                    "balance" in student['items'][0][0].lower()
                )

                # -------- STRICT CLASS PROTECTION ----------
                cursor.execute("""
                    SELECT COUNT(*)
                    FROM (
                        SELECT LOWER(name) AS name, student_class
                        FROM students
                        GROUP BY LOWER(name), student_class, family_id
                    )
                    WHERE name = LOWER(?)
                      AND student_class = ?
                """, (student['name'], student['class']))

                already_exists = cursor.fetchone()[0] > 0

                if already_exists and not is_balance_only:
                    messagebox.showerror(
                        "Duplicate Student ❌",
                        f"Student '{student['name']}' already exists in Class '{student['class']}'.\n\n"
                        "Same name students are allowed in other classes, but not duplicate in the same class."
                    )
                    conn.close()
                    return
                
                # Compute this student's total from items
                student_total = sum(p for _, p in student['items'])

                is_save_new = not selected_record_id.get()
                
                paid_amount = remaining_paid

                # -------- PREVIOUS BALANCE (FAMILY LEDGER) ----------
                cursor.execute("""
                    SELECT balance FROM students
                    WHERE family_id = ?
                    ORDER BY id DESC LIMIT 1
                """, (family_id,))
                row = cursor.fetchone()
                previous_balance = row[0] if row else 0

                # -------- LEDGER BALANCE (ALLOW NEGATIVE) ----------
                balance = previous_balance + student_total - paid_amount

                # consume payment ONCE (family-level)
                remaining_paid = 0

                student_referral = student.get("referral")

                cursor.execute("""
                    INSERT INTO students
                    (name, student_class, purpose, total, paid, payment_mode,
                     balance, date_added, family_id, referral, receipt_batch_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    student["name"], student["class"], p_text,
                    student_total, paid_amount, payment_mode,
                    balance, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    family_id, student_referral, current_batch_id
                ))
                student_id = cursor.lastrowid

                # 1️⃣ check admission
                is_admission = any(
                    "admission" in str(item[0]).lower()
                    for item in student.get("items", [])
                )

                # ---------- FAMILY REFERRAL CHECK (VERY IMPORTANT) ----------
                cursor.execute("""
                    SELECT COUNT(*)
                    FROM teacher_referral r
                    JOIN students s ON r.student_id = s.id
                    WHERE s.family_id = ?
                    AND s.id != ?
                """, (family_id, student_id))

                family_has_referral = cursor.fetchone()[0] > 0

                # ✅ NEW — allow referral for every admitted student
                if student_referral and is_admission:
                    save_referrals(cursor, student_id, student_referral)

                cursor.execute("""
                INSERT INTO activity_log (timestamp, action_type, details)
                VALUES (?, ?, ?)
                """,
                (
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "INSERT",
                    f"INSERTED -> Name:{student['name']} | Class:{student['class']} | "
                    f"Purpose:{p_text} | Paid:{paid_amount} | Balance:{balance} | "
                    f"Family:{family_id}"
                ))

            conn.commit()
            conn.close()

            messagebox.showinfo("Success", f"Saved {len(all_to_save)} student(s) successfully!")
            referral_entry.delete(0, tk.END)
            referral_entry.config(state="disabled", bg="#f0f0f0")
            reset_ui()

            selected_record_id.set("")

            current_family_id = None
            siblings.clear()

        except Exception as e:
            messagebox.showerror("Database Error", f"Critical Error: {e}")

    def set_referral_amount(student_id, total_amount):
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()

        c.execute("""
        SELECT COUNT(*) FROM teacher_referral
        WHERE student_id=? AND status='PENDING'
        """, (student_id,))

        count = c.fetchone()[0]

        if count == 0:
            conn.close()
            return

        split = total_amount / count

        c.execute("""
        UPDATE teacher_referral
        SET share_amount = ?
        WHERE student_id = ?
        AND status = 'PENDING'
        AND (share_amount IS NULL OR share_amount = 0)
        """, (split, student_id))

        conn.commit()
        conn.close()

    # ---------- AUDIT LOG (COLOUR + BOLD STAFF) ----------
    # ---------- AUDIT LOG (COLOUR + BOLD STAFF) ----------
    def view_audit_trail():
        # --- Only Admin Allowed ---
        if user_role != "ADMIN":
            messagebox.showerror("Denied", "Only Admins can view audit logs.")
            return

        audit_win = tk.Toplevel(root)
        audit_win.title("System Audit Trail")
        audit_win.geometry("1000x600")

        audit_win.grid_rowconfigure(1, weight=1)
        audit_win.grid_columnconfigure(0, weight=1)

        search_var = tk.StringVar()
        search_frame = tk.Frame(audit_win)
        search_frame.pack(fill="x", padx=10, pady=10)

        tk.Label(search_frame, text="🔍 Search Logs:", font=("Arial", 10, "bold")).pack(side="left")
        tk.Entry(search_frame, textvariable=search_var, width=40).pack(side="left", padx=10)


        # --- Treeview and Scrollbar Container ---
        container = tk.Frame(audit_win)
        container.pack(fill="both", expand=True, padx=10, pady=5)

        cols = ("Time", "Action", "Details")
        audit_tree = ttk.Treeview(container, columns=cols, show="headings")

        # Create Scrollbars
        vsb = ttk.Scrollbar(container, orient="vertical", command=audit_tree.yview)
        hsb = ttk.Scrollbar(audit_win, orient="horizontal", command=audit_tree.xview) # Pack to window bottom

        audit_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        # Layout using Grid to make scrollbars stick to edges
        audit_tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.pack(fill="x", side="bottom") # Horizontal bar at the very bottom

        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(0, weight=1)

        # --- Column Headers ---
        for c in cols:
            audit_tree.heading(c, text=c)

        audit_tree.column("Time", width=150, stretch=False)
        audit_tree.column("Action", width=200, stretch=False)
        # Increase width of Details and enable stretching
        audit_tree.column("Details", width=4000, stretch=True) 

        # --- Rest of your styling and refresh logic ---
        try:
            bold_font = font.nametofont("TkDefaultFont").copy()
        except:
            bold_font = font.Font(family="Arial", size=10)
        bold_font.configure(weight="bold")

        audit_tree.tag_configure("STAFF_BOLD", font=bold_font)
        audit_tree.tag_configure("INSERT", foreground="green")
        audit_tree.tag_configure("UPDATE", foreground="blue")
        audit_tree.tag_configure("DELETE", foreground="red")
        audit_tree.tag_configure("LOGIN", foreground="orange")
        audit_tree.tag_configure("RECEIPT", foreground="purple")
        audit_tree.tag_configure("SYSTEM_BACKUP", foreground="gray")

        def refresh(*args):
            audit_tree.delete(*audit_tree.get_children())
            query = search_var.get().lower()
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT timestamp, action_type, details 
                FROM activity_log
                WHERE details LIKE ? OR action_type LIKE ?
                ORDER BY log_id DESC
            """, (f"%{query}%", f"%{query}%"))
            rows = cursor.fetchall()
            conn.close()

            for r in rows:
                tags = [r[1]]
                if r[2] and "STAFF" in r[2].upper():
                    tags.append("STAFF_BOLD")
                audit_tree.insert("", tk.END, values=r, tags=tags)

        search_var.trace_add("write", refresh)
        refresh()

    def refresh_audit_list(*args):
            for item in audit_tree.get_children(): audit_tree.delete(item)

            query = search_var.get().lower()
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT timestamp, action_type, details 
                FROM activity_log 
                WHERE details LIKE ? OR action_type LIKE ?
                ORDER BY log_id DESC
            """, (f'%{query}%', f'%{query}%'))
            rows = cursor.fetchall()
            conn.close()

            for r in rows:
                tags = []
                if r[1] in ("INSERT","UPDATE","DELETE","RECEIPT","LOGIN","SYSTEM_BACKUP"):
                    tags.append(r[1])
                if "STAFF" in r[2].upper():
                    tags.append("STAFF_BOLD")

                audit_tree.insert("", tk.END, values=r, tags=tags)

                search_var.trace_add("write", refresh_audit_list)
                refresh_audit_list()


    def update_summary_bar(msg=None, color="#1F618D"):
        if not msg:
            # Hide summary bar
            try:
                summary_canvas.delete("all")
                summary_canvas.pack_forget()
            except:
                pass
            return
        
        summary_canvas.pack(side="bottom", fill="x", padx=20, pady=10)
        summary_canvas.delete("all")
        summary_canvas.update_idletasks()

        w = summary_canvas.winfo_width()
        h = summary_canvas.winfo_height()

        summary_canvas.create_rectangle(0, 0, w, h, fill=color, outline=color)

        summary_canvas.create_text(
            w//2, h//2,
            text=msg,
            fill="white",
            font=("Arial", 13, "bold")
        )

    def filter_by_month_year():
        m_idx = months.index(month_box.get()) + 1
        y_val = year_box.get()
        filter_str = f"{y_val}-{m_idx:02d}"

        # Clear table
        for item in tree.get_children():
            tree.delete(item)

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # 🔥 Latest first
        cursor.execute(
            "SELECT * FROM students "
            "WHERE date_added LIKE ? "
            "ORDER BY id DESC",
            (filter_str + '%',)
        )

        rows = cursor.fetchall()

        # ---------- LOAD MONTHLY EXPENSES ----------
        cursor.execute("""
            SELECT IFNULL(SUM(amount),0)
            FROM school_expenses
            WHERE strftime('%Y-%m', expense_date) = ?
        """, (filter_str,))
        monthly_expense = cursor.fetchone()[0]

        # ❌ No records
        if not rows:
            conn.close()
            messagebox.showinfo(
                "No Records",
                f"No transactions found for {month_box.get()} {y_val}."
            )

            update_summary_bar(
                f"📅 Monthly Report | {month_box.get()} {y_val} | No Transactions",
                "red"
            )

            add_audit("FILTER", f"Filtered by Month: {month_box.get()} {y_val} (No Records)")
            return

        # ✅ Total collected + transactions
        gross_collected = sum(row[5] for row in rows)   # what students paid
        total_p = gross_collected - monthly_expense    # after expenses

        if total_p < 0:
            total_p = 0

        transactions = len(rows)

        # Insert into table with proper column mapping
        for row in rows:
            values = (
                row[0],   # ID
                row[1],   # Name
                row[2],   # Class
                row[10],  # Family ID
                row[3],   # Purpose
                row[4],   # Total
                row[5],   # Paid
                row[9],   # Payment Mode
                row[6],   # Balance
                row[7],   # Date
            )

            tag = 'due' if row[6] > 0 else ''
            tree.insert("", tk.END, values=values, tags=(tag,))

        conn.close()

        # ✅ Beautiful summary bar
        summary = (
            f"📅 Monthly Report | {month_box.get()} {y_val} | "
            f"Collected: Rs. {gross_collected} | "
            f"Expenses: Rs. {monthly_expense} | "
            f"Net: Rs. {total_p} | "
            f"Transactions: {transactions}"
        )

        update_summary_bar(summary, "#1F618D")
        add_audit("FILTER", f"Filtered by Month: {month_box.get()} {y_val}")

    def filter_by_date():
        d_str = cal.get_date().strftime("%Y-%m-%d")

        # Clear table
        for item in tree.get_children():
            tree.delete(item)

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # 🔥 Order latest first
        cursor.execute(
            "SELECT * FROM students "
            "WHERE date_added LIKE ? "
            "ORDER BY id DESC",
            (d_str + '%',)
        )

        rows = cursor.fetchall()

        # ---------- LOAD DAILY EXPENSES ----------
        cursor.execute("""
            SELECT IFNULL(SUM(amount),0)
            FROM school_expenses
            WHERE expense_date = ?
        """, (d_str,))
        daily_expense = cursor.fetchone()[0]

        # ❌ No records found
        if not rows:
            conn.close()
            messagebox.showinfo("No Records",
                            f"No records found for {d_str}.")
            update_summary_bar(
                f"📅 Daily Report | Date: {d_str} | No Transactions",
                "red"
            )
            add_audit("FILTER", f"Filtered by Date: {d_str} (No Records)")
            return

        # ✅ Total collected & transaction count
        gross_collected = sum(row[5] for row in rows)
        total_p = gross_collected - daily_expense

        if total_p < 0:
            total_p = 0

        transactions = len(rows)

        # Insert rows into tree properly mapped
        for row in rows:
            values = (
                row[0],   # ID
                row[1],   # Name
                row[2],   # Class
                row[10],  # Family ID
                row[3],   # Purpose
                row[4],   # Total
                row[5],   # Paid
                row[9],   # Payment Mode
                row[6],   # Balance
                row[7],   # Date
            )

            tag = 'due' if row[6] > 0 else ''
            tree.insert("", tk.END, values=values, tags=(tag,))

        conn.close()

        # ✅ Beautiful summary bar
        summary = (
            f"📅 Daily Report | Date: {d_str} | "
            f"Collected: Rs. {gross_collected} | "
            f"Expenses: Rs. {daily_expense} | "
            f"Net: Rs. {total_p} | "
            f"Transactions: {transactions}"
        )

        update_summary_bar(summary, "#D35400")
        add_audit("FILTER", f"Filtered by Date: {d_str}")

    def get_history():
        name = search_name_entry.get().strip()
        s_class = search_class_box.get()

        # ---- Validation ----
        if name and (not s_class or s_class == "All Classes"):
            messagebox.showwarning("Class Required",
                               "Please select the student's class to search.")
            return

        for item in tree.get_children():
            tree.delete(item)

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        if s_class == "All Classes":
            cursor.execute(
                "SELECT * FROM students WHERE name LIKE ? COLLATE NOCASE "
                "ORDER BY id DESC",
                (f"%{name}%",)
            )
        else:
            cursor.execute(
                "SELECT * FROM students WHERE name LIKE ? COLLATE NOCASE "
                "AND student_class = ? "
                "ORDER BY id DESC",
                (f"%{name}%", s_class)
            )

        rows = cursor.fetchall()

        if not rows:
            messagebox.showwarning("Not Found", "No record found for this student.")
            conn.close()
            return

    # =============================
    #  LOAD TABLE
    # =============================
        for row in rows:
            values = (
                row[0],   # ID
                row[1],   # Name
                row[2],   # Class
                row[10],  # Family ID
                row[3],   # Purpose
                row[4],   # Total
                row[5],   # Paid
                row[9],   # Payment Mode
                row[6],   # Balance
                row[7],   # Date
            )

            tag = 'due' if row[6] > 0 else ''
            tree.insert('', tk.END, values=values, tags=(tag,))

    # =============================
    #  SUMMARY BAR VALUES
    # =============================
        student_name = rows[0][1]     # Name
        # Latest transaction for this student
        cursor = sqlite3.connect(DB_NAME).cursor()
        cursor.execute("""
            SELECT balance
            FROM students
            WHERE LOWER(name)=LOWER(?) AND student_class=?
            ORDER BY id DESC
            LIMIT 1
        """, (student_name, s_class))

        last_balance = cursor.fetchone()[0]

        conn.close()

        summary_text = (
            f"🔍 Search Results | "
            f"Student: {student_name} | "
            f"Class: {s_class} | "
            f"Last Balance: Rs. {last_balance}"
        )

        text_color = "red" if last_balance > 0 else "darkgreen"
        update_summary_bar(summary_text, text_color)

    def show_defaulters():
        for item in tree.get_children():
            tree.delete(item)
    
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
    
        # NEW LOGIC: We find the LATEST balance for each unique student
        # This ensures that if Muskan had a balance in row 1 but cleared it in row 10,
        # row 1 will no longer show up here.
        query = """
        SELECT id, name, student_class, family_id, purpose, total, paid, payment_mode, balance, date_added
        FROM students s1
        WHERE id = (
            SELECT MAX(id) 
            FROM students s2 
            WHERE s2.name = s1.name AND s2.student_class = s1.student_class
        )
        AND balance > 0
        ORDER BY balance DESC
        """
    
        cursor.execute(query)
        rows = cursor.fetchall()
    
        for row in rows:
            tree.insert("", tk.END, values=row, tags=('due',))
    
        conn.close()
    
        total_due = sum(row[8] for row in rows)
        messagebox.showinfo("Defaulter List", f"Found {len(rows)} students with active pending fees.\nTotal: ₹{total_due:,.2f}")

    def update_summary_for_defaulters(rows):
        total_due = sum(row[6] for row in rows) # Assuming balance is at index 6
        # You can update your info_canvas or a label here
        messagebox.showinfo("Defaulter Summary", f"Found {len(rows)} students with pending fees.\nTotal Outstanding: ₹{total_due:,.2f}")

    def fill_balance_if_needed(event):
        global purpose_items

        if purpose_entry.get() != "Balance":
            return

        name = name_entry.get().strip()
        student_class = entry_class_box.get().strip()

        if not name or not student_class:
            messagebox.showwarning("Missing Data", "Select student name and class first.")
            return

        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()

            # Step 1 → Get family_id of this student
            cursor.execute("""
                SELECT family_id
                FROM students
                WHERE LOWER(TRIM(name)) = LOWER(TRIM(?))
                  AND LOWER(TRIM(student_class)) = LOWER(TRIM(?))
                ORDER BY id DESC
                LIMIT 1
            """, (name, student_class))

            row = cursor.fetchone()

            if not row or not row[0]:
                conn.close()
                messagebox.showwarning("Not Found", "No family record found.")
                return None

            family_id = row[0]

            # Step 2 → Get LAST ledger balance of this family
            cursor.execute("""
                SELECT balance
                FROM students
                WHERE family_id = ?
                ORDER BY id DESC
                LIMIT 1
            """, (family_id,))

            row = cursor.fetchone()
            conn.close()

            balance = float(row[0]) if row else 0

            if balance <= 0:
                messagebox.showinfo("No Balance", "This family has no pending balance.")
                return None

            return balance

        except Exception as e:
            messagebox.showerror("Error", str(e))
            return None

    def generate_family_pdf():
        name = search_name_entry.get().strip()

        if not name:
            messagebox.showwarning("PDF Error", "Enter a student name to fetch family.")
            return

        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()

            # Get family id of selected child
            cursor.execute(
                "SELECT family_id FROM students WHERE name = ? COLLATE NOCASE LIMIT 1",
                (name,)
            )
            data = cursor.fetchone()

            if not data:
                messagebox.showerror("Error", f"No record found for '{name}'.")
                conn.close()
                return

            family_id = data[0]

            # Get all siblings
            cursor.execute("""
                SELECT LOWER(name) 
                FROM students
                WHERE family_id = ?
                GROUP BY LOWER(name)
                ORDER BY LOWER(name)
            """, (family_id,))
            siblings = [s[0] for s in cursor.fetchall()]

            if not siblings:
                siblings = [name]

            filename = f"Family_Report_{family_id}.pdf"
            c = canvas.Canvas(filename, pagesize=letter)

            # Header
            c.setFont("Helvetica-Bold", 18)
            c.drawString(180, 760, "FAMILY FEE REPORT")

            c.setFont("Helvetica", 12)
            c.drawString(50, 735, f"Family ID : {family_id}")
            c.drawString(50, 720, f"Students  : {', '.join(siblings)}")
            c.line(40, 705, 570, 705)

            y = 680
            family_total = 0
            family_paid = 0
            family_due = 0

            # Loop each student
            for child in siblings:
                cursor.execute("""
                    SELECT date_added, purpose, total, paid, balance, payment_mode
                    FROM students
                    WHERE name = ? COLLATE NOCASE
                    ORDER BY id DESC
                """, (child,))

                rows = cursor.fetchall()
                if not rows:
                    continue

                c.setFont("Helvetica-Bold", 14)
                c.drawString(50, y, f"Student: {child}")
                y -= 5
                c.line(40, y, 570, y)
                y -= 20
                c.setFont("Helvetica", 12)

                for row in rows:
                    date, purpose, total, paid, balance, mode = row

                    text = (
                        f"📅 {date}\n"
                        f"Purpose       : {purpose}\n"
                        f"Total Amount  : Rs {total}\n"
                        f"Paid Amount   : Rs {paid}\n"
                        f"Balance       : Rs {balance}\n"
                        f"Payment Mode  : {mode}"
                    )

                    for line in text.split("\n"):
                        c.drawString(50, y, line)
                        y -= 18

                    y -= 10
                    c.line(40, y, 570, y)
                    y -= 25

                    if y < 120:
                        c.showPage()
                        c.setFont("Helvetica", 12)
                        y = 760

                y -= 15

            # ===============================
            # FINAL FAMILY SUMMARY CALCULATION
            # ===============================
            cursor.execute("""
                SELECT purpose, total, paid 
                FROM students
                WHERE family_id=?
            """, (family_id,))

            rows = cursor.fetchall()

            family_total = 0
            family_paid = 0

            import re

            for purpose, total, paid in rows:
                total = float(total or 0)
                paid = float(paid or 0)
                family_paid += paid

                balance_amt = 0

                if purpose:
                    m = re.findall(r"(?i)balance[^0-9]*([\d\.]+)", purpose)
                    if m:
                        balance_amt = sum(float(x) for x in m)

                adjusted = total - balance_amt
                if adjusted < 0:
                    adjusted = 0

                family_total += adjusted

            family_due = max(family_total - family_paid, 0)

            # -------- FAMILY SUMMARY PAGE --------
            if y < 160:
                c.showPage()
                y = 760

            c.setFont("Helvetica-Bold", 14)
            c.drawString(50, y, "FAMILY SUMMARY")
            y -= 10
            c.line(40, y, 570, y)
            y -= 25
            c.setFont("Helvetica", 12)

            c.drawString(50, y, f"Total Fee (All Children): Rs {family_total}")
            y -= 20
            c.drawString(50, y, f"Total Paid: Rs {family_paid}")
            y -= 20
            c.drawString(50, y, f"Total Pending: Rs {family_due}")

            c.save()
            conn.close()

            add_audit("PDF EXPORT", f"{user_role} generated FAMILY REPORT for Family: {family_id}")
            messagebox.showinfo("Success", f"Family PDF saved as {filename}")

        except Exception as e:
            messagebox.showerror("PDF Error", str(e))

    def delete_record():
        if not selected_record_id.get(): 
            messagebox.showwarning("Selection Required", "Select a record to delete.")
            return

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM students WHERE id = ?", (selected_record_id.get(),))
            record = cursor.fetchone()

            if not record:
                return

            student_id = record[0]

            # -------- CHECK PAID REFERRALS FIRST --------
            cursor.execute("""
                SELECT COUNT(*)
                FROM teacher_referral
                WHERE student_id=? AND status='PAID'
            """, (student_id,))
            already_paid = cursor.fetchone()[0]

            if already_paid > 0:
                if not messagebox.askyesno(
                    "Warning",
                    "This student generated referral money which is already paid.\n"
                    "Deleting will deduct teacher salary in future months.\n\nContinue?"
                ):
                    conn.close()
                    return

            # -------- CONFIRM DELETE --------
            if not messagebox.askyesno("Confirm", f"Delete record for {record[1]}?"):
                conn.close()
                return

            audit_text = (
                f"DELETE -> ID:{record[0]} | Name:{record[1]} | Class:{record[2]} | "
                f"Purpose:{record[3]} | Total:{record[4]} | Paid:{record[5]} | "
                f"Balance:{record[6]} | Date:{record[7]} | Receipt:{record[8]} | Mode:{record[9]}"
            )

            # -------- TRANSACTION START --------

            # 1️⃣ Remove unpaid referrals
            cursor.execute("""
                DELETE FROM teacher_referral
                WHERE student_id=? AND status='PENDING'
            """, (student_id,))

            # 2️⃣ Mark already-paid referrals for recovery
            cursor.execute("""
                UPDATE teacher_referral
                SET status='RECOVER_PENDING',
                    paid_month=NULL,
                    recovery_reason='Student deleted / admission cancelled',
                    recovery_applied=0,
                    recovery_salary_id=NULL
                WHERE student_id=? AND status='PAID'
            """, (student_id,))

            # 3️⃣ Delete student
            cursor.execute("DELETE FROM students WHERE id=?", (student_id,))

            conn.commit()

            add_audit("DELETE", f"{user_role} {audit_text}")
            reset_ui()
            refresh_table()

        except Exception as e:
            conn.rollback()
            messagebox.showerror("Error", f"Failed to delete record:\n{e}")

        finally:
            conn.close()

    def update_record():

        if not purpose_items:
            messagebox.showerror(
                "Update Error",
                "Select a purpose (Balance, Monthly Fee, Books, etc) before clicking Update."
            )
            return

        if not selected_record_id.get():
            messagebox.showwarning("Selection Required", "Please select a student first.")
            return

        try:
            name = name_entry.get().strip()
            s_class = entry_class_box.get().strip()

            batch_id = datetime.now().strftime("%Y%m%d%H%M%S")

            # 🔥 Build purpose from ledger items
            purpose = ", ".join([f"{n}({a})" for n,a in purpose_items])

            # 🔥 Transaction total = sum of items (NOT family total)
            total = sum(a for _,a in purpose_items)

            paid = float(paid_entry.get() or 0)

            payment_mode = payment_mode_box.get()

            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()

            # --- NEW STEP 1️⃣: SEARCH BY FAMILY ID FOR CONSISTENCY ---
            selected_id = selected_record_id.get()
            
            cursor.execute("""
                SELECT s1.balance, s1.family_id 
                FROM students s1 
                WHERE s1.family_id = (SELECT family_id FROM students WHERE id = ?)
                ORDER BY s1.id DESC LIMIT 1
            """, (selected_id,))

            row = cursor.fetchone()
            if not row:
                messagebox.showerror("Error", "Student not found.")
                conn.close()
                return

            prev_balance, family_id = row

            # 2️⃣ Calculate new running balance
            purpose_lower = purpose.lower()

            # 2️⃣ Calculate new running balance (LEDGER CORRECT)
            if "balance" in purpose_lower and "," in purpose_lower:
                # Balance + new items (e.g. Uniform + Balance)
                fee_part = total - prev_balance
                new_balance = prev_balance + fee_part - paid

            elif "balance" in purpose_lower:
                # Only balance payment
                new_balance = prev_balance - paid

            else:
                # Normal new fee
                new_balance = prev_balance + total - paid

            # 3️⃣ Insert NEW ledger row (do NOT update old one)
            cursor.execute("""
                INSERT INTO students
                (name, student_class, family_id, purpose, total, paid, balance, payment_mode, date_added, receipt_batch_id)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                name,
                s_class,
                family_id,
                purpose,
                total,
                paid,
                new_balance,
                payment_mode,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                batch_id
            ))

            conn.commit()
            conn.close()

            add_audit("LEDGER ADD",
                      f"{user_role} {name}-{s_class} | {purpose} | Total:{total} Paid:{paid} Balance:{new_balance}")

            messagebox.showinfo("Saved", "New transaction added.")
            reset_ui()

            selected_record_id.set("")

        except ValueError:
            messagebox.showerror("Error", "Check numeric inputs")

    def open_new_admission_list():
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()

        c.execute("""
            SELECT name, student_class, referral, date_added, family_id, total, paid, balance
            FROM students
            WHERE LOWER(purpose) LIKE '%admission%'
            ORDER BY date_added DESC
        """)
        rows = c.fetchall()
        conn.close()

        # SAFE TOPLEVEL
        win = tk.Toplevel()
        win.title("New Admissions List")
        win.geometry("1000x520")

        # ================= SEARCH BAR =================
        search_frame = tk.Frame(win)
        search_frame.pack(fill="x", padx=10, pady=5)

        tk.Label(search_frame, text="Search: ", font=("Arial", 10, "bold")).pack(side="left")

        search_var = tk.StringVar()

        search_entry = tk.Entry(search_frame, textvariable=search_var, width=40)
        search_entry.pack(side="left", padx=5)

        # ================= TABLE =================
        cols = ("S.No","Name","Class","Referral","Date","FamilyID")
        tree = ttk.Treeview(win, columns=cols, show="headings", height=18)

        for c in cols:
            tree.heading(c, text=c)

        tree.column("S.No", width=60, anchor="center")
        tree.column("Name", width=150, anchor="center")
        tree.column("Class", width=80, anchor="center")
        tree.column("Referral", width=150)
        tree.column("Date", width=140)
        tree.column("FamilyID", width=120)

        tree.pack(fill="both", expand=True, padx=10, pady=5)

        # ---------- Insert Data ----------
        def load_table(data):
            tree.delete(*tree.get_children())
            serial = 1
            for r in data:
                tree.insert("", tk.END, values=(serial, *r))
                serial += 1

        load_table(rows)

        # ---------- SEARCH FUNCTION ----------
        def search_table(*args):
            text = search_var.get().lower()
            filtered = []
            for r in rows:
                joined = " ".join([str(x).lower() for x in r])
                if text in joined:
                    filtered.append(r)

            load_table(filtered)

        # PYTHON 3.11+ SUPPORT
        try:
            search_var.trace_add("write", search_table)
        except:
            search_var.trace("w", search_table)

    def reset_ui():
        global purpose_items, siblings, sibling_mode, total_entry, sibling_status, status_label, search_name_entry, search_class_box, info_canvas, summary_canvas


        siblings = []
        sibling_mode = False
        sibling_btn.config(text="Enable Sibling Mode")
        name_entry.config(bg="white")
        # 1. Reset logic variables
        purpose_items = []

        # 2. Clear Name and Paid Entry fields
        name_entry.delete(0, tk.END)
        paid_entry.delete(0, tk.END)

        # --- FIX: Force Total Entry to clear ---
        total_entry.config(state='normal') # Temporarily unlock
        total_entry.delete(0, tk.END)
        total_entry.insert(0, "0.00")
        # total_entry.config(state='readonly') # Lock it back if you use readonly mode
    
        # 3. FIX: Reset Name Field Background Color
        name_entry.config(bg="white") 

        # 4. FIX: Clear and Reset Total Field
        total_entry.delete(0, tk.END)
        total_entry.insert(0, "") 

        # 5. Clear Purpose Preview Label
        purpose_var.set("") 

        # 6. Reset Dropdowns (Class and Purpose Selection)
        try:
            entry_class_box.set("") 
            purpose_entry.set("")
        except:
            # If they are standard Entries instead of Comboboxes
            entry_class_box.delete(0, tk.END)
            purpose_entry.delete(0, tk.END)

        # 7. Reset Payment Mode to Default
        payment_mode_box.set("")

        # 8. Reset Sibling Mode Button Text
        try:
            sibling_btn.config(text="Enable Sibling Mode")
        except:
            pass

        # 9. Update Sibling Status Label (Resets count to 0 and color to black)
        update_sibling_status()
    
        # 10. Focus back on name entry for next transaction
        name_entry.focus()

        try:
            search_name_entry.delete(0, tk.END)
            search_class_box.set("")    # THIS resets combobox properly
        except:
            pass

        refresh_table()

        summary_canvas.delete("all")

        info_canvas.delete("all")

        referral_entry.delete(0, tk.END)
        referral_entry.config(state="disabled")

        purpose_items.clear()
        purpose_display.config(text="")

    def refresh_table():
        for item in tree.get_children():
            tree.delete(item)

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM students ORDER BY id DESC")
        for row in cursor.fetchall():

            values = (
                row[0],   # ID
                row[1],   # Name
                row[2],   # Class
                row[10],   # Family ID
                row[3],   # Purpose
                row[4],   # Total
                row[5],   # Paid
                row[9],   # PAYMENT MODE  ✅  (correct index)
                row[6],   # Balance
                row[7],   # Date
            )

            tag = "due" if row[6] > 0 else ""
            tree.insert("", tk.END, values=values, tags=(tag,))

        conn.close()

    def db_student_has_admission(student_id):
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("""
            SELECT COUNT(*)
            FROM students
            WHERE id=? AND LOWER(purpose) LIKE '%admission%'
        """, (student_id,))
        result = c.fetchone()[0] > 0
        conn.close()
        return result

    def on_click(event):
        global sibling_mode, siblings, purpose_items

        # ---- RESET SIBLING MODE ----
        sibling_mode = False
        siblings = []

        try:
            sibling_status.set("Sibling Mode: 0 Students")
        except:
            pass

        item = tree.selection()
        if not item:
            return

        v = tree.item(item)["values"]
        selected_record_id.set(v[0])

        # 🔥 Reset update-purpose engine
        purpose_var.set("")   # clears preview label

        # 🔒 Lock referral based on DB admission
        if db_student_has_admission(v[0]):
            referral_entry.config(state="disabled")
            referral_entry.delete(0, tk.END)
        else:
            referral_entry.config(state="normal")

        pass

        student_name = v[1]
        student_class = v[2]
        family = v[3]

        # -----------------------------------
        #  FILL ONLY STUDENT IDENTITY (Ledger Mode)
        # -----------------------------------
        name_entry.delete(0, tk.END)
        name_entry.insert(0, student_name)

        entry_class_box.set(student_class)

        # 🔥 Ledger mode: never load old transaction into entry fields
        purpose_var.set("")
        purpose_entry.delete(0, tk.END)

        # ---- SHOW FAMILY LEDGER DUE IN TOTAL BOX ----
        if family and family != "None":
            try:
                conn = sqlite3.connect(DB_NAME)
                c = conn.cursor()

                c.execute("""
                    SELECT balance
                    FROM students
                    WHERE family_id = ?
                    ORDER BY id DESC
                    LIMIT 1
                """, (family,))

                row = c.fetchone()
                conn.close()

                fam_due = float(row[0] or 0) if row else 0

                total_entry.delete(0, tk.END)
                total_entry.insert(0, f"{fam_due:.2f}")

            except:
                total_entry.delete(0, tk.END)
                total_entry.insert(0, "0")

        paid_entry.delete(0, tk.END)

        payment_mode_box.set("")

        # -----------------------------------
        # HIGHLIGHT FAMILY MEMBERS
        # -----------------------------------
        for i in tree.get_children():
            tree.item(i, tags=())

        if family and family != "None":
            for i in tree.get_children():
                row = tree.item(i)["values"]
                if row[3] == family:
                    tree.item(i, tags=("family",))

        # -----------------------------------
        # FAMILY SUMMARY (FINAL CORRECT LOGIC)
        # -----------------------------------
        # -----------------------------------
        # FAMILY SUMMARY (LEDGER MODE)
        # -----------------------------------
        try:
            if family and family != "None":
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                # Add 'name' to the start of the SELECT
                cursor.execute("""
                    SELECT name, purpose, total, paid, balance
                    FROM students
                    WHERE family_id = ?
                    ORDER BY id
                """, (family,))
                rows = cursor.fetchall()

                unique_names = set()

                # Wallet
                cursor.execute("""
                    SELECT credit_wallet
                    FROM family_accounts
                    WHERE family_id = ?
                """, (family,))
                wallet_row = cursor.fetchone()

                conn.close()
                
                import re

                fam_total = 0
                fam_paid = 0
                latest_balance = 0

                for name, purpose, t, p, b in rows:
                    unique_names.add(name)

                    total   = float(t or 0)
                    paid    = float(p or 0)
                    balance = float(b or 0)

                    latest_balance = balance

                    if "balance" in (purpose or "").lower():
                        # remove previous dues from this row
                        real_fee = total - prev_balance
                    else:
                        real_fee = total

                    fam_total += max(real_fee, 0)
                    fam_paid  += paid

                    prev_balance = balance

                fam_dues = max(latest_balance, 0)
                fam_advance = abs(min(latest_balance, 0))

                msg = (
                    f"👨‍👩‍👧 FAMILY: {family}  |  "
                    f"Members: {len(unique_names)}  |  "
                    f"Fees: {fam_total}  |  "
                    f"Paid: {fam_paid}  |  "
                    f"Dues: {fam_dues}  |  "
                    f"Advance Credit: {fam_advance}"
                )

                update_summary_bar(msg, "#0B5345")
                sibling_status.set(f"Sibling Group: {len(unique_names)} Student(s)")
            else:
                try:
                    summary_canvas.delete("all")
                    summary_canvas.pack_forget()
                except:
                    pass

                if not sibling_mode:
                    sibling_status.set("Sibling Mode: 0 Students")

        except Exception as e:
            print("Summary Error:", e)

    def toggle_sibling_mode():
        global sibling_mode, siblings, current_family_id

        sibling_mode = not sibling_mode

        if sibling_mode:
            siblings.clear()
            current_family_id = str(uuid.uuid4())[:8]   # 🔥 create family here

            messagebox.showinfo(
                "Sibling Billing",
                "Sibling Billing Mode ENABLED.\n\n"
                "Add each child using 'Add Sibling'.\n"
                "Then enter last child and press Save."
            )

            sibling_btn.config(text="Disable Sibling Mode")
            name_entry.config(bg="#e8f8ff")

        else:
            siblings.clear()
            current_family_id = None                   # 🔥 reset family
            sibling_mode = False

            messagebox.showinfo("Sibling Billing", "Sibling Billing Mode Disabled.")

            name_entry.config(bg="white")
            sibling_btn.config(text="Enable Sibling Mode")

    def update_sibling_status():
        global siblings, sibling_status, status_label # Add status_label to the globals
    
        count = len(siblings)
        sibling_status.set(f"Sibling Mode: {count} Students Added")
    
        # This is where the crash happened because 'status_label' wasn't global
        if count > 0:
            status_label.config(fg="green") 
        else:
            status_label.config(fg="black")

    def update_family_total():
        global siblings, purpose_items, total_entry, purpose_var

        if not sibling_mode:
            total_entry.config(state='normal')
            total_entry.delete(0, tk.END)
            purpose_var.set("")
            return
    
        grand_total = 0.0
        preview_lines = []

        # 1. Add up all siblings already in the queue
        for s in siblings:
            # Sum items for this specific sibling
            sib_total = sum(p for _, p in s['items'])
            grand_total += sib_total
        
            # Create a breakdown line: "Ali: Monthly Fee (1000), Admission (500)"
            item_str = ", ".join([f"{n}" for n, _ in s['items']])
            preview_lines.append(f"• {s['name']} ({s['class']}): {item_str} [Subtotal: {sib_total:.2f}]")

        # 2. Add current student on screen
        current_name = name_entry.get().strip()
        if current_name and purpose_items:
            current_total = sum(p for _, p in purpose_items)
            grand_total += current_total
        
            item_str = ", ".join([f"{n}" for n, _ in purpose_items])
            preview_lines.append(f"• {current_name} (Current): {item_str} [Subtotal: {current_total:.2f}]")

        # 3. Update the Total Entry Field
        total_entry.config(state='normal')
        total_entry.delete(0, tk.END)
        total_entry.insert(0, f"{grand_total:.2f}")
        # total_entry.config(state='readonly') # Optional: lock it back

        # 4. Update the Visual Breakdown Label
        if preview_lines:
            full_preview = "\n".join(preview_lines)
            purpose_var.set(full_preview)
        else:
            purpose_var.set("No items added yet.")

    # ================= UI =================
    top_frame = tk.LabelFrame(root, text="Reporting & Audit Filters", fg="purple", font=("Arial", 10, "bold"))
    top_frame.pack(pady=10, fill="x", padx=20)
    
    cal = DateEntry(top_frame, width=12, date_pattern='yyyy-mm-dd')
    cal.grid(row=0, column=0, padx=5, pady=10)
    tk.Button(top_frame, text="📅 Date Filter", command=filter_by_date, bg="#5D6D7E", fg="white").grid(row=0, column=1, padx=5)
    
    tk.Label(top_frame, text=" | Month:").grid(row=0, column=2)
    month_box = ttk.Combobox(top_frame, values=months, width=12, state="readonly")
    month_box.set(datetime.now().strftime("%B")); month_box.grid(row=0, column=3, padx=5)
    
    tk.Label(top_frame, text="Year:").grid(row=0, column=4)
    year_box = ttk.Combobox(top_frame, values=years, width=8, state="readonly")
    year_box.set(datetime.now().strftime("%Y")); year_box.grid(row=0, column=5, padx=5)
    
    tk.Button(top_frame, text="📊 Monthly Filter", command=filter_by_month_year, bg="#2E86C1", fg="white").grid(row=0, column=6, padx=5)
    
    audit_btn = tk.Button(top_frame, text="📜 Audit Logs",
                          command=view_audit_trail,
                          bg="purple", fg="white", width=12)
    audit_btn.grid(row=1, column=0, padx=10)

    if user_role == "ADMIN":
        tk.Button(
            top_frame,
            text="👨‍🏫 Teacher Salary",
            command=open_salary_module,
            bg="#1ABC9C",
            fg="white",
            width=14
        ).grid(row=1, column=9, padx=5)

    # Inside main_app(user_role), in the top_frame section:
    dash_btn = tk.Button(
    top_frame,
    text="📈 Dashboard",
    command=show_financial_dashboard,
    bg="#8E44AD",
    fg="white",
    width=12
    )
    dash_btn.grid(row=1, column=1, padx=5)

    # ---- Disable for STAFF ----
    if user_role == "STAFF":
        dash_btn.config(state="disabled")

    # Inside main_app(user_role), in the top_frame section:
    tk.Button(top_frame, text="⚠️ Defaulters", 
              command=show_defaulters, 
              bg="#E67E22", fg="white", width=12).grid(row=1, column=2, padx=5)

    # --- MANAGE USERS BUTTON ---
    manage_btn = tk.Button(
        top_frame,
        text="👥 Manage Users",
        command=open_user_management,
        bg="#34495e",
        fg="white",
        width=12
    )
    manage_btn.grid(row=1, column=3, padx=5)

    tk.Button(
        top_frame,
        text="↩ Undo Promotion",
        bg="#c0392b",
        fg="white",
        font=("Arial", 9, "bold"),
        padx=6,
        pady=2,
        command=undo_last_promotion
    ).grid(row=0, column=11, padx=6)

    tk.Button(
        top_frame,
        text="🧾 School Expenses",
        bg="#ddd20d",
        fg="white",
        font=("Arial",9,"bold"),
        padx=6,
        pady=2,
        command=open_expense_manager
    ).grid(row=0, column=10, padx=6)

    tk.Button(
        top_frame,
        text="⬆ Promote All Students",
        bg="#488c49",
        fg="white",
        font=("Arial", 9, "bold"),
        padx=8,
        pady=2,
       command=promote_all_students
    ).grid(row=1, column=11, padx=6)

    # ---- Disable for STAFF ----
    if user_role == "STAFF":
        manage_btn.config(state="disabled", bg="gray")

    tk.Button(top_frame, text="📂 Report", command=generate_family_pdf,bg="green", fg="white", width=12).grid(row=1, column=4, padx=5)
    delete_btn = tk.Button(
    top_frame,
    text="🗑️ Delete",
    command=delete_record,
    bg="black",
    fg="white",
    width=10
    )
    delete_btn.grid(row=1, column=5, padx=5)
    if user_role == "STAFF":
        delete_btn.config(state="disabled", bg="gray")

    tk.Button(top_frame, text="🔄 Reset", command=reset_ui, bg="#7F8C8D", fg="white", width=10).grid(row=1, column=6)
    tk.Button(top_frame, text="🔓 Logout", command=logout, bg="#E74C3C", fg="white", font=("Arial", 9, "bold"), width=10).grid(row=1, column=10, padx=20)

    global search_name_entry, search_class_box

    search_frame = tk.LabelFrame(root, text="Quick Search", fg="orange", font=("Arial", 10, "bold"))
    search_frame.pack(pady=5, fill="x", padx=20)
    tk.Label(search_frame, text="Student Name:").grid(row=0, column=0, padx=5)
    search_name_entry = tk.Entry(search_frame, width=30); search_name_entry.grid(row=0, column=1)
    tk.Label(search_frame, text="Filter Class:").grid(row=0, column=2, padx=10)
    # Inside your search_frame section in main_app:
    tk.Button(search_frame, text="👨‍👩‍👧‍👦 Show Family", 
              command=filter_by_family, 
              bg="#16A085", fg="white", width=15).grid(row=0, column=5, padx=10)
    search_class_box = ttk.Combobox(search_frame, values=search_classes, width=15, state="readonly"); search_class_box.set(""); search_class_box.grid(row=0, column=3)
    tk.Button(search_frame, text="Find History", command=get_history, bg="orange", width=15).grid(row=0, column=4, padx=15, pady=5)

    entry_frame = tk.LabelFrame(root, text="Data Entry / Edit", font=("Arial", 10, "bold"))
    entry_frame.pack(pady=10, fill="x", padx=20)

    tk.Label(entry_frame, text="Name:").grid(row=0, column=0); 
    global name_entry
    name_entry = tk.Entry(entry_frame); 
    name_entry.grid(row=0, column=1)

    tk.Label(entry_frame, text="Class:").grid(row=0, column=2); 
    global entry_class_box
    entry_class_box = ttk.Combobox(entry_frame, values=classes, width=10); 
    entry_class_box.grid(row=0, column=3)

    tk.Label(entry_frame, text="Purpose:").grid(row=0, column=4)

    global purpose_var
    purpose_var = tk.StringVar()
    # This traces changes to Purpose and updates the Total field automatically
    purpose_var.trace_add("write", auto_calculate_total)
    
    global purpose_entry # Declared global BEFORE assignment
    
    item_list = ["Monthly Fee", "Admission", "Books", "Uniform", "Exam Fee","Balance", "Diary", "Result Card", "Other"]
    purpose_entry = ttk.Combobox(entry_frame, textvariable=purpose_var, values=item_list)
    purpose_entry.grid(row=0, column=5, padx=5)
    purpose_entry.bind("<<ComboboxSelected>>", fill_balance_if_needed, add="+")
    purpose_entry.bind("<<ComboboxSelected>>", handle_selection, add="+")
    purpose_entry.bind("<<ComboboxSelected>>", handle_referral_enable, add="+")

    tk.Label(entry_frame, text="Total:").grid(row=1, column=0); 
    global total_entry
    total_entry = tk.Entry(entry_frame) # Ensure it starts with 't' 
    total_entry.grid(row=1, column=1, pady=5)

    tk.Label(entry_frame, text="Paid:").grid(row=1, column=2); 
    global paid_entry
    paid_entry = tk.Entry(entry_frame); 
    paid_entry.grid(row=1, column=3)
    
    # ---------------- REFERRAL FIELD ----------------
    tk.Label(entry_frame, text="Referral:").grid(row=2, column=0, pady=5)

    global referral_entry
    referral_entry = tk.Entry(entry_frame, state="disabled")
    referral_entry.grid(row=2, column=1, pady=5)

    tk.Label(entry_frame, text="Payment Mode:").grid(row=1, column=4)
    global payment_mode_box
    payment_mode_box = ttk.Combobox(entry_frame, values=["Cash","UPI","Card","Cheque"], width=10, state="readonly")
    payment_mode_box.grid(row=1, column=5)
    payment_mode_box.set("")

    sibling_btn = tk.Button(
    entry_frame,
    text="Enable Sibling Mode",
    bg="brown", fg="white",
    command=toggle_sibling_mode
    )
    sibling_btn.grid(row=0, column=6, padx=10)

    add_sibling_btn = tk.Button(
    entry_frame,
    text="Add Sibling",
    bg="pink", fg="black",
    command=add_sibling
    )
    add_sibling_btn.grid(row=0, column=8, padx=10)
    global sibling_status, status_label

    sibling_status = tk.StringVar(value="Sibling Mode: 0 Students")
    status_label = tk.Label(entry_frame, textvariable=sibling_status, fg="black")
    status_label.grid(row=0, column=10)

    btn_new_adm = tk.Button(
    top_frame,
    text="New Admissions",
    command=open_new_admission_list,
    bg="#2E86C1",
    fg="white",
    width=14,
    font=("Arial", 10, "bold")
    )
    btn_new_adm.grid(row=1, column=7, padx=5)

    if user_role == "STAFF":
        btn_new_adm.config(state="disabled")

    tk.Button(entry_frame, text="Save New", command=save_data, bg="green", fg="white", width=12).grid(row=1, column=6, padx=5)
    tk.Button(entry_frame, text="Update", command=update_record, bg="blue", fg="white", width=12).grid(row=1, column=7)
    tk.Button(entry_frame, text="🖨️ Receipt", command=generate_thermal_receipt, bg="#D4AC0D", fg="black", font=("Arial", 9, "bold"), width=12).grid(row=1, column=8, padx=10)
    tk.Button(entry_frame,
          text="Remove Item",
          bg="orange",
          fg="white",
          width=12,
          command=remove_purpose_item).grid(row=1, column=9, padx=5)

    table_frame = tk.Frame(root)
    table_frame.pack(pady=10, fill="both", expand=True, padx=20)

    tree = ttk.Treeview(table_frame,
                    columns=("ID","Name","Class","Family ID","Purpose","Total","Paid","Payment","Balance","Date"),
                    show="headings",
                    height=18)

    tree.grid(row=0, column=0, sticky="nsew")

    for col in ("ID","Name","Class","Family ID","Purpose","Total","Paid","Payment","Balance","Date"):
        tree.heading(col, text=col)

        if col == "Purpose":
            tree.column("Purpose", width=900, anchor="w", stretch=True)
        elif col == "Family ID":
            tree.column("Family ID", width=140, anchor="center")
        else:
            tree.column(col, width=120, anchor="center")

    tree.tag_configure('due', foreground='red')
    tree.tag_configure('family', background='#E8F6F3')
    tree.bind("<<TreeviewSelect>>", on_click)

    hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=tree.xview)
    tree.configure(xscrollcommand=hsb.set)
    hsb.grid(row=1, column=0, columnspan=2, sticky="ew")

    table_frame.grid_columnconfigure(0, weight=1)
    table_frame.grid_rowconfigure(0, weight=1)

    global info_canvas
    global summary_canvas
    global purpose_display

    # --- ADD THIS HERE ---
    # This replaces the old Message widget to allow for a clean list-style preview
    purpose_display = tk.Label(
        root,
        text="",
        font=("Arial", 10, "bold"),
        fg="blue",
        justify="left",
        anchor="w",
        wraplength=1100
    )

    purpose_display.pack(pady=5, fill="x", padx=20)

    summary_canvas = tk.Canvas(root, height=50, bg="#ecf0f1",
                           highlightthickness=1, relief="ridge")
    summary_canvas.pack(side="bottom", fill="x", padx=20, pady=10)


    info_canvas = tk.Canvas(root, height=50, bg="#ecf0f1",
                        highlightthickness=1, relief="ridge")
    info_canvas.pack(side="bottom", fill="x", padx=20, pady=10)

    refresh_table()
    root.mainloop()

# ------------ LOGIN SCREEN ------------
import hashlib # Make sure this is at the very top of your file!

def show_login_screen():
    login_scr = tk.Tk()
    login_scr.title("School Management - Login")
    login_scr.geometry("300x250")

    tk.Label(login_scr,text="User Login",font=("Arial",12,"bold")).pack(pady=10)

    tk.Label(login_scr,text="Username:").pack()
    user_entry=tk.Entry(login_scr); user_entry.pack(pady=5)

    tk.Label(login_scr,text="Password:").pack()
    pw_entry=tk.Entry(login_scr,show="*"); pw_entry.pack(pady=5)

    def check_login():
        u = user_entry.get().strip()
        p = pw_entry.get()
    
        # 1. Convert the typed password into a SHA-256 hash
        input_hash = hashlib.sha256(p.encode()).hexdigest()
    
        try:
            # 2. Connect to database to verify user
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT role FROM users WHERE username=? AND password_hash=?",
                (u, input_hash)
            )
            user = cursor.fetchone()
            conn.close()

            if user:
                role = user[0]

                # 🔐 STORE LOGGED-IN USERNAME
                global logged_in_user
                logged_in_user = u

                add_audit("LOGIN", f"User '{u}' logged in successfully.")
                login_scr.destroy()
                main_app(role)
            else:
                messagebox.showerror("Login Failed", "Invalid username or password")

        except sqlite3.OperationalError:
            messagebox.showerror(
                "Database Error",
                "User table not found. Please restart the app to initialize the database."
            )

    tk.Button(login_scr, text="Login", command=check_login,
              bg="#2ecc71", fg="white", width=15).pack(pady=20)

    login_scr.mainloop()

try:
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("ALTER TABLE students ADD COLUMN referral TEXT")
    conn.commit()
    conn.close()
except sqlite3.OperationalError:
    # Column already exists
    pass

conn = sqlite3.connect(DB_NAME)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS family_accounts (
    family_id TEXT PRIMARY KEY,
    credit_wallet REAL DEFAULT 0
)
""")

conn.commit()
conn.close()

conn = sqlite3.connect(DB_NAME)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS teacher_referral (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER,
    teacher_id INTEGER,
    share_amount REAL DEFAULT 0,   -- will fill later
    status TEXT DEFAULT 'PENDING', -- PENDING / PAID
    paid_month TEXT,
    FOREIGN KEY(student_id) REFERENCES students(id),
    FOREIGN KEY(teacher_id) REFERENCES teachers(id)
)
""")

conn.commit()
conn.close()

conn = sqlite3.connect(DB_NAME)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS teacher_referral (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER,
    teacher_id INTEGER,
    share_amount REAL DEFAULT 0,
    status TEXT DEFAULT 'PENDING',  -- PENDING / PAID
    paid_month TEXT
)
""")

conn = sqlite3.connect(DB_NAME)
c = conn.cursor()

c.execute("PRAGMA table_info(teacher_referral)")
cols = [col[1] for col in c.fetchall()]

if "recovery_reason" not in cols:
    c.execute("ALTER TABLE teacher_referral ADD COLUMN recovery_reason TEXT")

conn.commit()
conn.close()

if __name__ == "__main__":
    init_db()
    ensure_batch_column()
    create_family_wallet_table()
    ensure_referral_column()
    safe_add_recovery_columns()
    add_referral_bonus_column()
    ensure_academic_year_lock()
    ensure_expense_table()
    ensure_promotion_history()
    fix_family_id_column()
    show_login_screen()
