🏫 School Fee & Ledger Manager v2.0.0

A secure, multi-user, desktop-based School Fee & Ledger Management System built using Python, Tkinter, and SQLite.
This version is a major upgrade over v1.0, transforming the application into a complete school accounting & ledger solution.

⭐ Key Highlights (v2.0 Upgrade)

🔐 Role-based authentication (Admin / Staff)

👨‍👩‍👧 Advanced family & sibling billing system

🧾 Single & family receipt generation

📊 Financial dashboard & expense tracking

👩‍🏫 Teacher, salary & referral management

🎓 Academic promotion system with history & undo

🔒 Encrypted automatic database backups

🕵️ Complete audit trail system

🎓 Student & Fee Management

Add, update & manage student fee records

Auto calculation of Total / Paid / Balance

Monthly & yearly filtering

Search & sort student data table

Zero-amount & balance-safe handling

👨‍👩‍👧 Family / Sibling Billing System (Enhanced)

Unique Family ID–based accounting

Accurate family-level balance carry-forward

Combined Family Total / Paid / Balance

Auto sibling detection & visual highlighting

Family-wise filtering & summary view

Shared family receipt support

support

🧾 Receipt Generation (Upgraded)

Single-student & family-wise receipts

Thermal & PDF receipt support

Auto receipt number generation

Dynamic receipt height (item-based)

Multiple payment modes

Organized receipt storage

Admin / Staff receipt audit tracking

📊 Financial Dashboard & Ledger

Monthly financial overview:

Expected Fees

Paid Amount

Pending Dues (family-aware)

Expenses

Net Collection

School expense management module

Accurate net profit calculation

👩‍🏫 Teacher, Salary & Referral Management

Teacher master records

Salary calculation & payment tracking

Referral & commission management

Safe referral split logic

Referral recovery from salaries

Complete referral & recovery history

🎓 Academic Promotion System

Class promotion with preview

Academic year locking (prevents duplicate promotions)

Promotion history tracking

Undo last promotion (Admin only)

🕵️ Audit Trail System (Expanded)

Logs every critical action:

Login / Logout

Insert / Update / Delete

Receipt printing

Expense operations

User management

Promotions & filters

✔ Color-coded display
✔ Admin-only access

🔐 Security & Data Safety

Role-based access control (Admin / Staff)

Secure password hashing

Encrypted automatic database backups

Safe schema migrations (no data loss)

Error-safe operations

🖥 Desktop Software

Converted to Windows EXE

Runs without Python installed

User-friendly interface

Optimized for school office usage

| Component         | Technology  |
| ----------------- | ----------- |
| GUI               | Tkinter     |
| Database          | SQLite      |
| Receipts          | ReportLab   |
| Backup Encryption | Fernet      |
| Packaging         | PyInstaller |
| Language          | Python      |
🔽 Download Executable

Download the latest version (v2.0.0) from GitHub Releases:
👉 https://github.com/Aditya240302/Student-Fee-Ledger-Manager/releases

👤 User Roles
👑 Admin

Full system control

View audit logs

Manage users

Manage expenses

Promote students

Undo promotions

👨‍💼 Staff

Limited access

Cannot access restricted sections

Cannot view audit logs

📝 Audit Logs Example

ADMIN PRINTED FAMILY RECEIPT | Family ID: FAM1021 | Students: 3 | Total: 12000 | Paid: 7000
STAFF INSERTED STUDENT RECORD | Name: Rahul Sharma | Class: 5
ADMIN FILTERED RECORDS | Month: January 2025

📦 Developer Installation (Optional)

If running via Python:

pip install tkcalendar
pip install reportlab
pip install pillow

Run:
python test.py

🏗 Build as EXE (Developer Only)

pyinstaller --noconsole --onefile test.py

👨‍💻 Developer

Aditya Jaiswal
Python | Tkinter | Database Applications

🚀 Version

Current Version: v2.0.0
Previous Version: v1.0
