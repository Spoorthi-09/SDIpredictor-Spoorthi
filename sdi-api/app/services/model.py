import os
import numpy as np
from joblib import load

MODEL_PATH = os.getenv("MODEL_PATH", "app/services/model.pkl")

class DummyModel:
    def predict(self, X):
        # constant stub for demo; replace with real model.pkl later
        return np.full(shape=(len(X),), fill_value=1000.0)

def load_model():
    try:
        return load(MODEL_PATH)
    except Exception as e:
        print(f"⚠️ Model load failed ({e}); using DummyModel")
        return DummyModel()

pipe = load_model()
