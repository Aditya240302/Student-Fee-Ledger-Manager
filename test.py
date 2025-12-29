import re
import sys
import os
import uuid
import tkcalendar
import tkinter as tk
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
purpose_items = []
siblings = []
sibling_mode = False

# --- DATABASE SETUP ---
DB_NAME = 'school_data.db'
BACKUP_DIR = 'database_backups'

def init_db():
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
        
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

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
                       payment_mode TEXT)""")
    # ---- Add family_id column if not exists ----
    try:
        cursor.execute("ALTER TABLE students ADD COLUMN family_id TEXT")
    except:
        pass

    try: cursor.execute("ALTER TABLE students ADD COLUMN receipt_no TEXT")
    except: pass
    try: cursor.execute("ALTER TABLE students ADD COLUMN payment_mode TEXT")
    except: pass
    
    cursor.execute("""CREATE TABLE IF NOT EXISTS activity_log 
                      (log_id INTEGER PRIMARY KEY AUTOINCREMENT, 
                       action_type TEXT, 
                       details TEXT, 
                       timestamp TEXT)""")
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
        backup_filename = f"backup_{timestamp}_{user_role}.db"
        shutil.copy2(DB_NAME, os.path.join(BACKUP_DIR, backup_filename))
        add_audit("SYSTEM_BACKUP", f"Auto-backup created: {backup_filename}")
        return True
    except:
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
    global purpose_items
    purpose_items.clear()

    def add_sibling():
        global siblings, purpose_items, sibling_mode

        if not sibling_mode:
            messagebox.showwarning("Sibling Mode", "Enable Sibling Mode first")
            return
        # 1. Grab data from the main screen entries
        name = name_entry.get().strip()
        s_class = entry_class_box.get()

        if not name or not purpose_items:
            messagebox.showwarning("Logic Error", "Enter Name and add items first!")
            return

        # 2. Package the child data
        new_sibling = {
            "name": name,
            "class": s_class,
            "items": list(purpose_items) 
        }

        # 3. Save to list and clear current fields for next sibling
        siblings.append(new_sibling)
        purpose_items = []
        name_entry.delete(0, tk.END)
        purpose_var.set("")
        entry_class_box.set("") # Clears the class dropdown

        # 4. Update UI labels and totals
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


    def handle_selection(event):
        global purpose_items, siblings, sibling_mode
        selected_item = purpose_entry.get()

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

        c.execute("SELECT name, student_class, family_id FROM students WHERE id=?",
                  (selected_record_id.get(),))
        row = c.fetchone()

        if not row:
            conn.close()
            messagebox.showerror("Error", "Record not found!")
            return

        student_name, s_class, family_id = row

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
            ORDER BY id
        """, (family_id,))

        records = c.fetchall()

        if not records:
            conn.close()
            messagebox.showerror("Error", "No family records found!")
            return

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

        # ---- FAMILY TOTALS ----
        family_total = sum(r[4] for r in records)
        family_paid  = sum(r[5] for r in records)
        family_bal   = sum(r[6] for r in records)

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
        cpdf.drawString(20, y, f"TOTAL PAID: Rs {family_paid:.2f}")
        y -= 16

        cpdf.setFillColorRGB(1, 0, 0)
        cpdf.drawString(20, y, f"BALANCE: Rs {family_bal:.2f}")
        cpdf.setFillColorRGB(0, 0, 0)
        y -= 40

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
                f"Students: {len(records)} | Total: {family_total} | Paid: {family_paid} | Balance: {family_bal}"
            )
        except:
            pass


    # ---------- RECEIPT PRINT ----------
    def generate_single_student_receipt():
        # paste YOUR OLD generate_thermal_receipt() code here
        if not selected_record_id.get():
            messagebox.showwarning("Select", "Select a record first.")
            return
        
        name = name_entry.get().strip()
        s_class = entry_class_box.get()
        
        try:
            total = float(total_entry.get() or 0)
            paid = float(paid_entry.get() or 0)
        except ValueError:
            messagebox.showerror("Error", "Invalid amount in Total or Paid fields.")
            return
            
        purpose_str = purpose_entry.get()

        # --- DB Logic for Receipt No & Mode ---
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT receipt_no, payment_mode FROM students WHERE id=?", (selected_record_id.get(),))
        data = c.fetchone()
        receipt_no, pay_mode = data[0], data[1]
        
        if not receipt_no or receipt_no == "None":
            receipt_no = get_next_receipt_no()
            c.execute("UPDATE students SET receipt_no=? WHERE id=?", (receipt_no, selected_record_id.get()))
            conn.commit()
        conn.close()

        try:
            balance = total - paid
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
            cpdf.drawString(20, y, f"Balance: Rs. {balance:.2f}")
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


    # --- UPDATED SAVE DATA ---
    def save_data():
        global purpose_items, siblings, sibling_mode, name_entry, class_entry, paid_entry, purpose_var

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
                'items': list(purpose_items)
            })

        if not all_to_save:
            messagebox.showerror("Error", "No items added to save!")
            return

        # 3. Save to DB using WATERFALL logic
        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()

            # Paid for whole family
            # --- PAYMENT VALIDATION ---
            paid_text = paid_entry.get().strip()
            payment_mode = payment_mode_box.get().strip()  # your payment dropdown widget

            if paid_text == "" or payment_mode == "":
                messagebox.showerror("Error", "Please enter Paid Amount and select Payment Mode")
                return

            try:
                remaining_paid = float(paid_text)
            except ValueError:
                messagebox.showerror("Error", "Invalid Paid Amount")
                return
            
            family_id = str(uuid.uuid4())[:8]   # like 9f2a7b01

            for student in all_to_save:

                # Total for this student
                student_total = sum(p for _, p in student['items'])

                # Waterfall distribution
                if remaining_paid >= student_total:
                    paid_amount = student_total
                    remaining_paid -= student_total
                else:
                    paid_amount = remaining_paid
                    remaining_paid = 0

                balance = student_total - paid_amount

                # Purpose text: Fee (1000), Books (500)
                p_text = ", ".join([f"{n} ({p})" for n, p in student['items']])

                cursor.execute("""
                    INSERT INTO students
                    (name, student_class, purpose, total, paid, payment_mode, balance, date_added, family_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    student['name'],
                    student['class'],
                    p_text,
                    student_total,
                    paid_amount,
                    payment_mode,
                    balance,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    family_id,
                ))

                # --- AUDIT LOG ENTRY ---
                cursor.execute("""
                INSERT INTO activity_log (timestamp, action_type, details)
                VALUES (?, ?, ?)
                """, (
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "INSERT",
                    f"{'ADMIN' if user_role=='ADMIN' else 'STAFF'} INSERTED -> "
                    f"Name:{student['name']} | Class:{student['class']} | "
                    f"Purpose:{p_text} | Total:{student_total} | "
                    f"Paid:{paid_amount} | Balance:{balance} | Mode:{payment_mode}"
                ))

            conn.commit()
            conn.close()

            messagebox.showinfo("Success", f"Saved {len(all_to_save)} student(s) successfully!")
            reset_ui()

        except Exception as e:
            messagebox.showerror("Database Error", f"Critical Error: {e}")

        try:
            add_audit(
            "RECEIPT",
            f"{user_role} PRINTED RECEIPT | Name: {name} | Class: {s_class} | "
            f"Total: {total} | Paid: {paid} | Balance: {balance}"
        )
        except:
            pass

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

        # Show bar
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
        total_p = sum(row[5] for row in rows)
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
            f"Total Collected: Rs. {total_p} | "
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
        total_p = sum(row[5] for row in rows)
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
            f"Total Collected: Rs. {total_p} | "
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
        last_balance = rows[0][6]     # Last transaction balance

        conn.close()

        summary_text = (
            f"🔍 Search Results | "
            f"Student: {student_name} | "
            f"Class: {s_class} | "
            f"Last Balance: Rs. {last_balance}"
        )

        text_color = "red" if last_balance > 0 else "darkgreen"
        update_summary_bar(summary_text, text_color)


    def fill_balance_if_needed(event):
        global purpose_items
        if purpose_entry.get() != "Balance":
            return

        name = name_entry.get().strip()
        student_class = entry_class_box.get().strip()

        if not name or not student_class:
            messagebox.showwarning("Missing Data",
                               "Select student name and class first.")
            return

        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT total, paid 
                FROM students
                WHERE LOWER(TRIM(name)) = LOWER(TRIM(?))
                AND LOWER(TRIM(student_class)) = LOWER(TRIM(?))
                ORDER BY id DESC LIMIT 1
                """,
                (name, student_class)
            )

            row = cursor.fetchone()
            conn.close()

            if not row:
                messagebox.showwarning("Not Found",
                                   "No record found for this student.")
                return None

            total = float(row[0])
            paid = float(row[1])
            balance = total - paid

            if balance <= 0:
                messagebox.showinfo("No Balance",
                                "This student has no pending balance.")
                return None
            
            return balance

        except Exception as e:
            messagebox.showerror("Error", str(e))
            return None

    def generate_pdf():
        name = search_name_entry.get().strip()

        if not name:
            messagebox.showwarning("PDF Error", "Enter a student name.")
            return

        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()

            # 🔥 Get ALL records of student (latest first)
            cursor.execute("""
                SELECT date_added, purpose, total, paid, balance, payment_mode 
                FROM students 
                WHERE name = ? COLLATE NOCASE
                ORDER BY id DESC
                """, (name,))

            rows = cursor.fetchall()
            conn.close()

            if not rows:
                messagebox.showerror("Error", f"No data found for '{name}'.")
                return

            filename = f"{name}_report.pdf"
            c = canvas.Canvas(filename, pagesize=letter)

            # -------- Header --------
            c.setFont("Helvetica-Bold", 18)
            c.drawString(180, 760, "Fee Payment Report")

            c.setFont("Helvetica", 12)
            c.drawString(50, 735, f"Student Name : {name}")
            c.line(40, 720, 570, 720)

            # -------- Print All Records --------
            y = 700
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

                # 👉 If the page fills, create a new page
                if y < 120:
                    c.showPage()
                    c.setFont("Helvetica", 12)
                    y = 760

            c.save()

            add_audit("PDF EXPORT", f"{user_role} generated FULL REPORT for: {name}")
            messagebox.showinfo("Success", f"PDF saved as {filename}")

        except Exception as e:
            messagebox.showerror("PDF Error", str(e))


    def delete_record():
        if not selected_record_id.get(): 
            messagebox.showwarning("Selection Required", "Select a record to delete.")
            return
            
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM students WHERE id = ?", (selected_record_id.get(),))
        record = cursor.fetchone()
        
        if record and messagebox.askyesno("Confirm", f"Delete record for {record[1]}?"):
            audit_text = (
                f"DELETE -> ID:{record[0]} | Name:{record[1]} | Class:{record[2]} | "
                f"Purpose:{record[3]} | Total:{record[4]} | Paid:{record[5]} | "
                f"Balance:{record[6]} | Date:{record[7]} | Receipt:{record[8]} | Mode:{record[9]}"
            )
            cursor.execute("DELETE FROM students WHERE id = ?", (selected_record_id.get(),))
            conn.commit()
            add_audit("DELETE", f"{user_role} {audit_text}")
            reset_ui()
        conn.close()


    def update_record():
        if not selected_record_id.get(): 
            messagebox.showwarning("Selection Required", "Please select a record to update.")
            return
        try:
            new_name = name_entry.get().strip()
            new_class = entry_class_box.get()
            new_purpose = purpose_entry.get()
            new_total = float(total_entry.get())
            new_paid = float(paid_entry.get())
            new_balance = new_total - new_paid
            
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()

            cursor.execute("SELECT name, student_class, purpose, total, paid, balance FROM students WHERE id=?",
                           (selected_record_id.get(),))
            old = cursor.fetchone()

            cursor.execute("SELECT family_id FROM students WHERE id=?", (selected_record_id.get(),))
            fam = cursor.fetchone()[0]
            new_family_id = fam

            cursor.execute("""
                UPDATE students 
                SET name=?, student_class=?, purpose=?, total=?, paid=?, balance=?, family_id=?
                WHERE id=?""",
                (new_name, new_class, new_purpose, new_total, new_paid, new_balance, new_family_id, selected_record_id.get()))
            
            conn.commit()
            conn.close()

            audit_text = (
                f"UPDATE ID:{selected_record_id.get()} -> "
                f"[BEFORE] Name:{old[0]} | Class:{old[1]} | Purpose:{old[2]} | "
                f"Total:{old[3]} | Paid:{old[4]} | Balance:{old[5]}    ||    "
                f"[AFTER] Name:{new_name} | Class:{new_class} | Purpose:{new_purpose} | "
                f"Total:{new_total} | Paid:{new_paid} | Balance:{new_balance}"
            )

            add_audit("UPDATE", f"{user_role} {audit_text}")
            messagebox.showinfo("Success", "Record updated.")
            reset_ui()
        except ValueError: 
            messagebox.showerror("Error", "Check numeric inputs")


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


    def on_click(event):
        global sibling_mode, siblings, purpose_items

        # ---- RESET SIBLING MODE ----
        sibling_mode = False
        siblings = []
        purpose_items = []
        purpose_var.set("")

        try:
            sibling_status.set("Sibling Mode: 0 Students")
        except:
            pass

        item = tree.selection()
        if not item:
            return

        v = tree.item(item)["values"]
        selected_record_id.set(v[0])

        # 🔥 ALWAYS CLEAR BLUE PURPOSE PREVIEW TEXT
        try:
            purpose_var.set("")          # clear linked variable
            purpose_display.config(text="")   # force clear label
        except:
            pass

        student_name = v[1]
        student_class = v[2]
        family = v[3]
        purpose_text = v[4]
        total = v[5]
        paid = v[6]
        payment = v[7]
        balance = v[8]

        # -----------------------------------
        #  FILL DATA ENTRY INPUT FIELDS
        # -----------------------------------
        name_entry.delete(0, tk.END)
        name_entry.insert(0, student_name)

        entry_class_box.set(student_class)

        purpose_entry.delete(0, tk.END)
        purpose_entry.insert(0, purpose_text)

        # build purpose_items list
        purpose_items = []
        raw_items = purpose_text.split(",")

        for item in raw_items:
            item = item.strip()
            if "(" in item and ")" in item:
                name_part = item.split("(")[0].strip()
                price_part = item.split("(")[1].replace(")", "").strip()
                try:
                    price_val = float(price_part)
                except:
                    price_val = 0
                purpose_items.append((name_part, price_val))

        total_entry.delete(0, tk.END)
        total_entry.insert(0, total)

        paid_entry.delete(0, tk.END)
        paid_entry.insert(0, paid)

        payment_mode_box.set(payment)

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
        # FAMILY SUMMARY
        # -----------------------------------
        try:
            if family and family != "None":
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT COUNT(*), SUM(total), SUM(paid), SUM(balance)
                    FROM students
                    WHERE family_id = ?
                """, (family,))

                count, fam_total, fam_paid, fam_balance = cursor.fetchone()
                conn.close()

                msg = (
                    f"👨‍👩‍👧 FAMILY: {family}  |  "
                    f"Members: {count}  |  "
                    f"Total: {fam_total}  |  "
                    f"Paid: {fam_paid}  |  "
                    f"Balance: {fam_balance}"
                )

                update_summary_bar(msg, "#0B5345")
                sibling_status.set(f"Sibling Group: {count} Student(s)")
            else:
                try:
                    summary_canvas.delete("all")
                    summary_canvas.pack_forget()     # 🔥 FORCE REMOVE BLUE BAR
                except:
                    pass

            sibling_status.set("Sibling Mode: 0 Students")

        except Exception as e:
            print("Summary Error:", e)

    # ⬇️ PUT FUNCTION HERE
    def toggle_sibling_mode():
        global sibling_mode, siblings

        sibling_mode = not sibling_mode

        if sibling_mode:
            siblings = []
            messagebox.showinfo(
                "Sibling Billing",
                "Sibling Billing Mode ENABLED.\n\n"
                "You can add multiple students and combine payment."
            )

            sibling_btn.config(text="Disable Sibling Mode")
            name_entry.config(bg="#e8f8ff")

        else:
            siblings = []          # clear siblings
            sibling_mode = False   # ensure it is off

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
    audit_btn.grid(row=0, column=7, padx=10)

    if user_role == "STAFF":
        audit_btn.config(state="disabled", bg="gray")

    
    tk.Button(top_frame, text="📥 PDF Export", command=generate_pdf, bg="green", fg="white", width=12).grid(row=0, column=8)
    tk.Button(top_frame, text="🗑️ Delete", command=delete_record, bg="black", fg="white", width=10).grid(row=0, column=9, padx=5)
    tk.Button(top_frame, text="🔄 Reset", command=reset_ui, bg="#7F8C8D", fg="white", width=10).grid(row=0, column=10)
    tk.Button(top_frame, text="🔓 Logout", command=logout, bg="#E74C3C", fg="white", font=("Arial", 9, "bold"), width=10).grid(row=0, column=11, padx=20)

    global search_name_entry, search_class_box

    search_frame = tk.LabelFrame(root, text="Quick Search", fg="orange", font=("Arial", 10, "bold"))
    search_frame.pack(pady=5, fill="x", padx=20)
    tk.Label(search_frame, text="Student Name:").grid(row=0, column=0, padx=5)
    search_name_entry = tk.Entry(search_frame, width=30); search_name_entry.grid(row=0, column=1)
    tk.Label(search_frame, text="Filter Class:").grid(row=0, column=2, padx=10)
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
    
    item_list = ["Monthly Fee", "Admission", "Books", "Uniform", "Exam Fee","Balance", "Diary"]
    purpose_entry = ttk.Combobox(entry_frame, textvariable=purpose_var, values=item_list)
    purpose_entry.grid(row=0, column=5, padx=5)
    purpose_entry.bind("<<ComboboxSelected>>", fill_balance_if_needed)

    # Binds the selection event to trigger the price popup
    purpose_entry.bind("<<ComboboxSelected>>", handle_selection)

    tk.Label(entry_frame, text="Total:").grid(row=1, column=0); 
    global total_entry
    total_entry = tk.Entry(entry_frame) # Ensure it starts with 't' 
    total_entry.grid(row=1, column=1, pady=5)

    tk.Label(entry_frame, text="Paid:").grid(row=1, column=2); 
    global paid_entry
    paid_entry = tk.Entry(entry_frame); 
    paid_entry.grid(row=1, column=3)

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

    # --- ADD THIS HERE ---
    # This replaces the old Message widget to allow for a clean list-style preview
    purpose_display = tk.Label(
        root, 
        textvariable=purpose_var, 
        font=("Arial", 10, "bold"), 
        fg="blue", 
        justify="left",   # Aligns the names and bullet points to the left
        anchor="w",       # West alignment
        wraplength=500    # If the family is very large, it wraps to a new line
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
        u=user_entry.get().strip()
        p=pw_entry.get()
        
        if u=="admin" and p=="admin123":
            add_audit("LOGIN","ADMIN logged in")
            login_scr.destroy(); main_app("ADMIN")
        elif u=="staff" and p=="staff123":
            add_audit("LOGIN","STAFF logged in")
            login_scr.destroy(); main_app("STAFF")
        else:
            messagebox.showerror("Denied","Invalid Credentials")

    tk.Button(login_scr,text="Enter",command=check_login,bg="blue",fg="white",width=12).pack(pady=20)
    login_scr.mainloop()


init_db()

show_login_screen()