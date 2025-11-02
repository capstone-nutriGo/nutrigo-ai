# src/evaluate.py  (REPLACE)
import pandas as pd
import numpy as np
from pathlib import Path
import joblib
from sklearn.metrics import mean_absolute_error
from src.type_mapping import map_to_type
from src.baselines import get_baseline, NUTS

DATA_DIR = Path("data/processed")
VAL_CSV = DATA_DIR / "val.csv"
MODEL_PATH = Path("models/model.pkl")

def main():
    if not VAL_CSV.exists():
        raise FileNotFoundError("Run src/prepare_data.py first.")
    if not MODEL_PATH.exists():
        raise FileNotFoundError("Run src/train_baseline.py first.")

    Path("reports").mkdir(parents=True, exist_ok=True)

    bundle = joblib.load(MODEL_PATH)
    pipe = bundle["pipeline"]; targets = bundle["targets"]
    text_col = bundle["text_col"]
    feat_num = bundle["feat_num"]; feat_cat = bundle["feat_cat"]

    df = pd.read_csv(VAL_CSV)
    for t in targets:
        df[t] = pd.to_numeric(df[t], errors="coerce")
    mask = df[targets].notna().all(axis=1)
    dropped = len(df) - mask.sum()
    df = df[mask].copy()

    df[text_col] = (df.get("name","").astype(str) + " " + df.get("description","").astype(str)).str.strip()
    df["dish_type"] = [map_to_type(n, c) for n, c in zip(df.get("name",""), df.get("category",""))]

    X = df[feat_num + feat_cat + [text_col]]
    base_arr = np.array([[get_baseline(dt)[t] for t in targets] for dt in df["dish_type"]], dtype=float)

    y_true = df[targets].values.astype(float)
    y_res_pred = pipe.predict(X)
    y_pred = base_arr + y_res_pred

    mae = {t: float(mean_absolute_error(y_true[:,i], y_pred[:,i])) for i,t in enumerate(targets)}
    pd.Series(mae).to_csv("reports/mae.csv", header=False)
    print(f"[val] using {len(df)} rows; dropped {dropped} rows with missing targets.")
    print("MAE by nutrient:")
    for k,v in mae.items():
        print(f"  {k}: {v:.2f}")
    print("Saved reports/mae.csv")

if __name__ == "__main__":
    main()
