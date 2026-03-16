import joblib
import numpy as np
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.path.join(BASE_DIR, 'risk_model.pkl')

risk_model = joblib.load(MODEL_PATH)

def predict_risk(age, dose_val, is_anti, is_pain):
    input_data = np.array([[age, dose_val, is_anti, is_pain]])

    prediction = risk_model.predict(input_data)[0]
    probability = risk_model.predict_proba(input_data)[0][1]


    return prediction, probability



