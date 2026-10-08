from flask import Flask, render_template, request, redirect, url_for, session, send_file
import mysql.connector
import os
import base64
from io import BytesIO
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

try:
    import qrcode
except ImportError:
    qrcode = None

app = Flask(__name__)
app.secret_key = os.environ.get('STUDENT_SECRET_KEY')
app.config['SESSION_COOKIE_NAME'] = 'student_secure_session'

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def build_upi_payment_qr(upi_id, amount, fee_type):
    """Return an amount-specific UPI URI and an embeddable QR image for laptop payments."""
    upi_uri = 'upi://pay?' + urlencode({
        'pa': upi_id,
        'pn': 'BCE Hostel',
        'am': f'{amount:.2f}',
        'cu': 'INR',
        'tn': f'Hostel fee - {fee_type}'[:80]
    })
    if qrcode is None:
        return upi_uri, None
    image = qrcode.make(upi_uri)
    image_bytes = BytesIO()
    image.save(image_bytes, format='PNG')
    qr_image = base64.b64encode(image_bytes.getvalue()).decode('ascii')
    return upi_uri, qr_image

def connect_db():
    return mysql.connector.connect(
        host=os.environ.get('DB_HOST'),
        database=os.environ.get('DB_NAME'),
        user=os.environ.get('DB_USER'),
        password=os.environ.get('DB_PASSWORD'),
        port=int(os.environ.get('DB_PORT', 3306))
    )
    


def ensure_allocation_eligibility_column():
    """Support allocation removal even if the official portal has not started yet."""
    conn = connect_db()
    if not conn:
        return
    cursor = conn.cursor()
    try:
        cursor.execute("SHOW COLUMNS FROM Students LIKE 'Allocation_Eligible'")
        if not cursor.fetchone():
            cursor.execute(
                "ALTER TABLE Students ADD COLUMN Allocation_Eligible BOOLEAN NOT NULL DEFAULT TRUE AFTER Address"
            )
            conn.commit()
    except Exception:
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


def ensure_room_request_visibility_column():
    conn = connect_db()
    if not conn:
        return
    cursor = conn.cursor()
    try:
        cursor.execute("SHOW COLUMNS FROM Students LIKE 'Room_Request_Visible'")
        if not cursor.fetchone():
            cursor.execute(
                "ALTER TABLE Students ADD COLUMN Room_Request_Visible BOOLEAN NOT NULL DEFAULT FALSE AFTER Allocation_Eligible"
            )
            conn.commit()
    except Exception:
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


