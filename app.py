from flask import Flask, render_template, request, redirect, url_for, session
import mysql.connector
from datetime import date
from decimal import Decimal, InvalidOperation
import os
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ['SECRET_KEY']
app.config['SESSION_COOKIE_NAME'] = 'official_secure_session'

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
HOSTEL_UPI_ID = os.environ.get('HOSTEL_UPI_ID', 'singeshwarkumar1@ybl')

def connect_db():
    return mysql.connector.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        port=int(os.environ.get('DB_PORT', '3306')),
        database=os.environ.get('DB_NAME', 'HostelManagement'),
        user=os.environ.get('DB_USER', 'root'),
        password=os.environ['DB_PASSWORD']
    )
    


def log_audit(cursor, action, entity_type, entity_id=None, details=None):
    """Compatibility placeholder: audit logging has been removed from the portal."""
    return None

HOSTEL_LAYOUTS = {
    # (floor name, single-seater rooms, triple-seater rooms)
    # Every listed floor contains single-seater rooms.
    'Hostel 1': (
        ('Ground', 16, 16), ('1st', 17, 17), ('2nd', 17, 17),
    ),  # 50 single + 50 triple rooms = 200 beds
    'Hostel 2': (
        ('Ground', 16, 16), ('1st', 17, 17), ('2nd', 17, 17),
    ),  # 50 single + 50 triple rooms = 200 beds
    'Hostel 3': (
        ('Ground', 13, 13), ('1st', 13, 13), ('2nd', 13, 13),
        ('3rd', 12, 12), ('4th', 12, 12), ('5th', 12, 12),
    ),  # 75 single + 75 triple rooms = 300 beds
}


def init_all_hostels():
    """Create any missing rooms without changing existing room allocations."""
    conn = connect_db()
    if not conn:
        return

    cursor = conn.cursor()
    try:
        rooms_to_create = []
        for hostel_name, floors in HOSTEL_LAYOUTS.items():
            for floor_name, single_count, triple_count in floors:
                room_counter = 1
                prefix = 'G-' if floor_name == 'Ground' else floor_name[0]

                for _ in range(single_count):
                    rooms_to_create.append(
                        (f'{prefix}{room_counter:02d}', hostel_name, 1, 0)
                    )
                    room_counter += 1

                for _ in range(triple_count):
                    rooms_to_create.append(
                        (f'{prefix}{room_counter:02d}', hostel_name, 3, 0)
                    )
                    room_counter += 1

        # Room_No and Hostel_No are a composite primary key. INSERT IGNORE keeps
        # existing rooms and their occupancy intact while adding Hostel 2/3.
        cursor.executemany(
            """
            INSERT IGNORE INTO Rooms (Room_No, Hostel_No, Capacity, Current_Occupancy)
            VALUES (%s, %s, %s, %s)
            """,
            rooms_to_create,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def ensure_single_room_per_student():
    """Prevent more than one allocation record for the same student."""
    conn = connect_db()
    if not conn:
        return

    cursor = conn.cursor()
    try:
        cursor.execute("SHOW INDEX FROM Allocations WHERE Key_name = 'uq_allocations_student'")
        if not cursor.fetchone():
            cursor.execute(
                "ALTER TABLE Allocations ADD CONSTRAINT uq_allocations_student UNIQUE (Student_ID)"
            )
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def ensure_student_address_column():
    """Add address storage for installations created before the biodata feature."""
    conn = connect_db()
    if not conn:
        return

    cursor = conn.cursor()
    try:
        cursor.execute("SHOW COLUMNS FROM Students LIKE 'Address'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE Students ADD COLUMN Address TEXT NULL AFTER Gender")
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def ensure_allocation_eligibility_column():
    """Keep removed students in the portal while excluding them from bulk allocation."""
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
        raise
    finally:
        cursor.close()
        conn.close()


def ensure_room_request_visibility_column():
    """Keep new sign-ups out of the official directory until they request a room."""
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
            # Preserve visibility for existing students that already requested
            # or received a room before this feature was added.
            cursor.execute("""
                UPDATE Students s
                SET Room_Request_Visible = TRUE
                WHERE EXISTS (SELECT 1 FROM Room_Requests r WHERE r.Student_ID = s.Student_ID)
                   OR EXISTS (SELECT 1 FROM Allocations a WHERE a.Student_ID = s.Student_ID)
            """)
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def ensure_fee_date_range_columns():
    """Upgrade fee records from a single due date to a start/end date range."""
    conn = connect_db()
    if not conn:
        return
    cursor = conn.cursor()
    try:
        for table_name in ('Fee_Structures', 'Student_Fees'):
            cursor.execute(f"SHOW COLUMNS FROM {table_name} LIKE 'Start_Date'")
            if not cursor.fetchone():
                cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN Start_Date DATE NULL")
            cursor.execute(f"SHOW COLUMNS FROM {table_name} LIKE 'End_Date'")
            if not cursor.fetchone():
                cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN End_Date DATE NULL")
        # Preserve historical due dates as the end date for existing fee data.
        cursor.execute("UPDATE Fee_Structures SET End_Date = Due_Date WHERE End_Date IS NULL AND Due_Date IS NOT NULL")
        cursor.execute("UPDATE Student_Fees SET End_Date = Due_Date WHERE End_Date IS NULL AND Due_Date IS NOT NULL")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def ensure_payment_requests_table():
    """Create the student-submitted UPI payment verification queue."""
    conn = connect_db()
    if not conn:
        return
    cursor = conn.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS Payment_Requests (
                Payment_Request_ID INT AUTO_INCREMENT PRIMARY KEY,
                Student_Fee_ID INT NOT NULL,
                Student_ID VARCHAR(50) NOT NULL,
                Amount DECIMAL(10, 2) NOT NULL,
                UTR_Reference VARCHAR(100) NOT NULL,
                Payment_Method VARCHAR(50) NOT NULL DEFAULT 'UPI',
                Status ENUM('Pending Verification', 'Verified', 'Rejected') NOT NULL DEFAULT 'Pending Verification',
                Submitted_At TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                Reviewed_At DATETIME,
                Reviewed_By VARCHAR(50),
                Review_Notes TEXT,
                FOREIGN KEY (Student_Fee_ID) REFERENCES Student_Fees(Student_Fee_ID) ON DELETE CASCADE,
                FOREIGN KEY (Student_ID) REFERENCES Students(Student_ID) ON DELETE CASCADE,
                FOREIGN KEY (Reviewed_By) REFERENCES Users(User_ID) ON DELETE SET NULL,
                INDEX idx_payment_requests_status (Status, Submitted_At),
                INDEX idx_payment_requests_student_fee (Student_ID, Student_Fee_ID)
            )
        """)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def sync_room_occupancy():
    """Keep official room counters equal to the number of active allocations."""
    conn = connect_db()
    if not conn:
        return
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE Rooms r
            LEFT JOIN (
                SELECT Room_No, Hostel_No, COUNT(*) AS occupied
                FROM Allocations WHERE Status = 'Active'
                GROUP BY Room_No, Hostel_No
            ) a ON a.Room_No = r.Room_No AND a.Hostel_No = r.Hostel_No
            SET r.Current_Occupancy = LEAST(r.Capacity, COALESCE(a.occupied, 0))
        """)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


