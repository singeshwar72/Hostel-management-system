# 🏠 Hostel Management System

A comprehensive **Hostel Management System** designed to digitize and simplify hostel administration, student management, room allocation, fee management, maintenance complaints, support requests, notices, and emergency contact management.

The system provides separate functionality for **Students and Hostel Officials**, making hostel operations more organized, efficient, and accessible.

## ✨ Features

### 👨‍🎓 Student Management

* Student registration and login
* Student profile and biodata management
* Student dashboard
* Room request and allocation
* Emergency contact management
* Fee status and payment information
* Support ticket submission
* Maintenance complaint submission

### 🏢 Official Management

* Official registration and login
* Official dashboard
* Student management
* Room management and allocation
* Manual and bulk room allocation
* Fee structure management
* Payment verification
* Maintenance complaint management
* Support ticket management
* Notice and announcement management

### 🛏️ Room Management

* Hostel and room management
* Room capacity tracking
* Current occupancy monitoring
* Student room allocation
* Room requests
* Manual and bulk allocation

### 💰 Fee & Payment Management

* Fee structure management
* Student fee tracking
* Pending, partially paid, paid, overdue and waived status
* Payment request submission
* UTR/reference verification
* Payment approval and rejection

### 🔧 Maintenance & Support

* Maintenance complaint submission
* Complaint priority management
* Complaint status tracking
* Support ticket system
* Official response and resolution management

### 📢 Notices & Announcements

* Create notices and announcements
* Audience-based notices
* Notice categories
* Pinned notices
* Expiry date management

## 🛠️ Technology Stack

**Backend**

* Python
* Flask

**Frontend**

* HTML5
* CSS3
* JavaScript

**Database**

* MySQL

**Development Tools**

* Visual Studio Code
* Git & GitHub

## 📂 Project Structure

```text
Hostel-Management-System/
│
├── app.py
├── student.py
├── data.sql
├── .gitignore
│
├── static/
│   ├── css/
│   ├── js/
│   └── uploads/
│
└── templates/
    ├── login.html
    ├── register.html
    ├── student_dashboard.html
    ├── official_dashboard.html
    ├── allocate.html
    ├── fee_management.html
    ├── maintenance_request.html
    ├── notices.html
    └── ...
```

## ⚙️ Installation

### 1. Clone the Repository

```bash
git clone https://github.com/singeshwar72/Hostel-management-system.git
cd Hostel-management-system
```

### 2. Create a Virtual Environment

```bash
python -m venv venv
```

### 3. Activate the Virtual Environment

**Windows:**

```bash
venv\Scripts\activate
```

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

> If a `requirements.txt` file is not included, install the required Flask/MySQL packages according to the project configuration.

### 5. Configure the Database

Create the MySQL database and execute the SQL commands provided in:

```text
data.sql
```

Update the database connection configuration according to your local MySQL credentials.

### 6. Run the Application

```bash
python app.py
```

Open the application in your browser using the local Flask server address shown in the terminal.

## 🔐 Security

The project is designed with role-based functionality for **Students and Officials** and includes controlled access to hostel management operations.

For production deployment, additional security measures such as environment variables, password hashing, CSRF protection, secure session management, and input validation should be implemented or strengthened.

## 🚀 Future Improvements

* Online payment gateway integration
* Advanced authentication and authorization
* Email/SMS notifications
* Hostel analytics dashboard
* Automated room allocation
* Mobile application
* Advanced reporting and data visualization
* Cloud deployment

## 🎯 Project Objective

The main objective of this project is to provide a centralized digital platform for managing hostel operations while reducing manual work and improving communication between students and hostel officials.

## 👨‍💻 Author

**Singeshwar**

GitHub: [@singeshwar72](https://github.com/singeshwar72)

---

⭐ If you find this project useful, consider giving the repository a star!
