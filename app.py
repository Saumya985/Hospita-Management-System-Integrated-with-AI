from flask import Flask, render_template, request, jsonify, redirect, url_for
import mysql.connector
from db_config import db_config
import datetime
import re
import joblib           # For AI Risk Model
import numpy as np      # For Data Handling
import os               # For File Paths
import pytesseract      # For OCR (Vision)
from PIL import Image   # For Image Processing
import google.generativeai as genai  # NEW: For Interactive Chat

app = Flask(__name__)

# 1. AI CONFIGURATION

# --- A. GEMINI API SETUP ---

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-flash-latest')

# --- B. OCR / VISION SETUP ---
# Update this path if Tesseract is installed elsewhere on your system
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# --- C. RISK MODEL SETUP ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, 'risk_model.pkl')

try:
    risk_model = joblib.load(MODEL_PATH)
    print(f"✅ SUCCESS: AI Risk Model loaded from {MODEL_PATH}")
except Exception as e:
    risk_model = None
    print(f"⚠️ WARNING: Could not load AI model. Error: {e}")

# ==========================================
# 2. HELPER FUNCTIONS
# ==========================================

DOCTORS_NAMES = [
    "Dr. A. Smith (Cardiology)", "Dr. B. Jones (Neurology)", "Dr. C. Williams (Orthopedics)",
    "Dr. D. Brown (Pediatrics)", "Dr. E. Davis (General Surgeon)", "Dr. F. Miller (ENT)",
    "Dr. G. Wilson (Dermatology)", "Dr. H. Moore (Gynecology)", "Dr. I. Taylor (Oncology)",
    "Dr. J. Anderson (Psychiatry)"
]

def get_db_connection():
    try:
        conn = mysql.connector.connect(**db_config)
        return conn
    except mysql.connector.Error as err:
        print(f"Error connecting to DB: {err}")
        return None

def calculate_age(dob_str):
    try:
        # Support multiple date formats for reliability
        for fmt in ["%d-%m-%Y", "%d-%m-%y", "%d/%m/%Y", "%Y-%m-%d"]:
            try:
                birth_date = datetime.datetime.strptime(str(dob_str), fmt).date()
                today = datetime.date.today()
                return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
            except: continue
        return None
    except: return None

def get_health_advice(row):
    advice_list = []
    tablet = row.get('Nameoftablets', '').lower()
    daily_dose_str = row.get('dailydose', '0')
    dob = row.get('DOB', '')
    storage = row.get('storage', '')
    expdate = row.get('expdate', '')
    disease = row.get('Disease', '')  # Get disease info for advice

    # --- PART 1: EXISTING RULES ---
    exp_date_obj = None
    for fmt in ["%d-%m-%Y", "%d-%m-%y", "%d/%m/%Y", "%Y-%m-%d"]:
        try:
            exp_date_obj = datetime.datetime.strptime(str(expdate), fmt).date()
            break
        except: pass
    
    if exp_date_obj:
        days_left = (exp_date_obj - datetime.date.today()).days
        if days_left < 0: 
            advice_list.append("🔴 <b>CRITICAL:</b> Medicine EXPIRED! Do not consume.")
        elif days_left < 30: 
            advice_list.append(f"⚠️ <b>Expiry Warning:</b> Expires in {days_left} days.")

    if "corona" in tablet or "vaccine" in tablet: 
        advice_list.append("💉 <b>Vaccine Care:</b> Mild fever is normal. Rest for 2 days.")
    elif "acetaminophen" in tablet: 
        advice_list.append("💊 <b>Pain/Fever:</b> Take after food. Do not exceed dose.")
    elif "adderall" in tablet: 
        advice_list.append("🧠 <b>Focus:</b> Take early to avoid insomnia.")
    elif "amlodipine" in tablet: 
        advice_list.append("❤️ <b>BP Meds:</b> Avoid sudden standing.")
    elif "ativan" in tablet: 
        advice_list.append("💤 <b>Anxiety/Sleep:</b> May cause drowsiness. Do not drive.")
    elif "paracetamol" in tablet or "dollo" in tablet: 
        advice_list.append("🌡️ <b>Fever:</b> Monitor temperature. Gap of 6 hours between doses.")
    else: 
        advice_list.append("ℹ️ <b>General:</b> Complete the full course.")