try:
    init_all_hostels()
    ensure_single_room_per_student()
    ensure_student_address_column()
    ensure_allocation_eligibility_column()
    ensure_room_request_visibility_column()
    ensure_fee_date_range_columns()
    ensure_payment_requests_table()
    sync_room_occupancy()
except Exception:
    pass

@app.route('/', methods=['GET', 'POST'])
def login():
    error = None

    if request.method == 'POST':
        user_id = request.form.get('user_id', '').strip()
        password = request.form.get('password', '')

        conn = connect_db()

        if conn:
            cursor = conn.cursor(dictionary=True)

            try:
                cursor.execute(
                    "SELECT * FROM Users WHERE User_ID = %s AND Role = 'Official'",
                    (user_id,)
                )
                user = cursor.fetchone()

                if user:
                    if check_password_hash(user['Password'], password):
                        session['loggedin'] = True
                        session['user_id'] = user['User_ID']
                        session['role'] = user['Role']

                        return redirect(url_for('official_dashboard'))
                    else:
                        error = "Invalid password. Please check your credentials."
                else:
                    error = "Official account not found. Please contact the administrator."

            except Exception:
                error = "Unable to process login. Please try again."

            finally:
                cursor.close()
                conn.close()

    return render_template('login_v2.html', error=error)

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
    return redirect(url_for('login'))

@app.route('/official_dashboard')
def official_dashboard():
    if not session.get('loggedin') or session.get('role') != 'Official':
        return redirect(url_for('login'))
    conn = connect_db()
    rooms, allocations, room_requests, available_rooms = [], [], [], []
    room_stats, hostel_stats = {}, []
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM Rooms ORDER BY Hostel_No, Room_No;")
        rooms = cursor.fetchall()
        
        cursor.execute("""
            SELECT a.Allocation_ID, a.Room_No, a.Hostel_No, s.Student_ID, s.Name, s.Branch, a.Move_In_Date 
            FROM Allocations a
            JOIN Students s ON a.Student_ID = s.Student_ID
            WHERE a.Status = 'Active'
            ORDER BY a.Hostel_No ASC, a.Room_No ASC;
        """)
        allocations = cursor.fetchall()
        
        cursor.execute("""
            SELECT r.*, COALESCE(s.Name, 'Unknown') AS Name, COALESCE(s.Branch, 'N/A') AS Branch 
            FROM Room_Requests r 
            LEFT JOIN Students s ON r.Student_ID = s.Student_ID 
            WHERE r.Status = 'Pending';
        """)
        room_requests = cursor.fetchall()

        cursor.execute("""
            SELECT Room_No, Hostel_No, Capacity, Current_Occupancy
            FROM Rooms
            WHERE Current_Occupancy < Capacity
            ORDER BY Hostel_No, Room_No
        """)
        available_rooms = cursor.fetchall()
        cursor.execute("""
            SELECT COUNT(*) AS room_count, COALESCE(SUM(Capacity), 0) AS total_beds,
                   COALESCE(SUM(Current_Occupancy), 0) AS occupied_beds,
                   COALESCE(SUM(Capacity - Current_Occupancy), 0) AS vacant_beds
            FROM Rooms
        """)
        room_stats = cursor.fetchone()
        cursor.execute("""
            SELECT Hostel_No, COUNT(*) AS room_count, SUM(Capacity) AS total_beds,
                   SUM(Current_Occupancy) AS occupied_beds,
                   SUM(Capacity - Current_Occupancy) AS vacant_beds
            FROM Rooms GROUP BY Hostel_No ORDER BY Hostel_No
        """)
        hostel_stats = cursor.fetchall()
        cursor.close()
        conn.close()
    return render_template('official_dashboard_v2.html', rooms=rooms, allocations=allocations,
                           room_requests=room_requests, available_rooms=available_rooms,
                           room_stats=room_stats, hostel_stats=hostel_stats,
                           success=request.args.get('success'), error=request.args.get('error'))

