from flask import Flask, render_template, request, redirect, json, make_response, jsonify
import os
from dotenv import load_dotenv
from pymongo import MongoClient
from datetime import datetime
import pytz
import pandas as pd
from werkzeug.utils import secure_filename
import io
import csv
from io import StringIO, BytesIO
from bson import ObjectId

load_dotenv()

app = Flask(__name__)

ADMIN_USERNAME = os.getenv('ADMIN_USERNAME')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')
MONGO_URI = os.getenv('MONGO_URI')

client = MongoClient(MONGO_URI, w=1, retryWrites=True, socketTimeoutMS=20000)
db = client.get_database("cutm1")
cutm_collection = db.get_collection("CUTM1")
cbcs_collection = db.get_collection("cbcs")

# ---------------- Indexes ----------------
def ensure_indexes():
    try:
        cutm_collection.create_index([("Reg_No", 1)])
        cutm_collection.create_index([("Sem", 1)])
        cutm_collection.create_index([("Reg_No", 1), ("Sem", 1)])
        cutm_collection.create_index([("Name", 1)])
        cutm_collection.create_index([("Subject_Code", 1)])
        
        cbcs_collection.create_index([("Subject_Code", 1)])
        cbcs_collection.create_index([("Branch", 1)])
        cbcs_collection.create_index([("Basket", 1)])
        cbcs_collection.create_index([("Subject_Code", 1), ("Branch", 1)])
    except Exception:
        pass

ensure_indexes()

# ---------------- Branch Identification ----------------
def get_branch_from_reg_no(reg_no):
    """Extract branch name from registration number"""
    branch_codes = {
        '1': 'Civil Engineering',
        '2': 'Computer Science Engineering', 
        '3': 'Electronics & Communication Engineering',
        '5': 'Electrical & Electronics Engineering',
        '6': 'Mechanical Engineering'
    }
    
    if len(str(reg_no)) >= 10:
        branch_code = str(reg_no)[7:8]
        return branch_codes.get(branch_code, 'Unknown Branch')
    return 'Invalid Registration'

def get_year_from_reg_no(reg_no):
    """Extract admission year from registration number"""
    year_codes = {
        '20': '2020', '21': '2021', '22': '2022', '23': '2023', '24': '2024',
        '25': '2025', '26': '2026', '27': '2027', '28': '2028', '29': '2029'
    }
    
    if len(str(reg_no)) >= 2:
        year_code = str(reg_no)[:2]
        return year_codes.get(year_code, f'20{year_code}')
    return 'Unknown'

def get_branch_code_mapping():
    """Get branch name to code mapping for search"""
    return {
         'Civil': '1', 'CSE': '2', 'ECE': '3', 'EEE': '5', 'Mechanical': '6'
    }

def get_year_code_mapping():
    """Get year to code mapping for search"""
    return {
         '20': '2020', '21': '2021', '22': '2022', '23': '2023', '24': '2024',
        '25': '2025', '26': '2026', '27': '2027', '28': '2028', '29': '2029'
    }

# ---------------- Utilities ----------------
def convert_to_ist(gmt_time):
    ist_timezone = pytz.timezone('Asia/Kolkata')
    gmt_time = gmt_time.replace(tzinfo=pytz.utc)
    return gmt_time.astimezone(ist_timezone).strftime('%Y-%m-%d %I:%M:%S %p IST')

GRADE_MAP = {'O': 10, 'E': 9, 'A': 8, 'B': 7, 'C': 6, 'D': 5, 'S': 0, 'M': 0, 'F': 0, "I": 0, "R": 0}

def convert_grade_to_integer(grade):
    return GRADE_MAP.get(grade, 0)

def calculate_sgpa(result):
    total_credits, total_weighted_grades = 0, 0
    for row in result:
        credits_str = row.get("Credits") or ""
        parts = [p for p in str(credits_str).split('+') if p.strip() != ""]
        if not parts:
            continue
        credits_parts = [float(part) for part in parts]
        g = row.get("Grade")
        grade = convert_grade_to_integer(g) if isinstance(g, str) and g in "OEABCDSMF" else float(g)
        csum = sum(credits_parts)
        total_credits += csum
        total_weighted_grades += grade * csum
    sgpa = total_weighted_grades / total_credits if total_credits else 0
    return sgpa, total_credits

def calculate_cgpa(registration, name):
    cursor = cutm_collection.find(
        {"$or": [{"Reg_No": registration}, {"Name": {"$regex": f"^{name}$", "$options": "i"}}]},
        {"Credits": 1, "Grade": 1, "_id": 0}
    )
    total_credits, total_weighted_grades = 0, 0
    for row in cursor:
        credits_str = row.get("Credits") or ""
        parts = [p for p in str(credits_str).split('+') if p.strip() != ""]
        if not parts:
            continue
        credits_parts = [float(part) for part in parts]
        g = row.get("Grade")
        grade = convert_grade_to_integer(g) if isinstance(g, str) and g in "OEABCDSMF" else float(g)
        csum = sum(credits_parts)
        total_credits += csum
        total_weighted_grades += grade * csum
    cgpa = total_weighted_grades / total_credits if total_credits else 0
    return cgpa

# ---------------- Basket Credit Requirements ----------------
BASKET_CREDIT_REQUIREMENTS = {
    'Basket I': 17,
    'Basket II': 12,
    'Basket III': 25,
    'Basket IV': 58,
    'Basket V': 48,
    'Basket 1': 17,    # Alternative naming
    'Basket 2': 12,
    'Basket 3': 25,
    'Basket 4': 58,
    'Basket 5': 48
}

# Helper function to normalize credits and handle different formats
def parse_credits_normalized(credit_str):
    """Parse credit string like '2+0+1' or '2--0--1' into total numeric value"""
    if not credit_str or not isinstance(credit_str, str):
        return 0.0
    try:
        # Replace -- with + for consistency
        credit_str = credit_str.replace('--', '+')
        if '+' in credit_str:
            parts = credit_str.split('+')
            total = sum(float(p.strip()) for p in parts if p.strip())
            return total
        else:
            return float(credit_str)
    except Exception:
        return 0.0

def parse_credits(credit_str):
    """Parse credit string like '2+0+1' into total numeric value"""
    if not credit_str or not isinstance(credit_str, str):
        return 0.0
    try:
        if '+' in credit_str:
            parts = credit_str.split('+')
            total = sum(float(p.strip()) for p in parts if p.strip())
            return total
        else:
            return float(credit_str)
    except Exception:
        return 0.0

