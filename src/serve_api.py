from fastapi import FastAPI
import pandas as pd
import joblib

app = FastAPI(title="Menu → Nutrition API")

bundle = joblib.load("models/model.pkl")
pipe = bundle["pipeline"]
targets = bundle["targets"]
text_col = bundle["text_col"]

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/predict")
def predict(item: dict):
    row = pd.DataFrame([{
        text_col: f"{item.get('name','')} {item.get('description','')}".strip(),
        "price": item.get("price"),
        "category": item.get("category"),
        "region": item.get("region")
    }])
    pred = pipe.predict(row)[0]
    return {t: float(v) for t, v in zip(targets, pred)}