@app.route('/approve_request/<int:request_id>', methods=['POST'])
def approve_request(request_id):
    if not session.get('loggedin') or session.get('role') != 'Official':
        return redirect(url_for('login'))
    conn = connect_db()
    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            # A request can only be approved once. Lock it while assigning a room.
            cursor.execute(
                "SELECT * FROM Room_Requests WHERE Request_ID = %s AND Status = 'Pending' FOR UPDATE",
                (request_id,)
            )
            req = cursor.fetchone()
            if req:
                student_id = req['Student_ID']
                selected_room = request.form.get('selected_room', '')
                try:
                    room_no, hostel = selected_room.split('|', 1)
                except ValueError:
                    return redirect(url_for('official_dashboard', error='Select a valid vacant room first.'))

                cursor.execute(
                    "SELECT Allocation_ID FROM Allocations WHERE Student_ID = %s FOR UPDATE",
                    (student_id,)
                )
                existing_allocation = cursor.fetchone()
                if existing_allocation:
                    cursor.execute(
                        "UPDATE Room_Requests SET Status = 'Rejected' WHERE Request_ID = %s",
                        (request_id,)
                    )
                    log_audit(
                        cursor, 'Rejected duplicate room request', 'Room_Request', request_id,
                        f'{student_id} already has an active room allocation'
                    )
                else:
                    cursor.execute(
                        """
                        SELECT Room_No, Capacity, Current_Occupancy FROM Rooms
                        WHERE Room_No = %s AND Hostel_No = %s
                          AND Current_Occupancy < Capacity
                        FOR UPDATE
                        """,
                        (room_no, hostel)
                    )
                    vacant = cursor.fetchone()
                    if vacant:
                        today = date.today()
                        cursor.execute("INSERT INTO Allocations (Student_ID, Room_No, Hostel_No, Move_In_Date, Status) VALUES (%s, %s, %s, %s, 'Active')", (student_id, room_no, hostel, today))
                        cursor.execute("UPDATE Rooms SET Current_Occupancy = Current_Occupancy + 1 WHERE Room_No = %s AND Hostel_No = %s", (room_no, hostel))
                        cursor.execute("UPDATE Room_Requests SET Status = 'Approved' WHERE Request_ID = %s", (request_id,))
                        log_audit(cursor, 'Approved room request', 'Room_Request', request_id, f'{student_id} assigned to {hostel}, room {room_no}')
                    else:
                        return redirect(url_for('official_dashboard', error='That room is no longer vacant. Choose another room.'))
                conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()
    return redirect(url_for('official_dashboard', success='Room allocated successfully.'))

@app.route('/deny_request/<int:request_id>')
def deny_request(request_id):
    if not session.get('loggedin') or session.get('role') != 'Official':
        return redirect(url_for('login'))
    conn = connect_db()
    if conn:
        cursor = conn.cursor()
        try:
            cursor.execute("UPDATE Room_Requests SET Status = 'Rejected' WHERE Request_ID = %s", (request_id,))
            if cursor.rowcount:
                log_audit(cursor, 'Rejected room request', 'Room_Request', request_id)
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            cursor.close()
            conn.close()
    return redirect(url_for('official_dashboard'))

@app.route('/rooms_chart')
def rooms_chart():
    if not session.get('loggedin') or session.get('role') != 'Official':
        return redirect(url_for('login'))
    sync_room_occupancy()
    conn = connect_db()
    rooms, rooms_by_hostel, full_rooms_by_hostel = [], {}, {}
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM Rooms ORDER BY Hostel_No, Room_No;")
        rooms = cursor.fetchall()
        cursor.close()
        conn.close()
    for room in rooms:
        rooms_by_hostel.setdefault(room['Hostel_No'], []).append(room)
        if room['Current_Occupancy'] >= room['Capacity']:
            full_rooms_by_hostel.setdefault(room['Hostel_No'], []).append(room)
    return render_template('rooms_chart_v2.html', rooms=rooms, rooms_by_hostel=rooms_by_hostel,
                           full_rooms_by_hostel=full_rooms_by_hostel)

@app.route('/support_inbox')
def support_inbox():
    if not session.get('loggedin') or session.get('role') != 'Official':
        return redirect(url_for('login'))
    conn = connect_db()
    tickets = []
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT t.*, COALESCE(s.Name, 'Unknown') AS Student_Name, COALESCE(s.Branch, 'N/A') AS Branch 
            FROM Support_Tickets t 
            LEFT JOIN Students s ON t.Student_ID = s.Student_ID 
            ORDER BY t.Ticket_ID DESC;
        """)
        tickets = cursor.fetchall()
        cursor.close()
        conn.close()
    return render_template('support_inbox_v2.html', tickets=tickets)

@app.route('/official_profile', methods=['GET', 'POST'])
def official_profile():
    if not session.get('loggedin') or session.get('role') != 'Official':
        return redirect(url_for('login'))
    conn = connect_db()
    message = None
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        file = request.files.get('profile_pic')
        if conn:
            cursor = conn.cursor()
            try:
                if file and file.filename != '':
                    filename = secure_filename(f"{session['user_id']}_{file.filename}")
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    cursor.execute("UPDATE Users SET Name=%s, Email=%s, Phone=%s, Profile_Pic=%s WHERE User_ID=%s",
                                   (name, email, phone, filename, session['user_id']))
                else:
                    cursor.execute("UPDATE Users SET Name=%s, Email=%s, Phone=%s WHERE User_ID=%s",
                                   (name, email, phone, session['user_id']))
                conn.commit()
                message = "Profile updated successfully!"
            except Exception as e:
                conn.rollback()
                message = f"Error: {e}"
            finally:
                cursor.close()
                conn.close()
    conn = connect_db()
    staff_data = {}
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM Users WHERE User_ID = %s", (session['user_id'],))
        staff_data = cursor.fetchone()
        cursor.close()
        conn.close()
    return render_template('official_profile_v2.html', staff=staff_data, message=message)

@app.route('/registered_students')
def registered_students():
    if not session.get('loggedin') or session.get('role') != 'Official':
        return redirect(url_for('login'))
    conn = connect_db()
    students = []
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT s.Student_ID, s.Name, s.Phone, s.Branch, s.Year, s.Gender, s.Allocation_Eligible,
                   COALESCE(a.Room_No, 'Not Assigned') AS Room_No,
                   COALESCE(a.Hostel_No, '') AS Hostel_No
            FROM Students s
            LEFT JOIN Allocations a ON s.Student_ID = a.Student_ID AND a.Status = 'Active'
            WHERE s.Room_Request_Visible = TRUE;
        """)
        students = cursor.fetchall()
        cursor.close()
        conn.close()
    return render_template('registered_students_v2.html', students=students)


