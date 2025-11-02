# src/train_baseline.py  (REPLACE)
import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.multioutput import MultiOutputRegressor
from xgboost import XGBRegressor
from sklearn.metrics.pairwise import cosine_similarity
import joblib

from src.type_mapping import map_to_type
from src.baselines import get_baseline, NUTS

DATA_DIR = Path("data/processed")
TRAIN_CSV = DATA_DIR / "train.csv"
MODEL_DIR = Path("models")
MODEL_DIR.mkdir(parents=True, exist_ok=True)
MODEL_PATH = MODEL_DIR / "model.pkl"

TARGETS = NUTS  # ["kcal","carb_g","protein_g","fat_g","sodium_mg"]

def main():
    if not TRAIN_CSV.exists():
        raise FileNotFoundError("Run src/prepare_data.py first.")
    df = pd.read_csv(TRAIN_CSV)

    # 숫자로 강제
    for t in TARGETS:
        df[t] = pd.to_numeric(df[t], errors="coerce")

    # 텍스트 결합
    text_col = "text"
    df[text_col] = (df.get("name","").astype(str) + " " + df.get("description","").astype(str)).str.strip()

    # 타입 매핑
    df["dish_type"] = [map_to_type(n, c) for n, c in zip(df.get("name",""), df.get("category",""))]

    # Baseline 만들기 & 잔차 타깃
    base_arr = np.array([[get_baseline(dt)[t] for t in TARGETS] for dt in df["dish_type"]], dtype=float)
    y_true = df[TARGETS].values.astype(float)
    mask = np.isfinite(y_true).all(axis=1)
    df = df.loc[mask].reset_index(drop=True)
    y_true = y_true[mask]
    base_arr = base_arr[mask]

    y_res = y_true - base_arr  # 모델이 학습할 잔차

    # 특징 컬럼
    feat_num = [c for c in ["price"] if c in df.columns]
    feat_cat = [c for c in ["category","region","dish_type"] if c in df.columns]  # dish_type도 원핫에 포함
    X = df[feat_num + feat_cat + [text_col]]

    # 전처리: 문자 n-gram TF-IDF + 원핫
    preprocess = ColumnTransformer(
        transformers=[
            ("txt", TfidfVectorizer(analyzer="char_wb", ngram_range=(2,5), min_df=1, max_features=200000), text_col),
            ("num", "passthrough", feat_num),
            ("cat", OneHotEncoder(handle_unknown="ignore"), feat_cat),
        ],
        remainder="drop"
    )

    base = XGBRegressor(
        n_estimators=600,
        max_depth=8,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_lambda=2.0,
        n_jobs=-1,
        tree_method="hist"
    )

    pipe = Pipeline([
        ("prep", preprocess),
        ("xgb", MultiOutputRegressor(base))
    ])

    pipe.fit(X, y_res)

    # === KNN 폴백용 자료 저장 ===
    # 학습 텍스트의 TF-IDF(문자 ngram) 행렬과 원본 타깃(y_true) 저장
    txt_vec = pipe.named_steps["prep"].named_transformers_["txt"]
    train_texts = df[text_col].tolist()
    X_txt = txt_vec.transform(train_texts)  # sparse
    # 저장 번들
    bundle = {
        "pipeline": pipe,
        "targets": TARGETS,
        "feat_num": feat_num,
        "feat_cat": feat_cat,
        "text_col": text_col,
        "sim_threshold": 0.15,  # 유사도 임계
        "knn_k": 10,
        "train_texts": train_texts,
        "train_X_txt": X_txt,
        "train_y_true": y_true,     # 최종값(잔차X)
    }
    joblib.dump(bundle, MODEL_PATH)
    print(f"Saved model to {MODEL_PATH}")

if __name__ == "__main__":
    main()

