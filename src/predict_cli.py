# src/predict_cli.py  (REPLACE)
import argparse, numpy as np, pandas as pd, joblib
from sklearn.metrics.pairwise import cosine_similarity
from src.type_mapping import map_to_type
from src.baselines import get_baseline, NUTS

MODEL_PATH = "models/model.pkl"

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--name", required=True)
    p.add_argument("--description", default="")
    p.add_argument("--price", type=float, default=None)
    p.add_argument("--category", default=None)  # 입력 카테고리
    p.add_argument("--region", default=None)
    p.add_argument("--portion_g", type=float, default=None)  # 1인분 환산용 (선택)
    args = p.parse_args()

    bundle = joblib.load(MODEL_PATH)
    pipe = bundle["pipeline"]; targets = bundle["targets"]; text_col = bundle["text_col"]
    feat_num = bundle["feat_num"]; feat_cat = bundle["feat_cat"]
    txt_vec = pipe.named_steps["prep"].named_transformers_["txt"]
    train_texts = bundle["train_texts"]
    train_X_txt = bundle["train_X_txt"]
    train_y_true = bundle["train_y_true"]
    sim_th = float(bundle.get("sim_threshold", 0.15))
    knn_k = int(bundle.get("knn_k", 10))

    # dish type & baseline
    dish_type = map_to_type(args.name, args.category or "")
    base = get_baseline(dish_type)

    # model residual prediction
    row = pd.DataFrame([{
        text_col: f"{args.name} {args.description}".strip(),
        "price": args.price,
        "category": args.category,
        "region": args.region,
        "dish_type": dish_type
    }])
    y_res = pipe.predict(row)[0]
    model_pred = {t: float(base[t] + y_res[i]) for i,t in enumerate(targets)}

    # KNN fallback by text similarity (문자 n-gram 공간)
    q_vec = txt_vec.transform([row[text_col].iloc[0]])
    sims = cosine_similarity(q_vec, train_X_txt).ravel()
    max_sim = float(sims.max()) if sims.size else 0.0
    if max_sim < sim_th:
        # 유사도가 너무 낮으면 이웃 평균 사용
        nn_idx = sims.argsort()[::-1][:knn_k]
        nn_mean = train_y_true[nn_idx].mean(axis=0)
        final = {t: float(nn_mean[i]) for i,t in enumerate(targets)}
        used = "knn_fallback"
    else:
        final = model_pred
        used = "model"

    # 1인분 환산(선택)
    if args.portion_g:
        scale = args.portion_g / 100.0
        final_serv = {t: float(final[t] * scale) for t in targets}
        print({
            "dish_type": dish_type,
            "used": used,
            "max_sim": round(max_sim, 3),
            "per_100g": final,
            "per_serving": {"portion_g": args.portion_g, **final_serv}
        })
    else:
        print({
            "dish_type": dish_type,
            "used": used,
            "max_sim": round(max_sim, 3),
            **final
        })

if __name__ == "__main__":
    main()