@app.route('/student_biodata/<student_id>')
def student_biodata(student_id):
    """Show an official-only, complete record for one student."""
    if not session.get('loggedin') or session.get('role') != 'Official':
        return redirect(url_for('login'))

    student = None
    allocation = None
    emergency_contacts, fees, support_tickets, complaints = [], [], [], []
    fee_summary = {'total_due': Decimal('0.00'), 'total_paid': Decimal('0.00'), 'balance': Decimal('0.00')}
    conn = connect_db()
    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT s.*, u.Email, u.Profile_Pic
                FROM Students s
                LEFT JOIN Users u ON u.User_ID = s.Student_ID
                WHERE s.Student_ID = %s
            """, (student_id,))
            student = cursor.fetchone()

            if student:
                cursor.execute("""
                    SELECT a.Room_No, a.Hostel_No, a.Move_In_Date, r.Capacity, r.Current_Occupancy
                    FROM Allocations a
                    LEFT JOIN Rooms r ON r.Room_No = a.Room_No AND r.Hostel_No = a.Hostel_No
                    WHERE a.Student_ID = %s AND a.Status = 'Active'
                    LIMIT 1
                """, (student_id,))
                allocation = cursor.fetchone()

                cursor.execute("""
                    SELECT Contact_Name, Relationship, Phone, Alternate_Phone, Email, Address, Is_Primary
                    FROM Emergency_Contacts
                    WHERE Student_ID = %s
                    ORDER BY Is_Primary DESC, Emergency_Contact_ID DESC
                """, (student_id,))
                emergency_contacts = cursor.fetchall()

                cursor.execute("""
                    SELECT Student_Fee_ID, Fee_Type, Amount_Due, Amount_Paid, Start_Date, End_Date, Status,
                           Payment_Method, Transaction_Reference, Paid_At, Remarks
                    FROM Student_Fees
                    WHERE Student_ID = %s
                    ORDER BY End_Date IS NULL, End_Date DESC, Student_Fee_ID DESC
                """, (student_id,))
                fees = cursor.fetchall()

                cursor.execute("""
                    SELECT COALESCE(SUM(Amount_Due), 0) AS total_due,
                           COALESCE(SUM(Amount_Paid), 0) AS total_paid,
                           COALESCE(SUM(Amount_Due - Amount_Paid), 0) AS balance
                    FROM Student_Fees
                    WHERE Student_ID = %s
                """, (student_id,))
                fee_summary = cursor.fetchone()

                cursor.execute("""
                    SELECT Ticket_ID, Subject, Message, Status, Created_At
                    FROM Support_Tickets
                    WHERE Student_ID = %s
                    ORDER BY Ticket_ID DESC
                """, (student_id,))
                support_tickets = cursor.fetchall()

                cursor.execute("""
                    SELECT Complaint_ID, Room_No, Hostel_No, Category, Description, Priority, Status,
                           Resolution_Notes, Created_At, Resolved_At
                    FROM Maintenance_Complaints
                    WHERE Student_ID = %s
                    ORDER BY Complaint_ID DESC
                """, (student_id,))
                complaints = cursor.fetchall()
        finally:
            cursor.close()
            conn.close()

    if not student:
        return render_template('404_v2.html'), 404

    return render_template(
        'student_biodata.html', student=student, allocation=allocation,
        emergency_contacts=emergency_contacts, fees=fees, fee_summary=fee_summary,
        support_tickets=support_tickets, complaints=complaints,
    )

@app.route('/edit_student/<student_id>', methods=['GET', 'POST'])
def edit_student(student_id):
    if not session.get('loggedin') or session.get('role') != 'Official':
        return redirect(url_for('login'))
    conn = connect_db()
    message = None
    if request.method == 'POST':
        name = request.form.get('name')
        branch = request.form.get('branch')
        year = request.form.get('year')
        phone = request.form.get('phone')
        gender = request.form.get('gender')
        if conn:
            cursor = conn.cursor()
            try:
                address = request.form.get('address', '').strip() or None
                cursor.execute("UPDATE Students SET Name=%s, Branch=%s, Year=%s, Phone=%s, Gender=%s, Address=%s WHERE Student_ID=%s", (name, branch, year, phone, gender, address, student_id))
                cursor.execute("UPDATE Users SET Name=%s, Phone=%s WHERE User_ID=%s", (name, phone, student_id))
                conn.commit()
                message = "Student details updated successfully!"
            except Exception as e:
                conn.rollback()
                message = f"Error: {e}"
            finally:
                cursor.close()
                conn.close()
    conn = connect_db()
    student = {}
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM Students WHERE Student_ID = %s", (student_id,))
        student = cursor.fetchone()
        cursor.close()
        conn.close()
    return render_template('edit_student_v2.html', student=student, message=message)

@app.route('/manual_allocate/<student_id>', methods=['GET', 'POST'])
def manual_allocate(student_id):
    if not session.get('loggedin') or session.get('role') != 'Official':
        return redirect(url_for('login'))
        
    conn = connect_db()
    error = None
        
    if request.method == 'POST':
        new_room_data = request.form.get('new_room')
        
        if new_room_data and conn:
            new_room_no, new_hostel_no = new_room_data.split('|')
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute("SELECT Current_Occupancy, Capacity FROM Rooms WHERE Room_No=%s AND Hostel_No=%s", (new_room_no, new_hostel_no))
                room_check = cursor.fetchone()
                cursor.fetchall() 
                
                if room_check and room_check['Current_Occupancy'] < room_check['Capacity']:
                    cursor.execute("SELECT Room_No, Hostel_No FROM Allocations WHERE Student_ID=%s AND Status='Active'", (student_id,))
                    current_alloc = cursor.fetchone()
                    cursor.fetchall() 
                    
                    if current_alloc:
                        cursor.execute("UPDATE Rooms SET Current_Occupancy = GREATEST(Current_Occupancy - 1, 0) WHERE Room_No=%s AND Hostel_No=%s", (current_alloc['Room_No'], current_alloc['Hostel_No']))
                        cursor.execute("DELETE FROM Allocations WHERE Student_ID=%s AND Status='Active'", (student_id,))
                    
                    today = date.today()
                    cursor.execute("INSERT INTO Allocations (Student_ID, Room_No, Hostel_No, Move_In_Date, Status) VALUES (%s, %s, %s, %s, 'Active')", (student_id, new_room_no, new_hostel_no, today))
                    cursor.execute("UPDATE Rooms SET Current_Occupancy = Current_Occupancy + 1 WHERE Room_No=%s AND Hostel_No=%s", (new_room_no, new_hostel_no))
                    
                    conn.commit()
                    cursor.close()
                    conn.close()
                    return redirect(url_for('registered_students'))
                else:
                    error = "Selected room is full or does not exist."
            except Exception as e:
                conn.rollback()
                error = f"Error updating allocation: {e}"
            finally:
                if cursor:
                    cursor.close()
                if conn:
                    conn.close()

    student_info, current_allocation, available_rooms = {}, None, []
        
    conn = connect_db()
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT Name, Student_ID FROM Students WHERE Student_ID=%s", (student_id,))
        student_info = cursor.fetchone()
        cursor.fetchall() 
        
        cursor.execute("SELECT Room_No, Hostel_No FROM Allocations WHERE Student_ID=%s AND Status='Active'", (student_id,))
        current_allocation = cursor.fetchone()
        cursor.fetchall()
        
        cursor.execute("SELECT Room_No, Hostel_No, Capacity, Current_Occupancy FROM Rooms WHERE Current_Occupancy < Capacity ORDER BY Hostel_No, Room_No")
        available_rooms = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
    return render_template('manual_allocate_v2.html', student=student_info, available_rooms=available_rooms, current_allocation=current_allocation, error=error)

@app.route('/unallocate_student/<student_id>')
def unallocate_student(student_id):
    if not session.get('loggedin') or session.get('role') != 'Official':
        return redirect(url_for('login'))
    conn = connect_db()
    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT Room_No, Hostel_No FROM Allocations WHERE Student_ID = %s AND Status = 'Active'", (student_id,))
            alloc = cursor.fetchone()
            if alloc:
                cursor.execute("UPDATE Rooms SET Current_Occupancy = GREATEST(Current_Occupancy - 1, 0) WHERE Room_No = %s AND Hostel_No = %s", (alloc['Room_No'], alloc['Hostel_No']))
                cursor.execute("DELETE FROM Allocations WHERE Student_ID = %s AND Status = 'Active'", (student_id,))
                conn.commit()
        except Exception:
            conn.rollback()
        finally:
            cursor.close()
            conn.close()
    return redirect(url_for('registered_students'))

@app.route('/delete_student/<student_id>', methods=['POST'])
def delete_student(student_id):
    """Remove a student from allocation without deleting their portal profile."""
    if not session.get('loggedin') or session.get('role') != 'Official':
        return redirect(url_for('login'))

    conn = connect_db()
    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            # Release the bed and disable automatic allocation, while preserving
            # the student's profile, fees, contacts, and portal access.
            cursor.execute(
                "SELECT Room_No, Hostel_No FROM Allocations WHERE Student_ID = %s AND Status = 'Active'",
                (student_id,)
            )
            allocation = cursor.fetchone()
            if allocation:
                cursor.execute(
                    "UPDATE Rooms SET Current_Occupancy = GREATEST(Current_Occupancy - 1, 0) WHERE Room_No = %s AND Hostel_No = %s",
                    (allocation['Room_No'], allocation['Hostel_No'])
                )

            cursor.execute("DELETE FROM Allocations WHERE Student_ID = %s AND Status = 'Active'", (student_id,))
            cursor.execute("UPDATE Room_Requests SET Status = 'Cancelled' WHERE Student_ID = %s AND Status = 'Pending'", (student_id,))
            cursor.execute("UPDATE Students SET Allocation_Eligible = FALSE, Room_Request_Visible = FALSE WHERE Student_ID = %s", (student_id,))
            if cursor.rowcount:
                log_audit(cursor, 'Removed student from allocation', 'Student', student_id)
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            cursor.close()
            conn.close()
    return redirect(url_for('registered_students'))

@app.route('/bulk_allocation', methods=['GET', 'POST'])
def bulk_allocation():
    if not session.get('loggedin') or session.get('role') != 'Official':
        return redirect(url_for('login'))
        
    message = None
    if request.method == 'POST':
        room_type = request.form.get('room_type')
        conn = connect_db()
        if conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute("""
                    SELECT s.Student_ID FROM Students s
                    LEFT JOIN Allocations a ON s.Student_ID = a.Student_ID AND a.Status = 'Active'
                    LEFT JOIN Room_Requests r ON s.Student_ID = r.Student_ID AND r.Status = 'Pending'
                    WHERE a.Student_ID IS NULL AND r.Student_ID IS NULL
                      AND s.Allocation_Eligible = TRUE
                """)
                unassigned = cursor.fetchall()
                allocated_count = 0
                for student in unassigned:
                    if room_type:
                        cursor.execute("SELECT Room_No, Hostel_No FROM Rooms WHERE Capacity = %s AND Current_Occupancy < Capacity ORDER BY Hostel_No, Room_No LIMIT 1", (room_type,))
                    else:
                        cursor.execute("SELECT Room_No, Hostel_No FROM Rooms WHERE Current_Occupancy < Capacity ORDER BY Hostel_No, Room_No LIMIT 1")
                    
                    room = cursor.fetchone()
                    if not room:
                        break
                        
                    today = date.today()
                    cursor.execute("INSERT INTO Allocations (Student_ID, Room_No, Hostel_No, Move_In_Date, Status) VALUES (%s, %s, %s, %s, 'Active')", (student['Student_ID'], room['Room_No'], room['Hostel_No'], today))
                    cursor.execute("UPDATE Rooms SET Current_Occupancy = Current_Occupancy + 1 WHERE Room_No=%s AND Hostel_No=%s", (room['Room_No'], room['Hostel_No']))
                    allocated_count += 1
                conn.commit()
                
                if allocated_count:
                    message = f"Success! {allocated_count} student(s) were automatically allocated a room."
                else:
                    message = "No unassigned students or no vacant rooms of the selected type were found."
            except Exception as e:
                conn.rollback()
                message = f"Error running bulk allocation: {e}"
            finally:
                cursor.close()
                conn.close()
                
    return render_template('bulk_allocate_v2.html', message=message)

@app.route('/resolve_ticket/<int:ticket_id>')
def resolve_ticket(ticket_id):
    if not session.get('loggedin') or session.get('role') != 'Official':
        return redirect(url_for('login'))
        
    conn = connect_db()
    if conn:
        cursor = conn.cursor()
        try:
            cursor.execute("UPDATE Support_Tickets SET Status = 'Resolved' WHERE Ticket_ID = %s", (ticket_id,))
            if cursor.rowcount:
                log_audit(cursor, 'Resolved support ticket', 'Support_Ticket', ticket_id)
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            cursor.close()
            conn.close()
            
    return redirect(url_for('support_inbox'))


@app.route('/notices', methods=['GET', 'POST'])
def manage_notices():
    if not session.get('loggedin') or session.get('role') != 'Official':
        return redirect(url_for('login'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        message = request.form.get('message', '').strip()
        notice_type = request.form.get('notice_type', 'Notice')
        category = request.form.get('category', 'General').strip() or 'General'
        audience = request.form.get('audience', 'All')
        expires_at = request.form.get('expires_at') or None
        is_pinned = 1 if request.form.get('is_pinned') else 0

        if not title or not message:
            return redirect(url_for('manage_notices', error='Title and message are required.'))
        if notice_type not in ('Notice', 'Announcement') or audience not in ('All', 'Students', 'Officials'):
            return redirect(url_for('manage_notices', error='Invalid notice settings.'))

        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    INSERT INTO Notices
                    (Title, Message, Notice_Type, Category, Audience, Published_By, Expires_At, Is_Pinned)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (title, message, notice_type, category, audience, session['user_id'], expires_at, is_pinned)
                )
                notice_id = cursor.lastrowid
                log_audit(cursor, 'Created notice', 'Notice', notice_id, title)
                conn.commit()
                return redirect(url_for('manage_notices', success='Notice published successfully.'))
            except Exception as e:
                conn.rollback()
                return redirect(url_for('manage_notices', error=f'Could not publish notice: {e}'))
            finally:
                cursor.close()
                conn.close()

    notices = []
    conn = connect_db()
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT n.*, COALESCE(u.Name, n.Published_By, 'System') AS Publisher_Name
            FROM Notices n
            LEFT JOIN Users u ON n.Published_By = u.User_ID
            ORDER BY n.Is_Pinned DESC, n.Published_At DESC
            """
        )
        notices = cursor.fetchall()
        cursor.close()
        conn.close()
    return render_template('notices.html', portal='official', notices=notices,
                           success=request.args.get('success'), error=request.args.get('error'))


