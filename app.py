from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector
from db_config import db_config
import datetime
import re
import os
import pytesseract
from PIL import Image
import google.generativeai as genai
from services.risk_service import predict_risk
import random
import string

app = Flask(__name__)
app.secret_key = "super_secure_key"

# ==========================================
# 1. AI CONFIGURATION
# ==========================================

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.5-flash')

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# ==========================================
# 2. HELPER FUNCTIONS
# ==========================================

DOCTORS_NAMES = [
    "Dr. A. Smith (Cardiology)", "Dr. B. Jones (Neurology)",
    "Dr. C. Williams (Orthopedics)", "Dr. D. Brown (Pediatrics)",
    "Dr. E. Davis (General Surgeon)", "Dr. F. Miller (ENT)",
    "Dr. G. Wilson (Dermatology)", "Dr. H. Moore (Gynecology)",
    "Dr. I. Taylor (Oncology)", "Dr. J. Anderson (Psychiatry)"
]

def generate_reference():
    while True:
        ref = "ref" + str(random.randint(100, 9999))

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT * FROM users WHERE Reference_No=%s", (ref,))
        exists = cur.fetchone()

        cur.close()
        conn.close()

        if not exists:
            return ref

def get_db_connection():
    try:
        return mysql.connector.connect(**db_config)
    except mysql.connector.Error as err:
        print(f"DB Connection Error: {err}")
        return None

def calculate_age(dob_str):
    for fmt in ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"]:
        try:
            birth_date = datetime.datetime.strptime(str(dob_str), fmt).date()
            today = datetime.date.today()
            return today.year - birth_date.year - (
                (today.month, today.day) < (birth_date.month, birth_date.day)
            )
        except:
            continue
    return 30  # fallback


def get_health_advice(row):
    advice_list = []
    tablet = row.get('Nameoftablets', '').lower()
    daily_dose_str = row.get('dailydose', '1')
    dob = row.get('DOB', '')
    disease = row.get('Disease', '')

    # Basic rule-based advice
    if "paracetamol" in tablet or "dollo" in tablet:
        advice_list.append("🌡️ <b>Fever:</b> Maintain 6-hour gaps between doses.")
    elif "amlodipine" in tablet:
        advice_list.append("❤️ <b>Blood Pressure:</b> Take at the same time every day.")

    # ===== AI Risk Model Prediction (FIXED) =====
    try:
        age = calculate_age(dob)
        dose_match = re.search(r'\d+', str(daily_dose_str))
        dose_val = int(dose_match.group()) if dose_match else 1

        is_anti = 1 if any(x in tablet for x in ['cillin', 'mycin']) else 0
        is_pain = 1 if any(x in tablet for x in ['pain', 'dol', 'fenac']) else 0

        prediction, probability = predict_risk(age, dose_val, is_anti, is_pain)

        if prediction == 1:
            advice_list.append(
                f"🤖 <b>AI Alert:</b> High-risk dosage pattern detected "
                f"(Risk: {round(probability * 100, 2)}%)."
            )

    except Exception as e:
        print("Risk model error:", e)

    if disease:
        advice_list.append(f"🩺 <b>Note:</b> Monitoring for {disease}.")

    return advice_list

def parse_intent(text, context_ref=None):
    t = text.lower().strip()
    m = re.search(r"(ref[-_0-9a-zA-Z]+|\bref\s*\d+|\bpt[-_0-9a-zA-Z]+|\b[a-zA-Z]{2}\d{2,}|\b\d{3,})", t)
    
    ref = None
    if m: 
        raw_match = m.group(0)
        ref = re.sub(r"\b(reference|patient|ref|pt)\b\s*[:#]?\s*", "", raw_match, flags=re.IGNORECASE).replace(" ", "")
    
    if not ref and context_ref: ref = context_ref

    # --- 2. INTENT CLASSIFICATION ---
    show_keywords = ["show", "details", "display", "info", "tell me", "about", "give me", "status", "who is"]
    if any(k in t for k in show_keywords) and ref: return "show_patient", ref
    
    supply_keywords = ["supply", "days left", "stock", "how many", "remain"]
    if any(k in t for k in supply_keywords) and ref: return "supply", ref
    
    advice_keywords = ["recommend", "advice", "health", "risk", "safe", "what to do"]
    if any(k in t for k in advice_keywords) and ref: return "recommend", ref
    
    if ref and not any(k in t for k in ["hi", "hello", "help", "thanks"]): return "show_patient", ref
    

    return "general_chat", ref