def ensure_payment_requests_table():
    conn = connect_db()
    if not conn:
        return
    cursor = conn.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS Payment_Requests (
                Payment_Request_ID INT AUTO_INCREMENT PRIMARY KEY,
                Student_Fee_ID INT NOT NULL, Student_ID VARCHAR(50) NOT NULL,
                Amount DECIMAL(10, 2) NOT NULL, UTR_Reference VARCHAR(100) NOT NULL,
                Payment_Method VARCHAR(50) NOT NULL DEFAULT 'UPI',
                Status ENUM('Pending Verification', 'Verified', 'Rejected') NOT NULL DEFAULT 'Pending Verification',
                Submitted_At TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, Reviewed_At DATETIME,
                Reviewed_By VARCHAR(50), Review_Notes TEXT,
                FOREIGN KEY (Student_Fee_ID) REFERENCES Student_Fees(Student_Fee_ID) ON DELETE CASCADE,
                FOREIGN KEY (Student_ID) REFERENCES Students(Student_ID) ON DELETE CASCADE,
                FOREIGN KEY (Reviewed_By) REFERENCES Users(User_ID) ON DELETE SET NULL
            )
        """)
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


try:
    ensure_allocation_eligibility_column()
    ensure_room_request_visibility_column()
    ensure_payment_requests_table()
except Exception:
    pass


def log_audit(cursor, action, entity_type, entity_id=None, details=None, actor_id=None):
    """Compatibility placeholder: audit logging has been removed from the portal."""
    return None

@app.route('/', methods=['GET', 'POST'])
def student_login():
    error = request.args.get('error')
    if request.method == 'POST':
        user_id = request.form.get('user_id').strip()
        password = request.form.get('password')
        
        conn = connect_db()
        if conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM Users WHERE User_ID = %s AND Role = 'Student'", (user_id,))
            user = cursor.fetchone()
            
            if user:
                if check_password_hash(user['Password'], password):
                    session['loggedin'] = True
                    session['user_id'] = user['User_ID']
                    session['role'] = user['Role']
                    cursor.close()
                    conn.close()
                    return redirect(url_for('student_dashboard'))
                else:
                    error = "Invalid password. Please try again."
                    cursor.close()
                    conn.close()
            else:
                error = "Account not found! Please register first."
                cursor.close()
                conn.close()
                
    return render_template('student_login_v2.html', error=error)

@app.route('/register', methods=['GET', 'POST'])
def register_student():
    error, message = None, None
    if request.method == 'POST':
        user_id = request.form.get('user_id').strip()
        name = request.form.get('name').strip()
        email = request.form.get('email').strip()
        phone = request.form.get('phone').strip()
        branch = request.form.get('branch').strip()
        year = request.form.get('year')
        gender = request.form.get('gender')
        address = request.form.get('address', '').strip() or None
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if password != confirm_password:
            error = "Passwords do not match!"
        else:
            conn = connect_db()
            if conn:
                cursor = conn.cursor(dictionary=True)
                try:
                    cursor.execute("SELECT * FROM Users WHERE User_ID = %s", (user_id,))
                    if cursor.fetchone():
                        error = "Student ID already registered! Please sign in instead."
                    else:
                        hashed_pw = generate_password_hash(password)
                        
                        cursor.execute("""
                            INSERT INTO Users (User_ID, Password, Role, Name, Email, Phone) 
                            VALUES (%s, %s, 'Student', %s, %s, %s)
                        """, (user_id, hashed_pw, name, email, phone))
                        
                        cursor.execute("""
                            INSERT INTO Students (Student_ID, Name, Phone, Branch, Year, Gender, Address)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, (user_id, name, phone, branch, year, gender, address))
                        # Registration can be opened with a stale browser session.
                        # Record the newly inserted user, not any prior session user.
                        log_audit(cursor, 'Registered student account', 'Student', user_id, name,
                                  actor_id=user_id)
                        
                        conn.commit()
                        message = "Registration successful! You can now log in."
                except Exception as e:
                    conn.rollback()
                    error = f"Registration error: {e}"
                finally:
                    cursor.close()
                    conn.close()
                    
    return render_template('register_student_v2.html', error=error, message=message)

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    error, message = None, None
    if request.method == 'POST':
        user_id = request.form.get('user_id').strip()
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if new_password != confirm_password:
            error = "New passwords do not match!"
        else:
            conn = connect_db()
            if conn:
                cursor = conn.cursor(dictionary=True)
                try:
                    cursor.execute("SELECT * FROM Users WHERE User_ID = %s AND Role = 'Student'", (user_id,))
                    user = cursor.fetchone()
                    if not user:
                        error = "Student ID not found in the system!"
                    else:
                        hashed_pw = generate_password_hash(new_password)
                        cursor.execute("UPDATE Users SET Password = %s WHERE User_ID = %s", (hashed_pw, user_id))
                        conn.commit()
                        message = "Password successfully reset! You can now log in."
                except Exception as e:
                    conn.rollback()
                    error = f"Error updating password: {e}"
                finally:
                    cursor.close()
                    conn.close()
                    
    return render_template('forgot_password_v2.html', error=error, message=message)

@app.route('/about')
def about():
    return render_template('about_v2.html')

@app.route('/contact')
def contact():
    return render_template('contact_v2.html')

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404_v2.html'), 404

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('student_login'))