@app.route('/notices/<int:notice_id>/delete', methods=['POST'])
def delete_notice(notice_id):
    if not session.get('loggedin') or session.get('role') != 'Official':
        return redirect(url_for('login'))

    conn = connect_db()
    if conn:
        cursor = conn.cursor()
        try:
            cursor.execute('DELETE FROM Notices WHERE Notice_ID = %s', (notice_id,))
            if cursor.rowcount:
                log_audit(cursor, 'Deleted notice', 'Notice', notice_id)
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            cursor.close()
            conn.close()
    return redirect(url_for('manage_notices'))


@app.route('/fees', methods=['GET', 'POST'])
def fee_management():
    if not session.get('loggedin') or session.get('role') != 'Official':
        return redirect(url_for('login'))

    if request.method == 'POST':
        action = request.form.get('action')
        conn = connect_db()
        if conn:
            cursor = conn.cursor(dictionary=True)
            try:
                if action == 'create_structure':
                    fee_type = request.form.get('fee_type', '').strip()
                    academic_year = request.form.get('academic_year', '').strip()
                    start_date = request.form.get('start_date') or None
                    end_date = request.form.get('end_date') or None
                    description = request.form.get('description', '').strip() or None
                    try:
                        amount = Decimal(request.form.get('amount', ''))
                    except InvalidOperation:
                        amount = Decimal('-1')
                    if not fee_type or not academic_year or amount < 0 or not start_date or not end_date or start_date > end_date:
                        return redirect(url_for('fee_management', error='Enter a valid fee type, amount, and academic year.'))
                    cursor.execute(
                        """
                        INSERT INTO Fee_Structures (Fee_Type, Amount, Academic_Year, Start_Date, End_Date, Description)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """, (fee_type, amount, academic_year, start_date, end_date, description)
                    )
                    structure_id = cursor.lastrowid
                    log_audit(cursor, 'Created fee structure', 'Fee_Structure', structure_id, fee_type)

                elif action == 'assign_fee':
                    student_ids = request.form.getlist('student_ids')
                    if request.form.get('assign_to_all'):
                        cursor.execute('SELECT Student_ID FROM Students ORDER BY Student_ID')
                        student_ids = [student['Student_ID'] for student in cursor.fetchall()]
                    structure_id = request.form.get('fee_structure_id', type=int)
                    if not student_ids or not structure_id:
                        return redirect(url_for('fee_management', error='Choose at least one student and fee structure.'))
                    cursor.execute('SELECT * FROM Fee_Structures WHERE Fee_Structure_ID = %s AND Is_Active = TRUE', (structure_id,))
                    fee_structure = cursor.fetchone()
                    if not fee_structure:
                        return redirect(url_for('fee_management', error='The selected fee structure is unavailable.'))
                    assigned_count, skipped_count = 0, 0
                    for student_id in dict.fromkeys(student_ids):
                        cursor.execute('SELECT 1 FROM Student_Fees WHERE Student_ID = %s AND Fee_Structure_ID = %s', (student_id, structure_id))
                        if cursor.fetchone():
                            skipped_count += 1
                            continue
                        cursor.execute("""
                            INSERT INTO Student_Fees
                            (Student_ID, Fee_Structure_ID, Fee_Type, Amount_Due, Start_Date, End_Date)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (student_id, structure_id, fee_structure['Fee_Type'], fee_structure['Amount'], fee_structure['Start_Date'], fee_structure['End_Date']))
                        assigned_count += 1
                    log_audit(cursor, 'Assigned fee to students', 'Fee_Structure', structure_id,
                              f"{fee_structure['Fee_Type']}: {assigned_count} assigned, {skipped_count} already assigned")
                else:
                    return redirect(url_for('fee_management', error='Unknown fee action.'))

                conn.commit()
                success = 'Fee structure saved successfully.' if action == 'create_structure' else f'Fee assigned to {assigned_count} student(s); {skipped_count} duplicate assignment(s) skipped.'
                return redirect(url_for('fee_management', success=success))
            except Exception as e:
                conn.rollback()
                return redirect(url_for('fee_management', error=f'Could not save fee information: {e}'))
            finally:
                cursor.close()
                conn.close()

    fee_structures, students, student_fees, payment_requests = [], [], [], []
    conn = connect_db()
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT * FROM Fee_Structures WHERE Is_Active = TRUE ORDER BY Academic_Year DESC, Fee_Type')
        fee_structures = cursor.fetchall()
        cursor.execute('SELECT Student_ID, Name, Branch FROM Students ORDER BY Name')
        students = cursor.fetchall()
        cursor.execute(
            """
            SELECT sf.*, s.Name, s.Branch
            FROM Student_Fees sf
            JOIN Students s ON sf.Student_ID = s.Student_ID
            ORDER BY sf.Status, sf.End_Date IS NULL, sf.End_Date, s.Name
            """
        )
        student_fees = cursor.fetchall()
        cursor.execute("""
            SELECT pr.*, s.Name, sf.Fee_Type, sf.Amount_Due, sf.Amount_Paid
            FROM Payment_Requests pr
            JOIN Students s ON s.Student_ID = pr.Student_ID
            JOIN Student_Fees sf ON sf.Student_Fee_ID = pr.Student_Fee_ID
            WHERE pr.Status = 'Pending Verification'
            ORDER BY pr.Submitted_At ASC
        """)
        payment_requests = cursor.fetchall()
        cursor.close()
        conn.close()
    return render_template('fee_management.html', portal='official', fee_structures=fee_structures,
                           students=students, student_fees=student_fees, payment_requests=payment_requests,
                           success=request.args.get('success'), error=request.args.get('error'))


@app.route('/payments/<int:payment_request_id>/review', methods=['POST'])
def review_payment_request(payment_request_id):
    if not session.get('loggedin') or session.get('role') != 'Official':
        return redirect(url_for('login'))
    decision = request.form.get('decision')
    notes = request.form.get('review_notes', '').strip() or None
    if decision not in ('verify', 'reject'):
        return redirect(url_for('fee_management', error='Invalid payment review action.'))
    conn = connect_db()
    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT pr.*, sf.Amount_Due, sf.Amount_Paid
                FROM Payment_Requests pr
                JOIN Student_Fees sf ON sf.Student_Fee_ID = pr.Student_Fee_ID
                WHERE pr.Payment_Request_ID = %s AND pr.Status = 'Pending Verification'
                FOR UPDATE
            """, (payment_request_id,))
            payment = cursor.fetchone()
            if not payment:
                return redirect(url_for('fee_management', error='Payment request is unavailable or already reviewed.'))
            if decision == 'verify':
                new_paid = min(payment['Amount_Due'], payment['Amount_Paid'] + payment['Amount'])
                new_status = 'Paid' if new_paid >= payment['Amount_Due'] else 'Partially Paid'
                cursor.execute("""
                    UPDATE Student_Fees
                    SET Amount_Paid = %s, Status = %s, Payment_Method = %s,
                        Transaction_Reference = %s, Paid_At = NOW()
                    WHERE Student_Fee_ID = %s
                """, (new_paid, new_status, payment['Payment_Method'], payment['UTR_Reference'], payment['Student_Fee_ID']))
                request_status = 'Verified'
                success = 'Payment verified and fee record updated.'
            else:
                request_status = 'Rejected'
                success = 'Payment request rejected.'
            cursor.execute("""
                UPDATE Payment_Requests
                SET Status = %s, Reviewed_At = NOW(), Reviewed_By = %s, Review_Notes = %s
                WHERE Payment_Request_ID = %s
            """, (request_status, session['user_id'], notes, payment_request_id))
            log_audit(cursor, f'{request_status} payment request', 'Payment_Request', payment_request_id, payment['UTR_Reference'])
            conn.commit()
            return redirect(url_for('fee_management', success=success))
        except Exception as e:
            conn.rollback()
            return redirect(url_for('fee_management', error=f'Could not review payment: {e}'))
        finally:
            cursor.close()
            conn.close()
    return redirect(url_for('fee_management', error='Could not connect to the database.'))