# ==========================================
# AUTHENTICATION ROUTES
# ==========================================

@app.route('/register', methods=['GET','POST'])
def register():

    if request.method == 'POST':

        ref_no = request.form['Reference_No']
        #name= request.form['username']
        password = generate_password_hash(request.form['password'])
        role= request.form['role']
        conn = get_db_connection()
        cur = conn.cursor()

        try:
            # check if username already exists
            #cur.execute("SELECT * FROM users WHERE Reference_No=%s",(ref_no,))
            #cur.execute("SELECT * FROM users WHERE username=%s",(name,))
            #existing = cur.fetchone()

            #if existing:
            #    return "Reference number already exists"

            cur.execute("INSERT INTO users(Reference_No,password,role) VALUES(%s,%s,%s)",(ref_no,password,'patient'))
            #cur.execute("INSERT INTO users(username,password,role) VALUES(%s,%s,%s)",(name,password,'doctor'))

            conn.commit()

        except Exception as e:
            conn.rollback()
            return f"Database error: {str(e)}"

        finally:
            cur.close()
            conn.close()

        return redirect('/login')
    
    # GET request → generate reference
    ref = generate_reference()

    return render_template("register.html", ref_no=ref)


@app.route('/login', methods=['GET', 'POST'])
def login_page():
    return render_template("select_role.html")

@app.route('/choose_role', methods=['POST'])
def choose_role():

    role = request.form['role']

    if role == "doctor":
        return render_template("doctor_login.html")

    else:
        return render_template("patient_login.html")


@app.route('/doctor_login', methods=['POST'])
def doctor_login():
    
    username = request.form['username']
    password = request.form['password']

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    cur.execute("SELECT * FROM users WHERE username=%s AND role='doctor'", (username,))
    user = cur.fetchone()

    cur.close()
    conn.close()

    if user and check_password_hash(user['password'], password):

        session['user'] = username
        session['role'] = 'doctor'

        return redirect('/')

    return "Invalid doctor login"

@app.route('/patient_login', methods=['POST'])
def patient_login():

    ref_no = request.form['ref_no']
    password = request.form['password']

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    cur.execute("SELECT * FROM users WHERE Reference_No=%s AND role='patient'", (ref_no,))
    user = cur.fetchone()

    if user and check_password_hash(user['password'], password):

        session['user'] = ref_no
        session['role'] = 'patient'
        session['patient_ref'] = ref_no

        cur.close()
        conn.close()

        return redirect('/')

    cur.close()
    conn.close()

    return "Invalid patient login"

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


# ==========================================
# 3. ROUTES
# ==========================================

@app.route('/')
def index():
     if 'user' not in session:
            return redirect('/login')
     
     conn = get_db_connection()
     if not conn:
        return "Database connection failed."
     
     conn = get_db_connection()
     cursor = conn.cursor(dictionary=True)
     
     if session['role'] == 'patient':
        ref = session.get('patient_ref')
        cursor.execute(
            "SELECT * FROM hospital WHERE Reference_No=%s",
            (ref,)
        )
        patient = cursor.fetchone()
        conn.close()

        return render_template("patient_dashboard.html", patient=patient)

     else:  # doctor
        cursor.execute("SELECT * FROM hospital")
        patients = cursor.fetchall()
        conn.close()

        return render_template("index.html", patients=patients, doctors=DOCTORS_NAMES)