@app.route('/student_dashboard')
def student_dashboard():
    if not session.get('loggedin') or session.get('role') != 'Student':
        return redirect(url_for('student_login'))
        
    student_id = session.get('user_id')
    conn = connect_db()
    student_data, allocation, requests_list, notices = {}, None, [], []
    if conn:
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("SELECT * FROM Students WHERE Student_ID = %s", (student_id,))
        student_data = cursor.fetchone()
        cursor.fetchall()
        
        cursor.execute("SELECT * FROM Allocations WHERE Student_ID = %s AND Status = 'Active'", (student_id,))
        allocation = cursor.fetchone()
        cursor.fetchall()
        
        # A request only stores the preferred room type.  The actual room number is
        # stored in Allocations after an official approves the request, so include
        # the active allocation when building the request history for the dashboard.
        cursor.execute("""
            SELECT r.*, a.Room_No AS Allocated_Room_No, a.Hostel_No AS Allocated_Hostel_No
            FROM Room_Requests r
            LEFT JOIN Allocations a
                ON a.Student_ID = r.Student_ID AND a.Status = 'Active'
            WHERE r.Student_ID = %s
            ORDER BY r.Request_ID DESC
        """, (student_id,))
        requests_list = cursor.fetchall()

        cursor.execute("""
            SELECT Notice_ID, Title, Message, Notice_Type, Category, Published_At, Is_Pinned
            FROM Notices
            WHERE Audience IN ('All', 'Students')
              AND (Expires_At IS NULL OR Expires_At > NOW())
            ORDER BY Is_Pinned DESC, Published_At DESC
            LIMIT 3
        """)
        notices = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
    return render_template('student_dashboard_v2.html', student=student_data, allocation=allocation,
                           requests=requests_list, notices=notices)

@app.route('/request_room', methods=['GET', 'POST'])
def request_room():
    if not session.get('loggedin') or session.get('role') != 'Student':
        return redirect(url_for('student_login'))
        
    message, error = None, None
    student_id = session.get('user_id')
    
    conn = connect_db()
    if conn:
        cursor = conn.cursor(dictionary=True)

        # A deleted student can still have an old browser session. Do not allow
        # that stale session to submit a request that would violate the foreign key.
        cursor.execute("SELECT Student_ID FROM Students WHERE Student_ID = %s", (student_id,))
        student_profile = cursor.fetchone()
        if not student_profile:
            cursor.close()
            conn.close()
            session.clear()
            return redirect(url_for(
                'student_login',
                error='Your student profile is no longer available. Please sign in again or register a new account.'
            ))
        
        if request.method == 'POST':
            hostel = request.form.get('preferred_hostel')
            room_type = request.form.get('preferred_room_type')
            reason = request.form.get('reason', '').strip()
            if not reason:
                reason = "No reason provided."
                
            # Check if student currently has an active room allocation
            cursor.execute("SELECT * FROM Allocations WHERE Student_ID = %s AND Status = 'Active'", (student_id,))
            active_alloc = cursor.fetchone()
            cursor.fetchall() 
            
            # Check if student currently has a pending request
            cursor.execute("SELECT * FROM Room_Requests WHERE Student_ID = %s AND Status = 'Pending'", (student_id,))
            pending_request = cursor.fetchone()
            cursor.fetchall() 
            
            if active_alloc:
                error = "You already have an active room allocation. You cannot request another room."
            elif pending_request:
                error = "You already have a pending room request waiting for official approval."
            else:
                try:
                    # A new request opts the student back into the allocation
                    # workflow; bulk allocation still skips pending requests.
                    cursor.execute(
                        "UPDATE Students SET Allocation_Eligible = TRUE, Room_Request_Visible = TRUE WHERE Student_ID = %s",
                        (student_id,)
                    )
                    cursor.execute("""
                        INSERT INTO Room_Requests (Student_ID, Preferred_Hostel, Preferred_Room_Type, Reason, Status) 
                        VALUES (%s, %s, %s, %s, 'Pending')
                    """, (student_id, hostel, room_type, reason))
                    log_audit(cursor, 'Submitted room request', 'Room_Request', cursor.lastrowid, f'{hostel}, {room_type}-seater')
                    conn.commit()
                    message = "Room request submitted successfully!"
                except Exception as e:
                    conn.rollback()
                    error = f"Error: {e}"
        cursor.close()
        conn.close()
        
    return render_template('request_room_v2.html', message=message, error=error)