@app.route('/fees/<int:student_fee_id>/status', methods=['POST'])
def update_fee_status(student_fee_id):
    if not session.get('loggedin') or session.get('role') != 'Official':
        return redirect(url_for('login'))

    status = request.form.get('status')
    valid_statuses = ('Pending', 'Partially Paid', 'Paid', 'Overdue', 'Waived')
    if status not in valid_statuses:
        return redirect(url_for('fee_management', error='Invalid payment status.'))
    try:
        amount_paid = Decimal(request.form.get('amount_paid', '0'))
    except InvalidOperation:
        return redirect(url_for('fee_management', error='Enter a valid paid amount.'))

    conn = connect_db()
    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute('SELECT Amount_Due FROM Student_Fees WHERE Student_Fee_ID = %s', (student_fee_id,))
            fee = cursor.fetchone()
            if not fee:
                return redirect(url_for('fee_management', error='Fee record not found.'))
            if amount_paid < 0 or amount_paid > fee['Amount_Due']:
                return redirect(url_for('fee_management', error='Paid amount must be between zero and the amount due.'))
            if status == 'Paid':
                amount_paid = fee['Amount_Due']
            cursor.execute(
                """
                UPDATE Student_Fees
                SET Status = %s, Amount_Paid = %s,
                    Payment_Method = %s, Transaction_Reference = %s,
                    Paid_At = CASE WHEN %s IN ('Partially Paid', 'Paid') THEN NOW() ELSE Paid_At END
                WHERE Student_Fee_ID = %s
                """,
                (status, amount_paid, request.form.get('payment_method') or None,
                 request.form.get('transaction_reference', '').strip() or None, status, student_fee_id)
            )
            log_audit(cursor, 'Updated fee status', 'Student_Fee', student_fee_id, status)
            conn.commit()
            return redirect(url_for('fee_management', success='Fee status updated.'))
        except Exception as e:
            conn.rollback()
            return redirect(url_for('fee_management', error=f'Could not update fee status: {e}'))
        finally:
            cursor.close()
            conn.close()
    return redirect(url_for('fee_management', error='Could not connect to the database.'))


