🏫 School Fee & Ledger Manager

A powerful desktop-based School Fee Management System built using Python, Tkinter, and SQLite.
This application allows schools to manage student fees, payments, sibling billing, receipts, audit logs, and financial reports in an easy and efficient way.

⭐ Features
🎓 Student & Fee Management

Add, update and manage student fee records

Auto calculation of Total / Paid / Balance

Monthly & yearly filtering

Student data table with sorting and search

👨‍👩‍👧 Family / Sibling Billing System

Unique Family ID system

Waterfall fee distribution logic

Auto sibling detection & summary

Highlight siblings when selected

Combined Family Total / Paid / Balance

🧾 Receipt Generation

Thermal & PDF receipt support

Auto receipt number generation

Saves receipts safely in Receipts folder

Supports multiple payment modes

Admin/Staff receipt tracking

🕵️ Audit Trail System

Logs every important action:

Insert

Update

Delete

Login

Receipt Print

Filters

Color-coded activity display

Only Admin can view logs

🔍 Smart Filters & Reports

Filter by month & year

Search by name / class

Smart summary bar

Due-highlight system

💾 Secure Local Database

SQLite based storage

Backup support

Error-safe system

🖥 Desktop Software

Converted to Windows EXE application

Can run without Python

User-friendly interface

| Component | Technology  |
| --------- | ----------- |
| GUI       | Tkinter     |
| Database  | SQLite      |
| Receipts  | ReportLab   |
| Packaging | PyInstaller |
| Language  | Python      |

🔽 Download Executable

Download the latest build from Releases Section:
https://github.com/Aditya240302/Student-Fee-Ledger-Manager/releases/tag/v1.0

👤 User Roles

Admin

Full control

Can view audit logs

Can delete & update records

Staff

Limited access

Cannot access restricted sections

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