@app.route('/add', methods=['POST'])
def add_patient():
    if session.get('role') != "doctor":
        return "Unauthorized"

    data = request.form
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # UPDATED SQL: Added 'Disease' column
        sql = """INSERT INTO hospital (Nameoftablets, Reference_No, dose, Numbersoftablets, lot, issuedate, expdate, dailydose, storage, nhsnumber, patientname, DOB, patientaddress, doctor, Disease) 
                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
        
        # UPDATED VALUES: Added data.get('disease')
        val = (data['name'], data['ref'], data['dose'], data['no_of_tablets'], data['lot'], data['issue_date'], 
               data['exp_date'], data['daily_dose'], data['storage'], data['nhs'], data['pname'], data['dob'], 
               data['address'], data['doctor'], data.get('disease', ''))
        
        cur.execute(sql, val)
        conn.commit()
        conn.close()
    except Exception as e:
        print("Error adding:", e)
    return redirect(url_for('index'))

@app.route('/update', methods=['POST'])
def update_patient():
     if session.get('role') != "doctor":
            return "Unauthorized"

     data = request.form
     try:
        conn = get_db_connection()
        cur = conn.cursor()
        # UPDATED SQL: Added 'Disease=%s'
        sql = """UPDATE hospital SET Nameoftablets=%s, dose=%s, Numbersoftablets=%s, lot=%s, issuedate=%s, expdate=%s, 
                 dailydose=%s, storage=%s, nhsnumber=%s, patientname=%s, DOB=%s, patientaddress=%s, doctor=%s, Disease=%s 
                 WHERE Reference_No=%s"""
        
        # UPDATED VALUES: Added data.get('disease') before reference no
        val = (data['name'], data['dose'], data['no_of_tablets'], data['lot'], data['issue_date'], 
               data['exp_date'], data['daily_dose'], data['storage'], data['nhs'], data['pname'], 
               data['dob'], data['address'], data['doctor'], data.get('disease', ''), data['ref'])
        
        cur.execute(sql, val)
        conn.commit()
        conn.close()
     except Exception as e:
        print("Error updating:", e)
     return redirect(url_for('index'))

@app.route('/predict', methods=['GET', 'POST'])
def predict():
    if request.method == 'POST':
        try:
            age = int(request.form['age'])
            dose_val = int(request.form['dose_val'])
            tablet = request.form['tablet'].lower()

            is_anti = 1 if any(x in tablet for x in ['cillin', 'mycin']) else 0
            is_pain = 1 if any(x in tablet for x in ['pain', 'dol', 'fenac']) else 0

            prediction, probability = predict_risk(age, dose_val, is_anti, is_pain)

            risk_label = "High Risk" if prediction == 1 else "Low Risk"

            return render_template(
                'risk_result.html',
                risk=risk_label,
                probability=round(probability * 100, 2)
            )

        except Exception as e:
            return f"Prediction Error: {str(e)}"

    return render_template('risk_form.html')

@app.route('/delete/<ref>', methods=['GET'])
def delete_patient(ref):
    if session.get('role') != "doctor":
        return "Unauthorized"

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM hospital WHERE Reference_No=%s", (ref,))
        conn.commit()
        conn.close()
    except Exception as e:
        print("Error deleting:", e)
    return redirect(url_for('index'))


@app.route('/chat', methods=['POST'])
def chat():
    try:
        req = request.json
        user_text = req.get('message', '')
        context_ref = req.get('context_ref', '')

        intent, ref = parse_intent(user_text, context_ref)

        if intent in ["show_patient", "supply", "recommend"] and ref:

            # Authorization check
            if session.get('role') == 'patient':
                allowed_ref = session.get('patient_ref')

                if ref != allowed_ref:
                    return jsonify({
                        "response": "❌ You are not authorized to access other patient records."
                    })

            # Open DB connection ONCE
            conn = get_db_connection()
            cur = conn.cursor(dictionary=True)

            cur.execute("SELECT * FROM hospital WHERE Reference_No=%s", (ref,))
            row = cur.fetchone()

            cur.close()
            conn.close()

            if row:

                if intent == "show_patient":
                    assigned_doc = row.get('doctor', 'Not Assigned')

                    details = (
                        f"<b>👤 Patient Profile:</b><br>"
                        f"Name: {row['patientname']} (DOB: {row['DOB']})<br>"
                        f"Ref: {row['Reference_No']} | NHS: {row['nhsnumber']}<br>"
                        f"<b>🩺 Condition:</b> {row.get('Disease', 'Not Specified')}<br>"
                        f"Address: {row['patientaddress']}<br>"
                        f"<b>👨‍⚕️ Assigned Doctor:</b> {assigned_doc}<br>----------------<br>"
                        f"<b>💊 Prescription:</b><br>"
                        f"Tablet: {row['Nameoftablets']} (Qty: {row['Numbersoftablets']})<br>"
                        f"Dose: {row['dose']} | Daily: {row['dailydose']}<br>"
                        f"Issued: {row['issuedate']} | Exp: {row['expdate']}"
                    )

                    tips_html = "<br>".join(get_health_advice(row))

                    return jsonify({
                        "response": details + f"<br><br><b>💡 Health & Safety Advice:</b><br>{tips_html}"
                    })

                elif intent == "recommend":
                    tips_html = "<br>".join(get_health_advice(row))
                    return jsonify({
                        "response": f"<b>💡 Advice for {row['patientname']}:</b><br>{tips_html}"
                    })

                elif intent == "supply":
                    try:
                        total_qty = float(row['Numbersoftablets'])
                        daily_dose = float(row['dailydose'])
                        issue_date_str = row['issuedate']

                        total_days_supply = int(total_qty / daily_dose)

                        issue_date = None
                        for fmt in ["%d-%m-%Y", "%d-%m-%y", "%d/%m/%Y", "%Y-%m-%d"]:
                            try:
                                issue_date = datetime.datetime.strptime(str(issue_date_str), fmt).date()
                                break
                            except:
                                continue

                        if issue_date:
                            days_passed = (datetime.date.today() - issue_date).days
                            remaining_days = total_days_supply - days_passed

                            if remaining_days <= 0:
                                return jsonify({
                                    "response": f"⚠️ Medicine supply for {row['patientname']} has finished.",
                                    "ref": row['Reference_No']
                                })
                            else:
                                return jsonify({
                                    "response": f"📅 {row['patientname']} has approx <b>{remaining_days} days</b> of medicine left.",
                                    "ref": row['Reference_No']
                                })
                        else:
                            return jsonify({
                                "response": f"Total supply: {total_days_supply} days (Issue date unknown).",
                                "ref": row['Reference_No']
                            })

                    except:
                        return jsonify({
                            "response": "Cannot calculate supply (check dose/qty).",
                            "ref": row['Reference_No']
                        })

        # Gemini AI response
        patient_context = "No specific patient selected."

        if context_ref:
            conn = get_db_connection()
            cur = conn.cursor(dictionary=True)

            cur.execute("SELECT * FROM hospital WHERE Reference_No=%s", (context_ref,))
            row = cur.fetchone()

            cur.close()
            conn.close()

            if row:
                patient_context = (
                    f"Patient Name: {row['patientname']}, "
                    f"Age: {calculate_age(row['DOB'])}, "
                    f"Condition: {row.get('Disease','Unknown')}, "
                    f"Medicine: {row['Nameoftablets']}, "
                    f"Dose: {row['dose']}"
                )

        prompt = f"Context: {patient_context}\nUser: {user_text}\nAnswer briefly as a medical assistant."
        ai_response = model.generate_content(prompt)

        bot_reply = ai_response.text.replace("\n", "<br>")

        return jsonify({"response": f"🤖 <b>AI:</b> {bot_reply}"})

    except Exception as e:
        return jsonify({"response": f"Chat Error: {str(e)}"}), 500

@app.route('/scan_prescription', methods=['POST'])
def scan_prescription():
    file = request.files['file']
    img = Image.open(file)
    text = pytesseract.image_to_string(img)

    return jsonify({
        "raw_text": text.replace("\n","<br>")
    })

@app.route('/health_assessment',methods=['POST'])
def health_assessment():
    try:
        data=request.json
        name = data.get('name','')
        age = data.get('age','')
        symptoms = data.get('symptoms','')
        visited = data.get('visitedDoctor','')
        medicine = data.get('medicine','')
        
        prompt=f"""
        You are a hospital AI assistant.
        
        Patient:
        Name: {name}
        Age: {age}
        Symptoms: {symptoms}
        Visited Doctor: {visited}
        Current Medicine: {medicine}
        
        Give a SHORT answer in very simple words.
        
        Format:
        
        Possible issue:
        - (1 or 2 possible diseases only)
    
        Medicine that may help:
        - (1 or 2 common medicines)
        
        Precautions:
        - (2 short points)
        
        End with a note saying in bold: 
        "Please consult a doctor before taking any medicine."
        
        Keep the answer under 80 words and use only simple words.
        """
        
        response= model.generate_content(prompt)
        
        return jsonify({
            "response":response.text.replace("\n","<br>")
        })
    
    except Exception as e:
        return jsonify({
            "response": f"Error: {str(e)}"
        })


if __name__ == '__main__':
    app.run(debug=True)