# Age-Specific Safety
    age = calculate_age(dob)
    if age is None: age = 30 
    if age > 60: advice_list.append(f"👴 <b>Senior Care:</b> Drink water frequently, watch for dizziness.")
    if age < 12: advice_list.append(f"👶 <b>Child Care:</b> Ensure dosage is strictly by weight.")

    # --- PART 2: AI RISK PREDICTION ---
    if risk_model:
        try:
            try:
                dose_val = int(re.search(r'\d+', str(daily_dose_str)).group())
            except:
                dose_val = 1
            
            is_anti = 1 if any(x in tablet for x in ['cillin', 'mycin', 'oxacin', 'corona']) else 0
            is_pain = 1 if any(x in tablet for x in ['pain', 'acetaminophen', 'dol', 'fenac']) else 0
            
            prediction = risk_model.predict([[age, dose_val, is_anti, is_pain]])
            
            if prediction[0] == 1:
                advice_list.append("🤖 <b>AI RISK ALERT:</b> High-risk dosage pattern detected for this age group. Verify with doctor.")
            else:
                advice_list.append("🤖 <b>AI Analysis:</b> Dosage looks standard for this patient profile.")
        except Exception as e:
            print(f"AI Prediction Error: {e}")

    if storage and "fridge" in storage.lower(): 
        advice_list.append("❄️ <b>Storage:</b> Keep Refrigerated.")
    
    # Specific Advice based on Disease field
    if disease:
        advice_list.append(f"🩺 <b>Condition Note:</b> Managing {disease}.")

    return advice_list

def parse_intent(text, context_ref=None):
    t = text.lower().strip()
    
    # --- 1. SMART ID EXTRACTION using Regex---
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
# 3. APP ROUTES
# ==========================================

@app.route('/')
def index():
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM hospital")
        patients = cursor.fetchall()
        conn.close()

        assigned_doctors = set()
        for p in patients:
            if p.get('doctor'):
                doc_name_only = p['doctor'].split(' - ')[0]
                assigned_doctors.add(doc_name_only)
        
        doctors_status_list = []
        for doc_name in DOCTORS_NAMES:
            if doc_name in assigned_doctors:
                doctors_status_list.append(f"{doc_name} - Busy")
            else:
                doctors_status_list.append(f"{doc_name} - Available")

        return render_template('index.html', patients=patients, doctors=doctors_status_list)
    else:
        return "Database Connection Failed."

@app.route('/add', methods=['POST'])
def add_patient():
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

@app.route('/delete/<ref>', methods=['GET'])
def delete_patient(ref):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM hospital WHERE Reference_No=%s", (ref,))
        conn.commit()
        conn.close()
    except Exception as e:
        print("Error deleting:", e)
    return redirect(url_for('index'))