@app.route('/student_support', methods=['GET', 'POST'])
def student_support():
    if not session.get('loggedin') or session.get('role') != 'Student':
        return redirect(url_for('student_login'))
    message, error = None, None
    student_id = session.get('user_id')
    if request.method == 'POST':
        subject = request.form.get('subject')
        msg_body = request.form.get('message')
        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO Support_Tickets (Student_ID, Subject, Message, Status) 
                    VALUES (%s, %s, %s, 'Open')
                """, (student_id, subject, msg_body))
                log_audit(cursor, 'Submitted support ticket', 'Support_Ticket', cursor.lastrowid, subject)
                conn.commit()
                message = "Support message sent successfully!"
            except Exception as e:
                conn.rollback()
                error = f"Error: {e}"
            finally:
                cursor.close()
                conn.close()
                
    conn = connect_db()
    tickets = []
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM Support_Tickets WHERE Student_ID = %s ORDER BY Ticket_ID DESC", (student_id,))
        tickets = cursor.fetchall()
        cursor.close()
        conn.close()
    return render_template('student_support_v2.html', message=message, error=error, tickets=tickets)

@app.route('/student_profile', methods=['GET', 'POST'])
def student_profile():
    if not session.get('loggedin') or session.get('role') != 'Student':
        return redirect(url_for('student_login'))
    student_id = session.get('user_id')
    conn = connect_db()
    message = None
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        address = request.form.get('address', '').strip() or None
        file = request.files.get('profile_pic')
        if conn:
            cursor = conn.cursor()
            try:
                if file and file.filename != '':
                    filename = secure_filename(f"{student_id}_{file.filename}")
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    cursor.execute("UPDATE Users SET Name=%s, Email=%s, Phone=%s, Profile_Pic=%s WHERE User_ID=%s", (name, email, phone, filename, student_id))
                else:
                    cursor.execute("UPDATE Users SET Name=%s, Email=%s, Phone=%s WHERE User_ID=%s", (name, email, phone, student_id))
                cursor.execute("UPDATE Students SET Name=%s, Phone=%s, Address=%s WHERE Student_ID=%s", (name, phone, address, student_id))
                conn.commit()
                message = "Profile updated successfully!"
            except Exception as e:
                conn.rollback()
                message = f"Error: {e}"
            finally:
                cursor.close()
                conn.close()
                
    conn = connect_db()
    student_data = {}
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT s.*, u.Email, u.Profile_Pic FROM Students s LEFT JOIN Users u ON s.Student_ID = u.User_ID WHERE s.Student_ID = %s", (student_id,))
        student_data = cursor.fetchone()
        cursor.close()
        conn.close()
    return render_template('student_profile_v2.html', student=student_data, message=message)


@app.route('/notices')
def student_notices():
    if not session.get('loggedin') or session.get('role') != 'Student':
        return redirect(url_for('student_login'))

    notices = []
    conn = connect_db()
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT n.*, COALESCE(u.Name, n.Published_By, 'Hostel Office') AS Publisher_Name
            FROM Notices n
            LEFT JOIN Users u ON n.Published_By = u.User_ID
            WHERE n.Audience IN ('All', 'Students')
              AND (n.Expires_At IS NULL OR n.Expires_At > NOW())
            ORDER BY n.Is_Pinned DESC, n.Published_At DESC
            """
        )
        notices = cursor.fetchall()
        cursor.close()
        conn.close()
    return render_template('notices.html', portal='student', notices=notices)


