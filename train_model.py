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