# train_model.py
import pandas as pd
from sklearn.tree import DecisionTreeClassifier
import joblib

print("Step 1: Creating training data...")
# We train the model on 4 features: 
# [Age, Daily_Dose, Is_Antibiotic, Is_Painkiller]
# Labels: 0 = Low Risk, 1 = High Risk

# Features: [Age, Dose, Antibiotic?, Painkiller?]
X_train = [
    [25, 1, 0, 1], [30, 2, 0, 1], # Young, low dose = Low Risk (0)
    [65, 3, 1, 0], [75, 4, 1, 0], # Senior, high dose antibiotic = High Risk (1)
    [20, 1, 0, 0], [40, 1, 1, 0], # Standard cases = Low Risk (0)
    [50, 5, 0, 1], [85, 1, 0, 0], # High dose or Very Old = High Risk (1)
    [10, 1, 1, 0], [70, 4, 0, 1]  # Child antibiotic = Low(0), Senior High Painkiller = High(1)
    [45, 1, 0, 0], [55, 2, 0, 0], # Middle-aged, standard meds = Low Risk (0)
    [12, 5, 0, 0], [15, 6, 1, 0], # Kids/Teens, very high dose = High Risk (1)
    [35, 1, 1, 1], [40, 2, 1, 1], # Mixing Antibiotics + Painkillers = High Risk (1)
    [90, 1, 0, 1], [95, 2, 1, 0], # Extreme old age, even low dose = High Risk (1)
    [28, 10, 0, 0],               # Young person, massive overdose = High Risk (1)
    [32, 1, 0, 0]                 # Healthy adult, low dose = Low Risk (0)
]

# The answers (0 = Safe, 1 = Warning Needed)
y_train = [0, 0, 1, 1, 0, 0, 1, 1, 0, 1]

print("Step 2: Training the AI model...")
# Initialize the Decision Tree Classifier
clf = DecisionTreeClassifier()

# Train the model
clf.fit(X_train, y_train)

print("Step 3: Saving the model to 'risk_model.pkl'...")
joblib.dump(clf, 'risk_model.pkl')

print("Success! The AI brain is ready.")