# --- UPDATED SMART CHAT ROUTE (POWERED BY GOOGLE GEMINI) ---
@app.route('/chat', methods=['POST'])
def chat():
    try:
        req = request.json
        user_text = req.get('message', '')
        context_ref = req.get('context_ref', '')
        
        intent, ref = parse_intent(user_text, context_ref)

        if intent in ["show_patient", "supply", "recommend"] and ref:
            conn = get_db_connection()
            cur = conn.cursor(dictionary=True) 
            cur.execute("SELECT * FROM hospital WHERE Reference_No=%s", (ref,))
            row = cur.fetchone()
            conn.close()

            if row:
                if intent == "show_patient":
                    assigned_doc = row.get('doctor', 'Not Assigned')
                    # UPDATED: Added Disease to display
                    details = (f"<b>👤 Patient Profile:</b><br>Name: {row['patientname']} (DOB: {row['DOB']})<br>"
                               f"Ref: {row['Reference_No']} | NHS: {row['nhsnumber']}<br>"
                               f"<b>🩺 Condition:</b> {row.get('Disease', 'Not Specified')}<br>"
                               f"Address: {row['patientaddress']}<br>"
                               f"<b>👨‍⚕️ Assigned Doctor:</b> {assigned_doc}<br>----------------<br>"
                               f"<b>💊 Prescription:</b><br>Tablet: {row['Nameoftablets']} (Qty: {row['Numbersoftablets']})<br>"
                               f"Dose: {row['dose']} | Daily: {row['dailydose']}<br>Issued: {row['issuedate']} | Exp: {row['expdate']}")
                    tips_html = "<br>".join(get_health_advice(row))
                    return jsonify({"response": details + f"<br><br><b>💡 Health & Safety Advice:</b><br>{tips_html}"})
                
                elif intent == "recommend":
                    tips_html = "<br>".join(get_health_advice(row))
                    return jsonify({"response": f"<b>💡 Advice for {row['patientname']}:</b><br>{tips_html}"})

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
                            except: continue
                            
                        if issue_date:
                            days_passed = (datetime.date.today() - issue_date).days
                            remaining_days = total_days_supply - days_passed
                            
                            if remaining_days <= 0:
                                return jsonify({"response": f"⚠️ Medicine supply for {row['patientname']} has <b>finished</b> (Issued {issue_date_str}).", "ref": row['Reference_No']})
                            else:
                                return jsonify({"response": f"📅 {row['patientname']} has approx <b>{remaining_days} days</b> of medicine left.", "ref": row['Reference_No']})
                        else:
                            return jsonify({"response": f"Total supply: {total_days_supply} days (Issue date unknown).", "ref": row['Reference_No']})
                    except: 
                        return jsonify({"response": "Cannot calculate supply (check dose/qty).", "ref": row['Reference_No']})

        # 2. ASK GEMINI AI
        patient_context = "No specific patient selected from the table."
        if context_ref:
            conn = get_db_connection()
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM hospital WHERE Reference_No=%s", (context_ref,))
            row = cur.fetchone()
            conn.close()
            if row:
                # UPDATED: Added Disease to AI Context
                patient_context = (f"Patient Name: {row['patientname']}, Age: {calculate_age(row['DOB'])}, "
                                   f"Condition: {row.get('Disease', 'Unknown')}, Medicine: {row['Nameoftablets']}, "
                                   f"Dose: {row['dose']}, RefID: {row['Reference_No']}")

        prompt = f"Context: {patient_context}\nUser: {user_text}\nAnswer briefly as a medical assistant."
        ai_response = model.generate_content(prompt)
        bot_reply = ai_response.text.replace("\n", "<br>")
        
        return jsonify({"response": f"🤖 <b>AI:</b> {bot_reply}"})

    except Exception as e:
        print("Error:", e)
        return jsonify({"response": "I'm having trouble connecting to the AI brain right now. Please check your internet connection."}), 500

@app.route('/scan_prescription', methods=['POST'])
def scan_prescription():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files['file']
    
    try:
        img = Image.open(file)
        custom_config = r'--oem 3 --psm 6'
        extracted_text = pytesseract.image_to_string(img, config=custom_config)
        
        data = {"pname": "", "name": "", "raw_text": extracted_text}
        
        for line in extracted_text.split('\n'):
            l = line.lower().strip()
            if "name" in l or "patient" in l:
                cleaned = re.sub(r"(patient|name|:|[^a-zA-Z\s])", "", l, flags=re.IGNORECASE).strip()
                if len(cleaned) > 2: data["pname"] = cleaned.title()
            if any(m in l for m in ["mg", "paracetamol", "aspirin", "tablet", "capsule", "vaccine", "ativan", "dollo"]):
                data["name"] = line.strip()
        
        return jsonify(data)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)