@app.route('/maintenance_complaints')
def maintenance_complaints():
    if not session.get('loggedin') or session.get('role') != 'Official':
        return redirect(url_for('login'))

    complaints, officials = [], []
    conn = connect_db()
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT mc.*, s.Name AS Student_Name, s.Branch, u.Name AS Assigned_Name
            FROM Maintenance_Complaints mc
            JOIN Students s ON mc.Student_ID = s.Student_ID
            LEFT JOIN Users u ON mc.Assigned_To = u.User_ID
            ORDER BY FIELD(mc.Status, 'Open', 'In Progress', 'Resolved', 'Closed'),
                     FIELD(mc.Priority, 'Emergency', 'High', 'Medium', 'Low'), mc.Created_At DESC
            """
        )
        complaints = cursor.fetchall()
        cursor.execute("SELECT User_ID, Name FROM Users WHERE Role = 'Official' ORDER BY Name, User_ID")
        officials = cursor.fetchall()
        cursor.close()
        conn.close()
    return render_template('maintenance_inbox.html', portal='official', complaints=complaints,
                           officials=officials, success=request.args.get('success'), error=request.args.get('error'))


@app.route('/maintenance_complaints/<int:complaint_id>', methods=['POST'])
def update_maintenance_complaint(complaint_id):
    if not session.get('loggedin') or session.get('role') != 'Official':
        return redirect(url_for('login'))

    status = request.form.get('status')
    assigned_to = request.form.get('assigned_to') or None
    notes = request.form.get('resolution_notes', '').strip() or None
    if status not in ('Open', 'In Progress', 'Resolved', 'Closed'):
        return redirect(url_for('maintenance_complaints', error='Invalid complaint status.'))

    conn = connect_db()
    if conn:
        cursor = conn.cursor()
        try:
            if assigned_to:
                cursor.execute("SELECT 1 FROM Users WHERE User_ID = %s AND Role = 'Official'", (assigned_to,))
                if not cursor.fetchone():
                    return redirect(url_for('maintenance_complaints', error='Assigned staff member is invalid.'))
            cursor.execute(
                """
                UPDATE Maintenance_Complaints
                SET Status = %s, Assigned_To = %s, Resolution_Notes = %s,
                    Resolved_At = CASE WHEN %s IN ('Resolved', 'Closed') THEN COALESCE(Resolved_At, NOW()) ELSE Resolved_At END
                WHERE Complaint_ID = %s
                """, (status, assigned_to, notes, status, complaint_id)
            )
            if cursor.rowcount:
                log_audit(cursor, 'Updated maintenance complaint', 'Maintenance_Complaint', complaint_id, status)
            conn.commit()
            return redirect(url_for('maintenance_complaints', success='Complaint updated.'))
        except Exception as e:
            conn.rollback()
            return redirect(url_for('maintenance_complaints', error=f'Could not update complaint: {e}'))
        finally:
            cursor.close()
            conn.close()
    return redirect(url_for('maintenance_complaints', error='Could not connect to the database.'))
@app.route('/register-official', methods=['GET', 'POST'])
def register_official():
    error = None
    success = None

    if request.method == 'POST':
        user_id = request.form.get('user_id', '').strip()
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        registration_code = request.form.get('registration_code', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        official_code = os.environ.get('OFFICIAL_REGISTRATION_CODE', '')

        if not all([
            user_id,
            name,
            email,
            phone,
            registration_code,
            password,
            confirm_password
        ]):
            error = "Please fill in all fields."

        elif not official_code:
            error = "Official registration is currently unavailable."

        elif registration_code != official_code:
            error = "Invalid official registration code."

        elif password != confirm_password:
            error = "Passwords do not match."

        elif len(password) < 8:
            error = "Password must be at least 8 characters."

        else:
            conn = None
            cursor = None

            try:
                conn = connect_db()
                cursor = conn.cursor(dictionary=True)

                cursor.execute(
                    "SELECT User_ID FROM Users WHERE User_ID = %s",
                    (user_id,)
                )

                if cursor.fetchone():
                    error = "Staff ID already exists. Please use another Staff ID."

                else:
                    password_hash = generate_password_hash(password)

                    cursor.execute(
                        """
                        INSERT INTO Users
                        (User_ID, Password, Role, Name, Email, Phone)
                        VALUES (%s, %s, 'Official', %s, %s, %s)
                        """,
                        (
                            user_id,
                            password_hash,
                            name,
                            email,
                            phone
                        )
                    )

                    conn.commit()
                    success = "Official account created successfully. You can now sign in."

            except Exception:
                if conn:
                    conn.rollback()

                error = "Unable to create account. Please try again."

            finally:
                if cursor:
                    cursor.close()

                if conn:
                    conn.close()

    return render_template(
        'register_official_v2.html',
        error=error,
        success=success
    )


if __name__ == '__main__':
    app.run(debug=True, port=5001)