# ---------------- Home Route ----------------
@app.route('/', methods=['GET', 'POST'])
def home():
    try:
        semesters = sorted({doc["Sem"] for doc in cutm_collection.find({}, {"Sem": 1, "_id": 0})})
        
        results, count, message = [], 0, None
        semester_results = {}
        overall_cgpa = None
        total_all_semester_credits = 0

        if request.method == 'POST':
            name = (request.form.get('name') or "").strip()
            registration = (request.form.get('registration') or "").strip().upper()
            selected_semesters = request.form.getlist('semester')
            
            flat_semesters = []
            for sem in selected_semesters:
                if isinstance(sem, list):
                    flat_semesters.extend(sem)
                else:
                    flat_semesters.append(str(sem))
            selected_semesters = flat_semesters

            if not registration and not name:
                return render_template('index.html', semesters=semesters, error="Please enter registration or name.")
            
            if not selected_semesters:
                return render_template('index.html', semesters=semesters, error="Please select at least one semester.")

            total_count = 0
            for semester in selected_semesters:
                semester = str(semester).strip()
                
                query = {
                    "$and": [
                        {"$or": [
                            {"Reg_No": registration}, 
                            {"Name": {"$regex": f"^{name}$", "$options": "i"}}
                        ]}, 
                        {"Sem": semester}
                    ]
                }
                projection = {
                    "_id": 0, "Credits": 1, "Grade": 1, "Subject_Name": 1, 
                    "Subject_Code": 1, "Sem": 1, "Name": 1, "Reg_No": 1
                }
                
                semester_data = list(cutm_collection.find(query, projection))
                
                if semester_data:
                    sgpa, total_credits = calculate_sgpa(semester_data)
                    
                    semester_results[semester] = {
                        'data': semester_data,
                        'count': len(semester_data),
                        'sgpa': sgpa,
                        'total_credits': total_credits
                    }
                    
                    results.extend(semester_data)
                    total_count += len(semester_data)

            count = total_count

            if registration:
                all_credits = cutm_collection.find({"Reg_No": registration}, {"Credits": 1, "_id": 0})
                for row in all_credits:
                    credits_str = row.get("Credits") or ""
                    parts = [p for p in str(credits_str).split('+') if p.strip() != ""]
                    if not parts:
                        continue
                    try:
                        total_all_semester_credits += sum(float(part) for part in parts)
                    except ValueError:
                        continue

                overall_cgpa = calculate_cgpa(registration, name)

            if count == 0:
                message = "No records found for the selected criteria."

            current_date = datetime.now().strftime('%d-%b-%Y')

            if len(selected_semesters) == 1:
                semester = str(selected_semesters[0])
                
                if semester in semester_results:
                    sem_data = semester_results[semester]
                    return render_template(
                        'display.html',
                        result=sem_data['data'],
                        count=sem_data['count'],
                        sgpa=sem_data['sgpa'],
                        total_credits=sem_data['total_credits'],
                        cgpa=overall_cgpa,
                        total_all_semester_credits=total_all_semester_credits,
                        message=message,
                        selected_semester=semester,
                        semesters=semesters,
                        current_date=current_date
                    )
                else:
                    return render_template('index.html', semesters=semesters, 
                                         error=f"No data found for {semester}")
            else:
                semesters_display = ", ".join(selected_semesters)
                return render_template(
                    'display_multi.html',
                    result=results,
                    semester_results=semester_results,
                    selected_semesters=selected_semesters,
                    count=count,
                    cgpa=overall_cgpa,
                    total_all_semester_credits=total_all_semester_credits,
                    message=message,
                    semesters=semesters,
                    registration=registration,
                    name=name,
                    semesters_display=semesters_display,
                    current_date=current_date
                )

        return render_template('index.html', semesters=semesters)
        
    except Exception as e:
        print(f"ERROR in home route: {str(e)}")
        return render_template('index.html', semesters=semesters, error=str(e))

# ---------------- Get Semesters ----------------
@app.route('/semesters', methods=['POST'])
def get_semesters_for_student():
    try:
        registration = (request.form.get('registration') or "").strip().upper()
        if not registration:
            return jsonify(semesters=[])
        semesters = sorted({doc["Sem"] for doc in cutm_collection.find({"Reg_No": registration}, {"Sem": 1, "_id": 0})})
        return jsonify(semesters=semesters)
    except Exception as e:
        return jsonify(error=str(e))