@app.route('/my_fees')
def student_fees():
    if not session.get('loggedin') or session.get('role') != 'Student':
        return redirect(url_for('student_login'))

    fees, payment_requests = [], []
    conn = connect_db()
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT Student_Fee_ID, Fee_Type, Amount_Due, Amount_Paid, Start_Date, End_Date, Status,
                   Payment_Method, Transaction_Reference, Paid_At, Remarks
            FROM Student_Fees
            WHERE Student_ID = %s
            ORDER BY End_Date IS NULL, End_Date DESC, Student_Fee_ID DESC
            """, (session['user_id'],)
        )
        fees = cursor.fetchall()
        cursor.execute("""
            SELECT Payment_Request_ID, Student_Fee_ID, Amount, UTR_Reference, Status,
                   Submitted_At, Review_Notes
            FROM Payment_Requests WHERE Student_ID = %s
            ORDER BY Payment_Request_ID DESC
        """, (session['user_id'],))
        payment_requests = cursor.fetchall()
        cursor.close()
        conn.close()
    return render_template('student_fees.html', portal='student', fees=fees,
                           payment_requests=payment_requests,
                           upi_id=os.environ.get('HOSTEL_UPI_ID', 'singeshwarkumar1@ybl'),
                           success=request.args.get('success'), error=request.args.get('error'))


@app.route('/my_fees/<int:student_fee_id>/payment', methods=['POST'])
def submit_fee_payment(student_fee_id):
    if not session.get('loggedin') or session.get('role') != 'Student':
        return redirect(url_for('student_login'))
    try:
        amount = Decimal(request.form.get('amount', '0'))
    except InvalidOperation:
        amount = Decimal('0')
    utr_reference = request.form.get('utr_reference', '').strip()
    payment_method = request.form.get('payment_method', 'UPI').strip()
    allowed_payment_methods = {'UPI', 'Debit / Credit Card', 'Net Banking', 'Wallet'}
    if payment_method not in allowed_payment_methods:
        payment_method = 'UPI'
    if amount <= 0 or not utr_reference:
        return redirect(url_for('student_fees', error='Enter a valid payment amount and UTR / transaction reference.'))

    conn = connect_db()
    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT Amount_Due, Amount_Paid FROM Student_Fees
                WHERE Student_Fee_ID = %s AND Student_ID = %s
            """, (student_fee_id, session['user_id']))
            fee = cursor.fetchone()
            if not fee or amount > fee['Amount_Due'] - fee['Amount_Paid']:
                return redirect(url_for('student_fees', error='Payment amount exceeds the remaining balance.'))
            cursor.execute("SELECT 1 FROM Payment_Requests WHERE UTR_Reference = %s", (utr_reference,))
            if cursor.fetchone():
                return redirect(url_for('student_fees', error='This transaction reference was already submitted.'))
            cursor.execute("""
            INSERT INTO Payment_Requests (Student_Fee_ID, Student_ID, Amount, UTR_Reference, Payment_Method)
            VALUES (%s, %s, %s, %s, %s)
            """, (student_fee_id, session['user_id'], amount, utr_reference, payment_method))
            log_audit(cursor, 'Submitted fee payment for verification', 'Payment_Request', cursor.lastrowid, utr_reference)
            conn.commit()
            return redirect(url_for('student_fees', success='Payment submitted for official verification.'))
        except Exception as e:
            conn.rollback()
            return redirect(url_for('student_fees', error=f'Could not submit payment: {e}'))
        finally:
            cursor.close()
            conn.close()
    return redirect(url_for('student_fees', error='Could not connect to the database.'))


