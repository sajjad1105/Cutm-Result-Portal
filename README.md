# 🎓 CUTM Student Result Management System

Cutm-Result-Portal is a Python Flask app using MongoDB to manage CUTM student results. Admins add, update, and delete exam results and backlogs, while students securely view results and backlog status in real-time. Features include GPA calculation, backlog tracking, batch filtering, and data export for efficient record management.
---

## ✨ Key Features

### 🔍 Student Records Search
- Search by **Registration Number**
- **Semester-wise filtering**
- Real-time **SGPA** and **CGPA** calculation
- Complete academic history display

### 📊 GPA Calculation System
- **SGPA**: Semester-wise grade point calculation  
- **CGPA**: Cumulative GPA across all semesters  
- Automatic **credit-based computation**
- Grade mapping: `O=10`, `E=9`, `A=8`, `B=7`, `C=6`, `D=5`, `F=0`

### 🎯 Backlog Management
- Track failed subjects (`F`, `M`, `S`, `I`, `R` grades)
- Search by **Reg. No** or **Subject Code**
- **Branch-wise** and **Year-wise** backlog filtering
- Statistical charts and performance breakdowns

### 👥 Batch-Wise Data Management
- Filter by **Academic Year** (2020–2029)
- Filter by **Branch** (Civil, CSE, ECE, EEE, Mech)
- View complete records with analytics

### 📁 Data Export Options
- **CSV** for spreadsheet analysis
- **Excel** with formatted columns
- **PDF** with institutional branding

---

## 🛠️ Admin Panel

### 🔐 Authentication
- Secure **admin login**
- **Role-based access control**

### 📝 Result & Backlog Management
- Add, update, or delete student results
- **Bulk uploads** via CSV/Excel
- Grade, credit, and subject editing
- Real-time **SGPA/CGPA** recalculation

### 📂 Data Upload Center
- Drag & drop support for CSV/XLS/XLSX
- Built-in data validation with error reporting
- Batch processing for large datasets
- **Template download** for correct formatting

### 📊 Reports & Analytics
- Export student/backlog data to PDF/Excel
- Visual analytics: SGPA/CGPA trends
- Monitor performance by **branch** or **year**

---

## 🏠 Home Page – Student Portal

Simple and responsive student UI to check academic results.

### 🔎 Features:
- Enter **Registration Number** (e.g., `220101120012`)
- Select **Semester**
- Click **Search** to view results

### 📋 Displayed Info:
- Student details (Name, Reg. No, Semester)
- Subject-wise grades and credits
- **SGPA**, **CGPA**, Total/Cleared Credits
- Option to **Download PDF** of result

---

## 🔄 Backlog Assessment Search

Track and assess pending academic backlogs.

- Search by **Registration Number**
- Search by **Subject Code**
- Filter by **Branch** and **Batch**
- Visual insights into backlog distribution

---

## 📦 Tech Stack

### 🔧 Backend
- **Flask** (Python)
- **MongoDB** with PyMongo
- **Pandas** for data processing
- **Openpyxl** for Excel generation
- **ReportLab** for PDF generation

### 💻 Frontend
- **Bootstrap 5** UI framework
- **Jinja2** templating
- **Responsive** design with custom CSS

### 🔐 Security & Config
- Environment config with `python-dotenv`
- File uploads with `werkzeug`
- Timezone support with `pytz`

---

## 📋 Prerequisites

- Python 3.9+
- MongoDB 4.4+
- pip (Python package installer)

---
## 🚀 Installation & Setup  1. **Clone the Repository**  

git clone https://github.com/sajjad1105/Cutm-Result-Portal.git


cd cutm-result-management



### 🤝 Contribution Guidelines
We welcome contributions! 🚀

Fork this repository

Create a new feature branch

Commit with clear messages

Push to your fork

Open a Pull Request

🧑‍💻 Future Enhancements
👤 Student login portal

🧾 Automated transcript generation

📧 Email notification system

🌐 REST API for third-party integrations

🤖 AI-powered performance predictions

📜 License


Licensed under the MIT License – feel free to use, modify, and share.

👨‍🏫 Author


Developed by: [Md Sajjad Khan]


📧 Email: sajjadrockstar8294@gmail.com


🔗 GitHub: @sajjad1105