# ---------------- Update Data ----------------
ALLOWED_EXTENSIONS = {'csv', 'xls', 'xlsx'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/update_data', methods=['GET', 'POST'])
def update_data():
    if request.method == 'POST':
        if 'files' not in request.files:
            return render_template('update_data.html', error="No file part")

        files = request.files.getlist('files')
        if not files or all(f.filename == '' for f in files):
            return render_template('update_data.html', error="No selected files")

        updated_count = 0
        inserted_count = 0

        for file in files:
            if not (file and allowed_file(file.filename)):
                continue

            filename = secure_filename(file.filename)
            file_data = file.read()
            if filename.lower().endswith('.csv'):
                df = pd.read_csv(io.BytesIO(file_data))
            else:
                df = pd.read_excel(io.BytesIO(file_data))

            cols = {c.lower().strip(): c for c in df.columns}
            def col(*names):
                for n in names:
                    if n.lower() in cols:
                        return cols[n.lower()]
                return None

            col_reg = col('Reg_No', 'Registration No.')
            col_code = col('Subject_Code', 'Subject Code')
            col_sname = col('Subject_Name', 'Subject Name')
            col_name = col('Name')
            col_sem = col('Sem')
            col_credits = col('Credits', 'Credit')
            col_grade = col('Grade', 'Grade Point')
            col_stype = col('Subject_Type', 'Subject Type')

            for _, row in df.iterrows():
                reg_no = str(row.get(col_reg) or "").strip().upper() if col_reg else ""
                subject_code = str(row.get(col_code) or "").strip().upper() if col_code else ""
                if not reg_no or not subject_code:
                    continue

                subject_name = str(row.get(col_sname) or "").strip() if col_sname else ""
                name = str(row.get(col_name) or "").strip() if col_name else ""
                sem = str(row.get(col_sem) or "").strip() if col_sem else ""
                credits = str(row.get(col_credits) or "").strip() if col_credits else ""
                grade = str(row.get(col_grade) or "").strip().upper() if col_grade else ""
                subject_type = str(row.get(col_stype) or "").strip() if col_stype else ""
                sem_value = f"Sem {sem}" if sem.isdigit() else sem

                existing_record = cutm_collection.find_one(
                    {"Reg_No": reg_no, "Subject_Code": subject_code},
                    {"Grade": 1}
                )

                if existing_record:
                    if existing_record.get("Grade") in {'F', 'S', 'M', 'I', 'R', ''}:
                        cutm_collection.update_one(
                            {"Reg_No": reg_no, "Subject_Code": subject_code},
                            {"$set": {"Grade": grade}}
                        )
                        updated_count += 1
                else:
                    cutm_collection.insert_one({
                        "Reg_No": reg_no,
                        "Subject_Code": subject_code,
                        "Grade": grade,
                        "Name": name,
                        "Sem": sem_value,
                        "Subject_Name": subject_name,
                        "Subject_Type": subject_type,
                        "Credits": credits
                    })
                    inserted_count += 1

        message = f"All files processed successfully! Updated: {updated_count}, Inserted: {inserted_count}"
        return render_template('update_data.html', success=message)

    return render_template('update_data.html')

# ---------------- Backlog ----------------
@app.route('/backlog', methods=['GET', 'POST'])
def backlog():
    try:
        result, count, message, search_type = [], 0, None, None
        branch_stats = {}
        year_stats = {}
        search_criteria = []
        
        if request.method == 'POST':
            reg_no = (request.form.get('registration') or "").strip().upper()
            subject_code = (request.form.get('subject_code') or "").strip().upper()
            branch_filter = (request.form.get('branch') or "").strip()
            year_filter = (request.form.get('year') or "").strip()

            base_query = {"Grade": {"$in": ["F", "M", "S", "I", "R"]}}
            reg_conditions = []
            
            def get_branch_code_from_input(branch_input):
                branch_mapping = {
                    'civil': '1', 'civil engineering': '1',
                    'cse': '2', 'computer science': '2', 'computer science engineering': '2',
                    'ece': '3', 'electronics': '3', 'electronics & communication': '3', 'electronics & communication engineering': '3',
                    'eee': '5', 'electrical': '5', 'electrical & electronics': '5', 'electrical & electronics engineering': '5',
                    'mechanical': '6', 'mechanical engineering': '6'
                }
                
                branch_lower = branch_input.lower().strip()
                return branch_mapping.get(branch_lower)
            
            if reg_no:
                search_type = 'registration'
                base_query["Reg_No"] = reg_no
                search_criteria.append(f"Registration: {reg_no}")
                
            elif subject_code:
                search_type = 'subject_code'
                base_query["Subject_Code"] = subject_code
                search_criteria.append(f"Subject Code: {subject_code}")
                
                if branch_filter:
                    branch_code = get_branch_code_from_input(branch_filter)
                    
                    if branch_code:
                        search_criteria.append(f"Branch: {branch_filter}")
                        reg_conditions.append({"Reg_No": {"$regex": f"^.{{{7}}}{branch_code}"}})
                    else:
                        message = f"Invalid branch selection: {branch_filter}. Valid options: Civil, CSE, ECE, EEE, Mechanical"
                
                if year_filter and not message:
                    year_short = year_filter
                    
                    if len(year_filter) == 4 and year_filter.isdigit():
                        year_short = year_filter[-2:]
                    elif len(year_filter) == 2 and year_filter.isdigit():
                        year_short = year_filter
                    else:
                        message = f"Invalid year format: {year_filter}. Use format: 21, 22, 2021, 2022, etc."
                    
                    if not message:
                        search_criteria.append(f"Year: {year_filter}")
                        reg_conditions.append({"Reg_No": {"$regex": f"^{year_short}"}})
                
                if reg_conditions and not message:
                    if len(reg_conditions) == 1:
                        base_query.update(reg_conditions[0])
                    else:
                        base_query["$and"] = reg_conditions
                        
            elif branch_filter or year_filter:
                search_type = 'advanced'
                
                if branch_filter:
                    branch_code = get_branch_code_from_input(branch_filter)
                    
                    if branch_code:
                        search_criteria.append(f"Branch: {branch_filter}")
                        reg_conditions.append({"Reg_No": {"$regex": f"^.{{{7}}}{branch_code}"}})
                    else:
                        message = f"Invalid branch selection: {branch_filter}. Valid options: Civil, CSE, ECE, EEE, Mechanical"
                
                if year_filter and not message:
                    year_short = year_filter
                    
                    if len(year_filter) == 4 and year_filter.isdigit():
                        year_short = year_filter[-2:]
                    elif len(year_filter) == 2 and year_filter.isdigit():
                        year_short = year_filter
                    else:
                        message = f"Invalid year format: {year_filter}. Use format: 21, 22, 2021, 2022, etc."
                    
                    if not message:
                        search_criteria.append(f"Year: {year_filter}")
                        reg_conditions.append({"Reg_No": {"$regex": f"^{year_short}"}})
                
                if reg_conditions and not message:
                    if len(reg_conditions) == 1:
                        base_query.update(reg_conditions[0])
                    else:
                        base_query["$and"] = reg_conditions

            if not message and (reg_no or subject_code or branch_filter or year_filter):
                cursor = cutm_collection.find(
                    base_query,
                    {"_id": 0, "Reg_No": 1, "Subject_Code": 1, "Subject_Name": 1, 
                     "Grade": 1, "Sem": 1, "Name": 1}
                )
                result = list(cursor)
                count = len(result)
                
                for row in result:
                    row['Branch'] = get_branch_from_reg_no(row.get('Reg_No', ''))
                    row['Year'] = get_year_from_reg_no(row.get('Reg_No', ''))
                    if row['Branch'] != 'Unknown Branch':
                        row['Branch_Short'] = row['Branch'].split()[0]
                    else:
                        row['Branch_Short'] = 'Unknown'
                
                for row in result:
                    branch = row.get('Branch_Short', 'Unknown')
                    year = row.get('Year', 'Unknown')
                    branch_stats[branch] = branch_stats.get(branch, 0) + 1
                    year_stats[year] = year_stats.get(year, 0) + 1
                
                if count == 0:
                    if search_type == 'registration':
                        message = f"No backlog found for registration number {reg_no}."
                    elif search_type == 'subject_code':
                        criteria_text = ", ".join(search_criteria)
                        message = f"No students found with backlog for: {criteria_text}."
                    elif search_type == 'advanced':
                        criteria_text = ", ".join(search_criteria)
                        message = f"No backlog found for criteria: {criteria_text}."
            elif not (reg_no or subject_code or branch_filter or year_filter):
                message = "Please enter a registration number, subject code, or select branch/year to search."

        return render_template('backlog.html', 
                             result=result, 
                             count=count, 
                             message=message, 
                             search_type=search_type,
                             branch_stats=branch_stats,
                             year_stats=year_stats,
                             search_criteria=search_criteria)
    except Exception as e:
        return render_template('backlog.html', error=str(e))

# ---------------- Batch Route ----------------
@app.route('/batch', methods=['GET', 'POST'])
def batch():
    try:
        result, count, message = [], 0, None
        branch_stats = {}
        batch_stats = {}
        search_criteria = []
        
        if request.method == 'POST':
            branch_filter = (request.form.get('branch') or "").strip()
            batch_filter = (request.form.get('batch') or "").strip()
            
            base_query = {}
            reg_conditions = []
            
            def get_branch_code_from_input(branch_input):
                branch_mapping = {
                    'civil': '1', 'civil engineering': '1',
                    'cse': '2', 'computer science': '2', 'computer science engineering': '2',
                    'ece': '3', 'electronics': '3', 'electronics & communication': '3', 'electronics & communication engineering': '3',
                    'eee': '5', 'electrical': '5', 'electrical & electronics': '5', 'electrical & electronics engineering': '5',
                    'mechanical': '6', 'mechanical engineering': '6'
                }
                
                branch_lower = branch_input.lower().strip()
                return branch_mapping.get(branch_lower)
            
            if branch_filter:
                branch_code = get_branch_code_from_input(branch_filter)
                
                if branch_code:
                    search_criteria.append(f"Branch: {branch_filter}")
                    reg_conditions.append({"Reg_No": {"$regex": f"^.{{{7}}}{branch_code}"}})
                else:
                    message = f"Invalid branch selection: {branch_filter}. Valid options: Civil, CSE, ECE, EEE, Mechanical"
            
            if batch_filter and not message:
                batch_short = batch_filter
                
                if len(batch_filter) == 4 and batch_filter.isdigit():
                    batch_short = batch_filter[-2:]
                elif len(batch_filter) == 2 and batch_filter.isdigit():
                    batch_short = batch_filter
                else:
                    message = f"Invalid batch format: {batch_filter}. Use format: 21, 22, 2021, 2022, etc."
                
                if not message:
                    search_criteria.append(f"Batch: {batch_filter}")
                    reg_conditions.append({"Reg_No": {"$regex": f"^{batch_short}"}})
            
            if reg_conditions and not message:
                if len(reg_conditions) == 1:
                    base_query.update(reg_conditions[0])
                else:
                    base_query["$and"] = reg_conditions
            
            if not message and (branch_filter or batch_filter):
                if base_query:
                    cursor = cutm_collection.find(
                        base_query,
                        {"_id": 0, "Reg_No": 1, "Name": 1, "Sem": 1, 
                         "Subject_Code": 1, "Subject_Name": 1, "Credits": 1, "Grade": 1}
                    ).sort([("Reg_No", 1), ("Sem", 1), ("Subject_Code", 1)])
                    
                    result = list(cursor)
                    count = len(result)
                    
                    unique_students = set()
                    for row in result:
                        reg_no = row.get('Reg_No', '')
                        row['Branch'] = get_branch_from_reg_no(reg_no)
                        row['Batch'] = get_year_from_reg_no(reg_no)
                        
                        if row['Branch'] != 'Unknown Branch':
                            row['Branch_Short'] = row['Branch'].split()[0]
                        else:
                            row['Branch_Short'] = 'Unknown'
                        
                        unique_students.add(reg_no)
                    
                    for row in result:
                        branch = row.get('Branch_Short', 'Unknown')
                        batch = row.get('Batch', 'Unknown')
                        branch_stats[branch] = branch_stats.get(branch, 0) + 1
                        batch_stats[batch] = batch_stats.get(batch, 0) + 1
                    
                    student_count = len(unique_students)
                    
                    if count == 0:
                        criteria_text = ", ".join(search_criteria)
                        message = f"No records found for criteria: {criteria_text}."
                    else:
                        success_criteria = ", ".join(search_criteria)
                        message = f"Found {count} records for {student_count} students matching: {success_criteria}."
                else:
                    message = "Please select at least one filter (branch or batch)."
            elif not message:
                message = "Please select branch and/or batch to view data."
        
        return render_template('batch.html', 
                             result=result, 
                             count=count, 
                             message=message,
                             branch_stats=branch_stats,
                             batch_stats=batch_stats,
                             search_criteria=search_criteria)
                             
    except Exception as e:
        return render_template('batch.html', error=str(e))

# ---------------- Admin Routes ----------------
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username') or ""
        password = request.form.get('password') or ""
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            return redirect('/admin/panel')
        else:
            return render_template('admin_login.html', error="Invalid username or password")
    return render_template('admin_login.html')

@app.route('/admin/panel')
def admin_panel():
    return render_template('admin_panel.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/data')
def data():
    return render_template('data.html')

# ---------------- View Data ----------------
@app.route('/view_data', methods=['GET', 'POST'])
def view_data():
    try:
        rows = []
        registration = ""
        message = ""
        error = ""
        total_credits = 0
        
        if request.method == 'POST':
            if 'search_registration' in request.form:
                registration = (request.form.get('search_registration') or "").strip().upper()
                
                if not registration:
                    error = "Please enter a registration number."
                else:
                    cursor = cutm_collection.find(
                        {"Reg_No": registration},
                        {"Reg_No": 1, "Name": 1, "Sem": 1, "Subject_Code": 1, 
                         "Subject_Name": 1, "Credits": 1, "Grade": 1, "_id": 0}
                    ).sort([("Sem", 1), ("Subject_Code", 1)])
                    
                    student_data = list(cursor)
                    
                    if not student_data:
                        error = f"No records found for registration number: {registration}"
                    else:
                        rows = [(record.get('Reg_No', ''), 
                                record.get('Name', ''),
                                record.get('Sem', ''),
                                record.get('Subject_Code', ''),
                                record.get('Subject_Name', ''),
                                record.get('Credits', ''),
                                record.get('Grade', '')) for record in student_data]
                        
                        for record in student_data:
                            credits_str = record.get("Credits") or ""
                            parts = [p for p in str(credits_str).split('+') if p.strip() != ""]
                            if parts:
                                try:
                                    total_credits += sum(float(part) for part in parts)
                                except ValueError:
                                    continue
                        
            elif 'reg_no' in request.form and 'subject_code' in request.form:
                reg_no = (request.form.get('reg_no') or "").strip().upper()
                subject_code = (request.form.get('subject_code') or "").strip().upper()
                new_grade = (request.form.get('new_grade') or "").strip().upper()
                
                if not all([reg_no, subject_code, new_grade]):
                    error = "All fields are required for update."
                elif new_grade not in ['O', 'E', 'A', 'B', 'C', 'D', 'F', 'M', 'S', 'I', 'R']:
                    error = "Invalid grade. Please use: O, E, A, B, C, D, F, M, S, I, R"
                else:
                    result = cutm_collection.update_one(
                        {"Reg_No": reg_no, "Subject_Code": subject_code},
                        {"$set": {"Grade": new_grade}}
                    )
                    
                    if result.modified_count > 0:
                        message = f"Grade updated successfully for {subject_code}!"
                        registration = reg_no
                        
                        cursor = cutm_collection.find(
                            {"Reg_No": registration},
                            {"Reg_No": 1, "Name": 1, "Sem": 1, "Subject_Code": 1, 
                             "Subject_Name": 1, "Credits": 1, "Grade": 1, "_id": 0}
                        ).sort([("Sem", 1), ("Subject_Code", 1)])
                        
                        student_data = list(cursor)
                        rows = [(record.get('Reg_No', ''), 
                                record.get('Name', ''),
                                record.get('Sem', ''),
                                record.get('Subject_Code', ''),
                                record.get('Subject_Name', ''),
                                record.get('Credits', ''),
                                record.get('Grade', '')) for record in student_data]
                        
                        for record in student_data:
                            credits_str = record.get("Credits") or ""
                            parts = [p for p in str(credits_str).split('+') if p.strip() != ""]
                            if parts:
                                try:
                                    total_credits += sum(float(part) for part in parts)
                                except ValueError:
                                    continue
                    else:
                        error = "No record found to update or grade was already the same."
        
        return render_template('view_data.html', 
                             rows=rows, 
                             registration=registration,
                             message=message,
                             error=error,
                             total_credits=total_credits)
                             
    except Exception as e:
        return render_template('view_data.html', error=str(e))

# ---------------- CBCS/Basket Management ----------------

@app.route('/basket')
def basket():
    """Display all CBCS subjects with search and filter options"""
    try:
        branch = request.args.get('branch', '')
        basket = request.args.get('basket', '')
        search = request.args.get('search', '')
        
        query = {}
        if branch and branch != 'All':
            query['Branch'] = branch
        if basket:
            query['Basket'] = basket
        if search:
            query['$or'] = [
                {'Subject_name': {'$regex': search, '$options': 'i'}},
                {'Subject Code': {'$regex': search, '$options': 'i'}}
            ]
        
        page = int(request.args.get('page', 1))
        per_page = 20
        skip = (page - 1) * per_page
        
        subjects = list(cbcs_collection.find(query).skip(skip).limit(per_page))
        total_subjects = cbcs_collection.count_documents(query)
        
        if subjects:
            print("DEBUG - Sample subject fields:", subjects[0].keys())
        
        branches = sorted([b for b in cbcs_collection.distinct('Branch') if b])
        baskets = sorted([b for b in cbcs_collection.distinct('Basket') if b])
        
        return render_template('basket.html', 
                             subjects=subjects,
                             branches=branches,
                             baskets=baskets,
                             current_page=page,
                             total_pages=(total_subjects + per_page - 1) // per_page,
                             total_subjects=total_subjects,
                             filters={'branch': branch, 'basket': basket, 'search': search})
    except Exception as e:
        print(f"ERROR in basket route: {str(e)}")
        return render_template('basket.html', error=str(e))

@app.route('/basket/add', methods=['GET', 'POST'])
def basket_add():
    """Add new CBCS subject"""
    try:
        if request.method == 'POST':
            subject_data = {
                'Branch': request.form.get('branch', '').strip(),
                'Basket': request.form.get('basket', '').strip(),
                'Subject Code': request.form.get('subject_code', '').strip().upper(),
                'Subject_name': request.form.get('subject_name', '').strip(),
                'Credits': request.form.get('credits', '').strip()
            }
            
            if not all([subject_data['Branch'], subject_data['Subject Code'], subject_data['Subject_name']]):
                error = 'Branch, Subject Code, and Subject Name are required'
                branches = sorted([b for b in cbcs_collection.distinct('Branch') if b]) or ['All', 'CSE', 'ECE', 'EEE', 'Civil', 'Mechanical']
                baskets = sorted([b for b in cbcs_collection.distinct('Basket') if b]) or ['Basket I', 'Basket II', 'Basket III', 'Basket IV', 'Basket V']
                return render_template('basket_add.html', error=error, branches=branches, baskets=baskets)
            
            existing = cbcs_collection.find_one({'Subject Code': subject_data['Subject Code']})
            if existing:
                error = 'Subject Code already exists'
                branches = sorted([b for b in cbcs_collection.distinct('Branch') if b]) or ['All', 'CSE', 'ECE', 'EEE', 'Civil', 'Mechanical']
                baskets = sorted([b for b in cbcs_collection.distinct('Basket') if b]) or ['Basket I', 'Basket II', 'Basket III', 'Basket IV', 'Basket V']
                return render_template('basket_add.html', error=error, branches=branches, baskets=baskets)
            
            cbcs_collection.insert_one(subject_data)
            return redirect('/basket?success=Subject added successfully')
        
        branches = sorted([b for b in cbcs_collection.distinct('Branch') if b]) or ['All', 'CSE', 'ECE', 'EEE', 'Civil', 'Mechanical']
        baskets = sorted([b for b in cbcs_collection.distinct('Basket') if b]) or ['Basket I', 'Basket II', 'Basket III', 'Basket IV', 'Basket V']
        
        return render_template('basket_add.html', branches=branches, baskets=baskets)
    except Exception as e:
        return render_template('basket_add.html', error=str(e))

@app.route('/basket/edit/<subject_id>', methods=['GET', 'POST'])
def basket_edit(subject_id):
    """Edit existing CBCS subject"""
    try:
        if not ObjectId.is_valid(subject_id):
            return redirect('/basket?error=Invalid subject ID')
        
        if request.method == 'POST':
            update_data = {
                'Branch': request.form.get('branch', '').strip(),
                'Basket': request.form.get('basket', '').strip(),
                'Subject Code': request.form.get('subject_code', '').strip().upper(),
                'Subject_name': request.form.get('subject_name', '').strip(),
                'Credits': request.form.get('credits', '').strip()
            }
            
            if not all([update_data['Branch'], update_data['Subject Code'], update_data['Subject_name']]):
                error = 'Branch, Subject Code, and Subject Name are required'
                subject = cbcs_collection.find_one({'_id': ObjectId(subject_id)})
                branches = sorted([b for b in cbcs_collection.distinct('Branch') if b]) or ['All', 'CSE', 'ECE', 'EEE', 'Civil', 'Mechanical']
                baskets = sorted([b for b in cbcs_collection.distinct('Basket') if b]) or ['Basket I', 'Basket II', 'Basket III', 'Basket IV', 'Basket V']
                return render_template('basket_edit.html', error=error, subject=subject, branches=branches, baskets=baskets)
            
            existing = cbcs_collection.find_one({
                'Subject Code': update_data['Subject Code'],
                '_id': {'$ne': ObjectId(subject_id)}
            })
            if existing:
                error = 'Subject Code already exists'
                subject = cbcs_collection.find_one({'_id': ObjectId(subject_id)})
                branches = sorted([b for b in cbcs_collection.distinct('Branch') if b]) or ['All', 'CSE', 'ECE', 'EEE', 'Civil', 'Mechanical']
                baskets = sorted([b for b in cbcs_collection.distinct('Basket') if b]) or ['Basket I', 'Basket II', 'Basket III', 'Basket IV', 'Basket V']
                return render_template('basket_edit.html', error=error, subject=subject, branches=branches, baskets=baskets)
            
            result = cbcs_collection.update_one(
                {'_id': ObjectId(subject_id)},
                {'$set': update_data}
            )
            
            if result.matched_count == 0:
                return render_template('basket_edit.html', error='Subject not found')
            
            return redirect('/basket?success=Subject updated successfully')
        
        subject = cbcs_collection.find_one({'_id': ObjectId(subject_id)})
        if not subject:
            return redirect('/basket?error=Subject not found')
        
        branches = sorted([b for b in cbcs_collection.distinct('Branch') if b]) or ['All', 'CSE', 'ECE', 'EEE', 'Civil', 'Mechanical']
        baskets = sorted([b for b in cbcs_collection.distinct('Basket') if b]) or ['Basket I', 'Basket II', 'Basket III', 'Basket IV', 'Basket V']
        
        return render_template('basket_edit.html', subject=subject, branches=branches, baskets=baskets)
    
    except Exception as e:
        print(f"ERROR in basket_edit: {str(e)}")
        return redirect(f'/basket?error={str(e)}')

@app.route('/basket/delete/<subject_id>', methods=['POST'])
def basket_delete(subject_id):
    """Delete CBCS subject"""
    try:
        if not ObjectId.is_valid(subject_id):
            return jsonify({'error': 'Invalid subject ID'}), 400
            
        result = cbcs_collection.delete_one({'_id': ObjectId(subject_id)})
        
        if result.deleted_count == 0:
            return jsonify({'error': 'Subject not found'}), 404
        
        return jsonify({'success': True, 'message': 'Subject deleted successfully'})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/basket/import')
def basket_import():
    """Import CBCS data from CSV file"""
    try:
        import os
        csv_path = 'CBCS.csv'
        if not os.path.exists(csv_path):
            return f"Error: CSV file '{csv_path}' not found. Please upload your CBCS.csv file to the project directory."
        
        df = pd.read_csv(csv_path)
        df = df.dropna(how='all')
        df = df.fillna('')
        
        records = []
        for _, row in df.iterrows():
            if pd.isna(row.get('Subject Code')) or str(row.get('Subject Code', '')).strip() == '':
                continue
                
            record = {
                'Branch': str(row.get('Branch', '')).strip() if not pd.isna(row.get('Branch')) else '',
                'Basket': str(row.get('Basket', '')).strip() if not pd.isna(row.get('Basket')) else '',
                'Subject Code': str(row.get('Subject Code', '')).strip().upper() if not pd.isna(row.get('Subject Code')) else '',
                'Subject_name': str(row.get('Subject_name', '')).strip() if not pd.isna(row.get('Subject_name')) else '',
                'Credits': str(row.get('Credits', '')).strip() if not pd.isna(row.get('Credits')) else ''
            }
            
            if record['Subject Code']:
                records.append(record)
        
        if records:
            cbcs_collection.delete_many({})
            cbcs_collection.insert_many(records)
            return f"<h2>Import Successful!</h2><p>Successfully imported {len(records)} CBCS subjects!</p><a href='/basket'>← Back to CBCS Management</a>"
        else:
            return "<h2>Import Failed</h2><p>No valid records found in CSV file.</p><a href='/basket'>← Back to CBCS Management</a>"
        
    except Exception as e:
        return f"<h2>Import Error</h2><p>Error importing CBCS data: {str(e)}</p><a href='/basket'>← Back to CBCS Management</a>"

@app.route('/basket/debug')
def basket_debug():
    """Debug route to check field names and data structure"""
    try:
        sample = cbcs_collection.find_one()
        if sample:
            fields_html = "<h3>Available Fields:</h3><ul>"
            for field in sample.keys():
                fields_html += f"<li><strong>{field}</strong>: {sample[field]}</li>"
            fields_html += "</ul>"
            
            return f"""
            <h2>CBCS Collection Debug Info</h2>
            {fields_html}
            <br><br>
            <h3>Total Documents:</h3>
            {cbcs_collection.count_documents({})}
            <br><br>
            <a href="/basket">← Back to CBCS Management</a>
            """
        else:
            return """
            <h2>No Data Found</h2>
            <p>No documents found in CBCS collection.</p>
            <a href='/basket/import'>Import data first</a> | 
            <a href="/basket">← Back to CBCS Management</a>
            """
    except Exception as e:
        return f"<h2>Debug Error</h2><p>Error: {str(e)}</p><a href='/basket'>← Back to CBCS Management</a>"







# ---------------- Main Basket Track Route ----------------

@app.route('/baskettrack', methods=['GET', 'POST'])
def baskettrack():
    """Basket tracking system - FIXED VERSION"""
    try:
        search_performed = False
        student_data = {}
        basket_progress = {}
        filters = {
            'department': '',
            'batch': '',
            'registration': '',
            'semester': [],
            'basket': ''
        }
        
        if request.method == 'POST':
            department = request.form.get('department', '').strip()
            batch = request.form.get('batch', '').strip()
            registration = request.form.get('registration', '').strip().upper()
            selected_semesters = request.form.getlist('semester')
            selected_semesters = [sem.strip() for sem in selected_semesters if sem.strip()]
            basket = request.form.get('basket', '').strip()
            
            filters.update({
                'department': department,
                'batch': batch,
                'registration': registration,
                'semester': selected_semesters,
                'basket': basket
            })
            
            print(f"DEBUG - Filters received: {filters}")
            
            if registration and registration != 'All':
                search_performed = True
                
                # Get student information
                student_info = cutm_collection.find_one({"Reg_No": registration}, {"Name": 1, "Reg_No": 1, "_id": 0})
                if not student_info:
                    return render_template('baskettrack.html', error="Student not found", filters=filters)
                
                # Get student's branch
                branch = get_branch_from_reg_no(registration)
                branch_short = branch.split() if branch != "Unknown Branch" else "Unknown"
                print(f"DEBUG - Student branch: {branch} ({branch_short})")
                
                # Get all student subjects
                student_query = {"Reg_No": registration}
                all_student_subjects = list(cutm_collection.find(student_query, {
                    "Subject_Code": 1, "Subject_Name": 1, "Grade": 1, "Sem": 1, "Credits": 1, "_id": 0
                }))
                print(f"DEBUG - Found {len(all_student_subjects)} total student subjects")
                
                # Apply semester filter if specified
                if selected_semesters and 'All' not in selected_semesters:
                    all_student_subjects = [subj for subj in all_student_subjects if subj.get('Sem') in selected_semesters]
                    print(f"DEBUG - After semester filter: {len(all_student_subjects)} subjects")
                
                # **SIMPLIFIED APPROACH: Use Python for credits parsing**
                # Get CBCS data without complex aggregation
                pipeline = []
                
                # Step 1: Enhanced branch matching
                branch_match_conditions = [
                    {"Branch": "All"},
                    {"Branch": branch_short}
                ]
                
                # Add regex patterns for combined branches
                if branch_short != "Unknown":
                    branch_match_conditions.extend([
                        {"Branch": {"$regex": f".*{branch_short}.*", "$options": "i"}},
                        {"Branch": {"$regex": f"{branch_short}.*", "$options": "i"}},
                        {"Branch": {"$regex": f".*{branch_short}", "$options": "i"}}
                    ])
                
                match_stage = {"$match": {"$or": branch_match_conditions}}
                if basket and basket != 'All':
                    match_stage["$match"]["Basket"] = basket
                
                pipeline.append(match_stage)
                
                # Step 2: **FIXED** Basket normalization only
                pipeline.append({
                    "$addFields": {
                        "assigned_basket": {
                            "$switch": {
                                "branches": [
                                    # Handle numeric formats
                                    {"case": {"$eq": ["$Basket", "Basket 1"]}, "then": "Basket I"},
                                    {"case": {"$eq": ["$Basket", "Basket 2"]}, "then": "Basket II"},
                                    {"case": {"$eq": ["$Basket", "Basket 3"]}, "then": "Basket III"},
                                    {"case": {"$eq": ["$Basket", "Basket 4"]}, "then": "Basket IV"},
                                    {"case": {"$eq": ["$Basket", "Basket 5"]}, "then": "Basket V"},
                                    # Handle Roman numeral formats
                                    {"case": {"$eq": ["$Basket", "Basket I"]}, "then": "Basket I"},
                                    {"case": {"$eq": ["$Basket", "Basket II"]}, "then": "Basket II"},
                                    {"case": {"$eq": ["$Basket", "Basket III"]}, "then": "Basket III"},
                                    {"case": {"$eq": ["$Basket", "Basket IV"]}, "then": "Basket IV"},
                                    {"case": {"$eq": ["$Basket", "Basket V"]}, "then": "Basket V"}
                                ],
                                "default": {
                                    "$cond": {
                                        "if": {
                                            "$and": [
                                                {"$ne": ["$Basket", ""]},
                                                {"$ne": ["$Basket", None]},
                                                {"$ne": ["$Basket", "null"]}
                                            ]
                                        },
                                        "then": "$Basket",
                                        "else": "Basket V"
                                    }
                                }
                            }
                        }
                    }
                })
                
                # Step 3: Simple grouping by basket - no complex credit parsing in MongoDB
                pipeline.append({
                    "$group": {
                        "_id": "$assigned_basket",
                        "subjects": {
                            "$push": {
                                "code": "$Subject Code",
                                 "name": "$Subject_name",   # Handles both variations
                                "credits": "$Credits",
                                "original_basket": "$Basket",
                                "branch": "$Branch"
                            }
                        },
                        "total_subjects": {"$sum": 1}
                    }
                })
                
                pipeline.append({"$sort": {"_id": 1}})
                
                print(f"DEBUG - Executing simplified aggregation pipeline with {len(pipeline)} stages")
                
                # Execute CBCS aggregation
                cbcs_basket_data = list(cbcs_collection.aggregate(pipeline))
                print(f"DEBUG - Aggregation returned {len(cbcs_basket_data)} baskets")
                
                # **Process in Python - much more reliable**
                student_subject_codes = {subj.get('Subject_Code') for subj in all_student_subjects}
                
                # Process each basket's subjects
                for basket in cbcs_basket_data:
                    basket_subjects = []
                    total_earned_credits = 0
                    completed_subjects_count = 0
                    
                    for subject in basket.get('subjects', []):
                        subject_code = subject.get('code')
                        
                        # Check if student has completed this subject
                        completed = subject_code in student_subject_codes
                        
                        # Parse credits using Python function
                        credits_numeric = parse_credits_normalized(subject.get('credits', ''))
                        earned_credits = credits_numeric if completed else 0
                        
                        # Get student's semester for this subject
                        student_semester = None
                        if completed:
                            for student_subj in all_student_subjects:
                                if student_subj.get('Subject_Code') == subject_code:
                                    student_semester = student_subj.get('Sem')
                                    break
                        
                        processed_subject = {
                            'code': subject_code,
                            'name': subject.get('name', ''),
                            'credits': subject.get('credits', ''),
                            'credits_numeric': credits_numeric,
                            'completed': completed,
                            'semester': student_semester,
                            'earned_credits': earned_credits,
                            'original_basket': subject.get('original_basket'),
                            'branch': subject.get('branch'),
                            'is_default_assigned': False
                        }
                        
                        basket_subjects.append(processed_subject)
                        
                        if completed:
                            total_earned_credits += earned_credits
                            completed_subjects_count += 1
                    
                    # Update basket data
                    basket['subjects'] = basket_subjects
                    basket['completed_subjects'] = completed_subjects_count
                    basket['total_earned_credits'] = total_earned_credits
                
                print(f"DEBUG - Processed baskets with credits:")
                for basket in cbcs_basket_data:
                    print(f"  - {basket.get('_id')}: {basket.get('total_earned_credits')} earned credits")
                
                # Find uncategorized subjects (completed but not in CBCS)
                completed_subject_codes = set()
                for basket in cbcs_basket_data:
                    for subject in basket.get('subjects', []):
                        if subject.get('completed'):
                            completed_subject_codes.add(subject.get('code'))
                
                uncategorized_codes = student_subject_codes - completed_subject_codes
                uncategorized_subjects = []
                
                for subj in all_student_subjects:
                    if subj.get('Subject_Code') in uncategorized_codes:
                        credits_numeric = parse_credits_normalized(subj.get('Credits', ''))
                        uncategorized_subjects.append({
                            'code': subj.get('Subject_Code'),
                            'name': subj.get('Subject_Name', ''),
                            'credits': subj.get('Credits', ''),
                            'credits_numeric': credits_numeric,
                            'completed': True,
                            'semester': subj.get('Sem'),
                            'earned_credits': credits_numeric,
                            'original_basket': 'Unknown',
                            'branch': 'Unknown',
                            'is_default_assigned': True
                        })
                
                print(f"DEBUG - Found {len(uncategorized_subjects)} uncategorized subjects")
                
                # Add uncategorized subjects to Basket V
                if uncategorized_subjects:
                    basket_v_found = False
                    for basket in cbcs_basket_data:
                        if basket['_id'] == 'Basket V':
                            basket['subjects'].extend(uncategorized_subjects)
                            basket['total_subjects'] += len(uncategorized_subjects)
                            basket['completed_subjects'] += len(uncategorized_subjects)
                            basket['total_earned_credits'] += sum(s['earned_credits'] for s in uncategorized_subjects)
                            basket_v_found = True
                            break
                    
                    if not basket_v_found:
                        new_basket_v = {
                            '_id': 'Basket V',
                            'subjects': uncategorized_subjects,
                            'total_subjects': len(uncategorized_subjects),
                            'completed_subjects': len(uncategorized_subjects),
                            'total_earned_credits': sum(s['earned_credits'] for s in uncategorized_subjects)
                        }
                        cbcs_basket_data.append(new_basket_v)
                
                # Ensure ALL baskets are present
                all_baskets = ['Basket I', 'Basket II', 'Basket III', 'Basket IV', 'Basket V']
                basket_dict = {basket['_id']: basket for basket in cbcs_basket_data if basket.get('_id')}
                
                # Initialize overall statistics
                overall_stats = {
                    'total_subjects': 0,
                    'completed_subjects': 0,
                    'total_required_credits': sum(BASKET_CREDIT_REQUIREMENTS.values()),
                    'total_earned_credits': 0,
                    'baskets_completed': 0,
                    'total_baskets': len(all_baskets),
                    'default_assigned_subjects': len(uncategorized_subjects)
                }
                
                # Process ALL baskets
                for basket_name in all_baskets:
                    basket_required_credits = BASKET_CREDIT_REQUIREMENTS.get(basket_name, 0)
                    
                    if basket_name in basket_dict:
                        basket = basket_dict[basket_name]
                        basket_earned_credits = basket.get('total_earned_credits', 0)
                        
                        completion_percentage = round((basket_earned_credits / basket_required_credits) * 100, 1) if basket_required_credits > 0 else 0
                        is_basket_completed = basket_earned_credits >= basket_required_credits
                        status = "Completed" if is_basket_completed else ("Not Started" if basket_earned_credits == 0 else "Not Completed")
                        
                        default_count = sum(1 for s in basket.get('subjects', []) if s.get('is_default_assigned', False))
                        
                        basket_progress[basket_name] = {
                            'subjects': basket.get('subjects', []),
                            'total_subjects': basket.get('total_subjects', 0),
                            'completed_subjects': basket.get('completed_subjects', 0),
                            'required_credits': basket_required_credits,
                            'earned_credits': basket_earned_credits,
                            'pending_credits': max(0, basket_required_credits - basket_earned_credits),
                            'percentage': completion_percentage,
                            'status': status,
                            'is_completed': is_basket_completed,
                            'has_default_subjects': default_count > 0,
                            'default_assigned_count': default_count
                        }
                        
                        # Update overall statistics
                        overall_stats['total_subjects'] += basket.get('total_subjects', 0)
                        overall_stats['completed_subjects'] += basket.get('completed_subjects', 0)
                        overall_stats['total_earned_credits'] += basket_earned_credits
                        
                        if is_basket_completed:
                            overall_stats['baskets_completed'] += 1
                    else:
                        # Create empty basket data for missing baskets
                        basket_progress[basket_name] = {
                            'subjects': [],
                            'total_subjects': 0,
                            'completed_subjects': 0,
                            'required_credits': basket_required_credits,
                            'earned_credits': 0,
                            'pending_credits': basket_required_credits,
                            'percentage': 0,
                            'status': "Not Started",
                            'is_completed': False,
                            'has_default_subjects': False,
                            'default_assigned_count': 0
                        }
                
                # Calculate final statistics
                overall_stats['percentage'] = round((overall_stats['total_earned_credits'] / overall_stats['total_required_credits']) * 100, 1) if overall_stats['total_required_credits'] > 0 else 0
                overall_stats['overall_status'] = "Completed" if overall_stats['baskets_completed'] == overall_stats['total_baskets'] else "In Progress"
                
                # Prepare final student data
                student_data = {
                    'name': student_info.get('Name', 'Unknown'),
                    'registration': registration,
                    'department': branch,
                    'overall_stats': overall_stats
                }
                
                print(f"DEBUG - Final stats: {overall_stats}")
                
                return render_template('baskettrack.html',
                                     student_data=student_data,
                                     basket_progress=basket_progress,
                                     filters=filters,
                                     search_performed=search_performed,
                                     basket_requirements=BASKET_CREDIT_REQUIREMENTS)
        
        return render_template('baskettrack.html', filters=filters)
        
    except Exception as e:
        print(f"ERROR in baskettrack: {str(e)}")
        traceback.print_exc()
        return render_template('baskettrack.html', error=f"System error: {str(e)}", filters=filters)

# ---------------- Additional Helper Routes ----------------

@app.route('/api/basket_requirements')
def get_basket_requirements():
    """API endpoint to get basket credit requirements"""
    return jsonify(BASKET_CREDIT_REQUIREMENTS)

@app.route('/debug/baskets/<registration>')
def debug_baskets(registration):
    """Debug route to check basket assignments and data structure"""
    try:
        # Get student's branch
        branch = get_branch_from_reg_no(registration)
        branch_short = branch.split()[0] if branch != 'Unknown Branch' else 'Unknown'
        
        # Check CBCS subjects for this branch
        branch_conditions = [
            {"Branch": "All"},
            {"Branch": branch_short},
            {"Branch": {"$regex": f".*{branch_short}.*", "$options": "i"}}
        ]
        
        cbcs_subjects = list(cbcs_collection.find({
            "$or": branch_conditions
        }, {
            "Branch": 1,
            "Basket": 1,
            "Subject Code": 1,
            "Subject_name": 1,
            "Credits": 1,
            "_id": 0
        }).limit(20))
        
        # Group by basket for summary
        baskets_found = {}
        for subject in cbcs_subjects:
            basket = subject.get('Basket', 'Unknown')
            if basket not in baskets_found:
                baskets_found[basket] = 0
            baskets_found[basket] += 1
        
        # Check student records
        student_records = list(cutm_collection.find({
            "Reg_No": registration
        }, {
            "Subject_Code": 1,
            "Subject_Name": 1,
            "Grade": 1,
            "Sem": 1,
            "Credits": 1,
            "_id": 0
        }).limit(20))
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Debug: Basket Data for {registration}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .section {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
                pre {{ background: #f5f5f5; padding: 10px; border-radius: 3px; overflow-x: auto; }}
                .nav {{ margin-bottom: 20px; }}
                .nav a {{ padding: 10px 15px; background: #007bff; color: white; text-decoration: none; border-radius: 3px; margin-right: 10px; }}
                .nav a:hover {{ background: #0056b3; }}
            </style>
        </head>
        <body>
            <div class="nav">
                <a href="/baskettrack">← Back to Basket Track</a>
                <a href="/">Main Dashboard</a>
            </div>
            
            <h1>🔍 Debug Info for Registration: {registration}</h1>
            
            <div class="section">
                <h2>Student Branch Information</h2>
                <p><strong>Full Branch:</strong> {branch}</p>
                <p><strong>Short Branch:</strong> {branch_short}</p>
            </div>
            
            <div class="section">
                <h2>CBCS Baskets Summary</h2>
                <pre>{baskets_found}</pre>
            </div>
            
            <div class="section">
                <h2>Statistics</h2>
                <p><strong>Total CBCS Subjects Found:</strong> {len(cbcs_subjects)}</p>
                <p><strong>Total Student Records:</strong> {len(student_records)}</p>
            </div>
            
            <div class="section">
                <h2>Sample CBCS Subjects (first 20)</h2>
                <pre>{cbcs_subjects}</pre>
            </div>
            
            <div class="section">
                <h2>Sample Student Records (first 20)</h2>
                <pre>{student_records}</pre>
            </div>
            
            <div class="section">
                <h2>Branch Match Conditions Used</h2>
                <pre>{branch_conditions}</pre>
            </div>
        </body>
        </html>
        """
        
    except Exception as e:
        return f"<h1>Debug Error</h1><p>{str(e)}</p><a href='/baskettrack'>← Back</a>"

# ---------------- AJAX Helper Routes ----------------

@app.route('/ajax/get_departments')
def ajax_get_departments():
    """Get all departments"""
    try:
        departments = cutm_collection.distinct('Department')
        options = ['<option value="">Select Department</option>']
        options.append('<option value="All">All</option>')
        
        for dept in sorted(departments):
            if dept:
                options.append(f'<option value="{dept}">{dept}</option>')
        
        return '\n'.join(options)
    except Exception as e:
        return '<option value="">Error loading departments</option>'

@app.route('/ajax/get_registrations', methods=['POST'])
def ajax_get_registrations():
    """Get registrations by department"""
    try:
        department = request.form.get('department', '')
        query = {}
        
        if department and department != 'All':
            branch_mapping = {
                'Civil Engineering': '1',
                'Computer Science Engineering': '2', 
                'Electronics & Communication Engineering': '3',
                'Electrical & Electronics Engineering': '5',
                'Mechanical Engineering': '6'
            }
            
            branch_code = branch_mapping.get(department)
            if branch_code:
                query['Reg_No'] = {'$regex': f'^.{{{7}}}{branch_code}'}
        
        registrations = cutm_collection.distinct('Reg_No', query)
        
        options = ['<option value="">Select Registration No</option>']
        options.append('<option value="All">All</option>')
        
        for reg in sorted(registrations):
            options.append(f'<option value="{reg}">{reg}</option>')
        
        return '\n'.join(options)
    except Exception as e:
        return '<option value="">Error loading registrations</option>'

@app.route('/ajax/get_semesters', methods=['POST'])
def ajax_get_semesters():
    """Get semesters for a specific registration number"""
    try:
        registration = request.form.get('registration', '').strip().upper()
        if not registration or registration == 'All':
            return '<option value="">Select Semester</option><option value="All">All Semesters</option>'
        
        semesters = sorted(set(doc["Sem"] for doc in cutm_collection.find(
            {"Reg_No": registration}, 
            {"Sem": 1, "_id": 0}
        ) if doc.get("Sem")))
        
        options = ['<option value="">Select Semester</option>']
        options.append('<option value="All">All Semesters</option>')
        
        for sem in semesters:
            options.append(f'<option value="{sem}">{sem}</option>')
        
        return '\n'.join(options)
    except Exception as e:
        return '<option value="">Error loading semesters</option>'

@app.route('/ajax/get_baskets', methods=['POST'])
def ajax_get_baskets():
    """Get all available baskets"""
    try:
        baskets = ['Basket I', 'Basket II', 'Basket III', 'Basket IV', 'Basket V']
        
        options = ['<option value="">Select Basket</option>']
        options.append('<option value="All">All Baskets</option>')
        
        for basket in baskets:
            credits = BASKET_CREDIT_REQUIREMENTS.get(basket, 0)
            options.append(f'<option value="{basket}">{basket} ({credits} Credits)</option>')
        
        return '\n'.join(options)
    except Exception as e:
        return '<option value="">Error loading baskets</option>'

# ---------------- Run Application ----------------
if __name__ == "__main__":
    app.run(debug=True)