@app.route('/my_fees/<int:student_fee_id>/pay')
def payment_browser(student_fee_id):
    if not session.get('loggedin') or session.get('role') != 'Student':
        return redirect(url_for('student_login'))
    conn = connect_db()
    fee = None
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT Student_Fee_ID, Fee_Type, Amount_Due, Amount_Paid, Start_Date, End_Date
            FROM Student_Fees WHERE Student_Fee_ID = %s AND Student_ID = %s
        """, (student_fee_id, session['user_id']))
        fee = cursor.fetchone()
        cursor.close()
        conn.close()
    if not fee or fee['Amount_Due'] <= fee['Amount_Paid']:
        return redirect(url_for('student_fees', error='This fee is unavailable for payment.'))
    balance = fee['Amount_Due'] - fee['Amount_Paid']
    upi_id = os.environ.get('HOSTEL_UPI_ID', 'singeshwarkumar1@ybl')
    upi_uri, qr_image = build_upi_payment_qr(upi_id, balance, fee['Fee_Type'])
    return render_template('payment_browser.html', fee=fee, balance=balance,
                           upi_id=upi_id, upi_uri=upi_uri, qr_image=qr_image)


@app.route('/my_fees/<int:student_fee_id>/upi-qr.png')
def payment_upi_qr(student_fee_id):
    """Serve a fresh PNG QR code so laptop browsers always display it correctly."""
    if not session.get('loggedin') or session.get('role') != 'Student' or qrcode is None:
        return '', 404
    conn = connect_db()
    fee = None
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT Student_Fee_ID, Fee_Type, Amount_Due, Amount_Paid
            FROM Student_Fees WHERE Student_Fee_ID = %s AND Student_ID = %s
        """, (student_fee_id, session['user_id']))
        fee = cursor.fetchone()
        cursor.close()
        conn.close()
    if not fee or fee['Amount_Due'] <= fee['Amount_Paid']:
        return '', 404
    balance = fee['Amount_Due'] - fee['Amount_Paid']
    try:
        amount = Decimal(request.args.get('amount', str(balance)))
    except InvalidOperation:
        return '', 400
    if amount <= 0 or amount > balance:
        return '', 400
    upi_uri, _ = build_upi_payment_qr(
        os.environ.get('HOSTEL_UPI_ID', 'singeshwarkumar1@ybl'), amount, fee['Fee_Type']
    )
    image = qrcode.make(upi_uri)
    image_bytes = BytesIO()
    image.save(image_bytes, format='PNG')
    image_bytes.seek(0)
    return send_file(image_bytes, mimetype='image/png', max_age=0)


