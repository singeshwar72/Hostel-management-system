CREATE DATABASE IF NOT EXISTS HostelManagement;
USE HostelManagement;

CREATE TABLE IF NOT EXISTS Users (
    User_ID VARCHAR(50) PRIMARY KEY,
    Password VARCHAR(500) NOT NULL,
    Role ENUM('Official', 'Student') NOT NULL,
    Name VARCHAR(100),
    Email VARCHAR(100),
    Phone VARCHAR(20),
    Profile_Pic VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS Students (
    Student_ID VARCHAR(50) PRIMARY KEY,
    Name VARCHAR(100) NOT NULL,
    Phone VARCHAR(20) NOT NULL,
    Branch VARCHAR(50) NOT NULL,
    Year INT NOT NULL,
    Gender VARCHAR(20) NOT NULL,
    Address TEXT,
    Allocation_Eligible BOOLEAN NOT NULL DEFAULT TRUE,
    Room_Request_Visible BOOLEAN NOT NULL DEFAULT FALSE,
    FOREIGN KEY (Student_ID) REFERENCES Users(User_ID) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS Rooms (
    Room_No VARCHAR(20) NOT NULL,
    Hostel_No VARCHAR(50) NOT NULL,
    Capacity INT NOT NULL,
    Current_Occupancy INT DEFAULT 0,
    PRIMARY KEY (Room_No, Hostel_No)
);

CREATE TABLE IF NOT EXISTS Allocations (
    Allocation_ID INT AUTO_INCREMENT PRIMARY KEY,
    Student_ID VARCHAR(50) NOT NULL,
    Room_No VARCHAR(20) NOT NULL,
    Hostel_No VARCHAR(50) NOT NULL,
    Move_In_Date DATE NOT NULL,
    Status VARCHAR(20) DEFAULT 'Active',
    UNIQUE KEY uq_allocations_student (Student_ID),
    FOREIGN KEY (Student_ID) REFERENCES Students(Student_ID) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS Room_Requests (
    Request_ID INT AUTO_INCREMENT PRIMARY KEY,
    Student_ID VARCHAR(50) NOT NULL,
    Preferred_Hostel VARCHAR(50) NOT NULL,
    Preferred_Room_Type INT NOT NULL,
    Reason TEXT NOT NULL,
    Status VARCHAR(20) DEFAULT 'Pending',
    FOREIGN KEY (Student_ID) REFERENCES Students(Student_ID) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS Support_Tickets (
    Ticket_ID INT AUTO_INCREMENT PRIMARY KEY,
    Student_ID VARCHAR(50) NOT NULL,
    Subject VARCHAR(150) NOT NULL,
    Message TEXT NOT NULL,
    Status VARCHAR(20) DEFAULT 'Open',
    Created_At TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (Student_ID) REFERENCES Students(Student_ID) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS Emergency_Contacts (
    Emergency_Contact_ID INT AUTO_INCREMENT PRIMARY KEY,
    Student_ID VARCHAR(50) NOT NULL,
    Contact_Name VARCHAR(100) NOT NULL,
    Relationship VARCHAR(50) NOT NULL,
    Phone VARCHAR(20) NOT NULL,
    Alternate_Phone VARCHAR(20),
    Email VARCHAR(100),
    Address TEXT,
    Is_Primary BOOLEAN NOT NULL DEFAULT FALSE,
    Created_At TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (Student_ID) REFERENCES Students(Student_ID) ON DELETE CASCADE,
    INDEX idx_emergency_contacts_student (Student_ID)
);
CREATE TABLE IF NOT EXISTS Fee_Structures (
    Fee_Structure_ID INT AUTO_INCREMENT PRIMARY KEY,
    Fee_Type VARCHAR(100) NOT NULL,
    Amount DECIMAL(10, 2) NOT NULL,
    Academic_Year VARCHAR(20) NOT NULL,
    Start_Date DATE,
    End_Date DATE,
    Description TEXT,
    Is_Active BOOLEAN NOT NULL DEFAULT TRUE,
    Created_At TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_fee_structures_year (Academic_Year)
);
CREATE TABLE IF NOT EXISTS Student_Fees (
    Student_Fee_ID INT AUTO_INCREMENT PRIMARY KEY,
    Student_ID VARCHAR(50) NOT NULL,
    Fee_Structure_ID INT,
    Fee_Type VARCHAR(100) NOT NULL,
    Amount_Due DECIMAL(10, 2) NOT NULL,
    Amount_Paid DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    Start_Date DATE,
    End_Date DATE,
    Status ENUM('Pending', 'Partially Paid', 'Paid', 'Overdue', 'Waived') NOT NULL DEFAULT 'Pending',
    Payment_Method VARCHAR(50),
    Transaction_Reference VARCHAR(100),
    Paid_At DATETIME,
    Remarks TEXT,
    Created_At TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    Updated_At TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (Student_ID) REFERENCES Students(Student_ID) ON DELETE CASCADE,
    FOREIGN KEY (Fee_Structure_ID) REFERENCES Fee_Structures(Fee_Structure_ID) ON DELETE SET NULL,
    INDEX idx_student_fees_student_status (Student_ID, Status),
    INDEX idx_student_fees_end_date (End_Date)
);

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
);

CREATE TABLE IF NOT EXISTS Notices (
    Notice_ID INT AUTO_INCREMENT PRIMARY KEY,
    Title VARCHAR(200) NOT NULL,
    Message TEXT NOT NULL,
    Notice_Type ENUM('Notice', 'Announcement') NOT NULL DEFAULT 'Notice',
    Category VARCHAR(50) NOT NULL DEFAULT 'General',
    Audience ENUM('All', 'Students', 'Officials') NOT NULL DEFAULT 'All',
    Published_By VARCHAR(50),
    Published_At TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    Expires_At DATETIME,
    Is_Pinned BOOLEAN NOT NULL DEFAULT FALSE,
    FOREIGN KEY (Published_By) REFERENCES Users(User_ID) ON DELETE SET NULL,
    INDEX idx_notices_audience_published (Audience, Published_At),
    INDEX idx_notices_expiry (Expires_At)
);
CREATE TABLE IF NOT EXISTS Maintenance_Complaints (
    Complaint_ID INT AUTO_INCREMENT PRIMARY KEY,
    Student_ID VARCHAR(50) NOT NULL,
    Room_No VARCHAR(20),
    Hostel_No VARCHAR(50),
    Category VARCHAR(50) NOT NULL,
    Description TEXT NOT NULL,
    Priority ENUM('Low', 'Medium', 'High', 'Emergency') NOT NULL DEFAULT 'Medium',
    Status ENUM('Open', 'In Progress', 'Resolved', 'Closed') NOT NULL DEFAULT 'Open',
    Assigned_To VARCHAR(50),
    Resolution_Notes TEXT,
    Created_At TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    Updated_At TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    Resolved_At DATETIME,
    FOREIGN KEY (Student_ID) REFERENCES Students(Student_ID) ON DELETE CASCADE,
    FOREIGN KEY (Room_No, Hostel_No) REFERENCES Rooms(Room_No, Hostel_No) ON DELETE SET NULL,
    FOREIGN KEY (Assigned_To) REFERENCES Users(User_ID) ON DELETE SET NULL,
    INDEX idx_maintenance_status_priority (Status, Priority),
    INDEX idx_maintenance_student (Student_ID)
);