@app.route('/emergency_contacts', methods=['GET', 'POST'])
def emergency_contacts():
    if not session.get('loggedin') or session.get('role') != 'Student':
        return redirect(url_for('student_login'))

    student_id = session['user_id']
    if request.method == 'POST':
        contact_name = request.form.get('contact_name', '').strip()
        relationship = request.form.get('relationship', '').strip()
        phone = request.form.get('phone', '').strip()
        alternate_phone = request.form.get('alternate_phone', '').strip() or None
        email = request.form.get('email', '').strip() or None
        address = request.form.get('address', '').strip() or None
        is_primary = bool(request.form.get('is_primary'))
        if not contact_name or not relationship or not phone:
            return redirect(url_for('emergency_contacts', error='Name, relationship, and phone number are required.'))

        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            try:
                if is_primary:
                    cursor.execute('UPDATE Emergency_Contacts SET Is_Primary = FALSE WHERE Student_ID = %s', (student_id,))
                cursor.execute(
                    """
                    INSERT INTO Emergency_Contacts
                    (Student_ID, Contact_Name, Relationship, Phone, Alternate_Phone, Email, Address, Is_Primary)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (student_id, contact_name, relationship, phone, alternate_phone, email, address, is_primary)
                )
                contact_id = cursor.lastrowid
                log_audit(cursor, 'Added emergency contact', 'Emergency_Contact', contact_id, contact_name)
                conn.commit()
                return redirect(url_for('emergency_contacts', success='Emergency contact saved.'))
            except Exception as e:
                conn.rollback()
                return redirect(url_for('emergency_contacts', error=f'Could not save contact: {e}'))
            finally:
                cursor.close()
                conn.close()

    contacts = []
    conn = connect_db()
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            'SELECT * FROM Emergency_Contacts WHERE Student_ID = %s ORDER BY Is_Primary DESC, Contact_Name',
            (student_id,)
        )
        contacts = cursor.fetchall()
        cursor.close()
        conn.close()
    return render_template('emergency_contacts.html', portal='student', contacts=contacts,
                           success=request.args.get('success'), error=request.args.get('error'))


@app.route('/emergency_contacts/<int:contact_id>/delete', methods=['POST'])
def delete_emergency_contact(contact_id):
    if not session.get('loggedin') or session.get('role') != 'Student':
        return redirect(url_for('student_login'))

    conn = connect_db()
    if conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                'DELETE FROM Emergency_Contacts WHERE Emergency_Contact_ID = %s AND Student_ID = %s',
                (contact_id, session['user_id'])
            )
            if cursor.rowcount:
                log_audit(cursor, 'Deleted emergency contact', 'Emergency_Contact', contact_id)
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            cursor.close()
            conn.close()
    return redirect(url_for('emergency_contacts'))


@app.route('/maintenance_request', methods=['GET', 'POST'])
def submit_maintenance():
    if not session.get('loggedin') or session.get('role') != 'Student':
        return redirect(url_for('student_login'))

    student_id = session['user_id']
    if request.method == 'POST':
        category = request.form.get('category', '').strip()
        description = request.form.get('description', '').strip()
        priority = request.form.get('priority', 'Medium')
        if not category or not description:
            return redirect(url_for('submit_maintenance', error='Category and description are required.'))
        if priority not in ('Low', 'Medium', 'High', 'Emergency'):
            return redirect(url_for('submit_maintenance', error='Invalid maintenance priority.'))

        conn = connect_db()
        if conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute(
                    """
                    SELECT Room_No, Hostel_No FROM Allocations
                    WHERE Student_ID = %s AND Status = 'Active'
                    LIMIT 1
                    """, (student_id,)
                )
                allocation = cursor.fetchone()
                cursor.fetchall()
                room_no = allocation['Room_No'] if allocation else None
                hostel_no = allocation['Hostel_No'] if allocation else None
                cursor.execute(
                    """
                    INSERT INTO Maintenance_Complaints
                    (Student_ID, Room_No, Hostel_No, Category, Description, Priority)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """, (student_id, room_no, hostel_no, category, description, priority)
                )
                complaint_id = cursor.lastrowid
                log_audit(cursor, 'Submitted maintenance complaint', 'Maintenance_Complaint', complaint_id, category)
                conn.commit()
                return redirect(url_for('submit_maintenance', success='Maintenance complaint submitted.'))
            except Exception as e:
                conn.rollback()
                return redirect(url_for('submit_maintenance', error=f'Could not submit complaint: {e}'))
            finally:
                cursor.close()
                conn.close()

    complaints, allocation = [], None
    conn = connect_db()
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT Room_No, Hostel_No FROM Allocations
            WHERE Student_ID = %s AND Status = 'Active'
            LIMIT 1
            """, (student_id,)
        )
        allocation = cursor.fetchone()
        cursor.fetchall()
        cursor.execute(
            """
            SELECT Complaint_ID, Room_No, Hostel_No, Category, Description, Priority, Status,
                   Resolution_Notes, Created_At, Updated_At, Resolved_At
            FROM Maintenance_Complaints
            WHERE Student_ID = %s
            ORDER BY Created_At DESC
            """, (student_id,)
        )
        complaints = cursor.fetchall()
        cursor.close()
        conn.close()
    return render_template('maintenance_request.html', portal='student', complaints=complaints,
                           allocation=allocation, success=request.args.get('success'), error=request.args.get('error'))

if __name__ == '__main__':
    app.run(debug=True, port=5002)
