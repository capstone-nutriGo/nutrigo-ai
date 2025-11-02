# 🍱 Menu → Nutrition (XGBoost) — Starter Project

메뉴명(+메타데이터)을 입력하면 100g 기준 영양성분을 예측하는 베이스라인 파이프라인입니다.
문자 n-gram TF-IDF + 요리타입 Baseline + XGBoost 잔차회귀 + KNN 폴백으로 처음 보는 메뉴명도 근사 예측합니다. (선택적으로 1인분 환산 지원)

✨ 핵심 아이디어
- dish_type 매핑 → Baseline(버거/찌개/면/볶음밥 등 타입별 100g 대략값)
- 잔차 회귀: y_res = y_true − Baseline[type]을 MultiOutput XGBoost로 학습
- 문자 n-gram TF-IDF: OOV(처음보는 메뉴명) 완화
- KNN 폴백: 텍스트 유사도 낮을 때, 학습셋 이웃 평균으로 안전 보정
- 1인분 환산(옵션): per_serving = per_100g × (portion_g/100)
---

## 📦 Project Structure
```
ml-menu-nutrition-starter/
├─ data/
│  ├── raw/                # put your CSVs here (menu.csv, nutrition.csv)
│  └─ processed/
│     ├─ train.csv            # 학습 데이터 (내부용)
│     └─ val.csv              # 검증 데이터 (내부용)
├─ models/
│  └─ model.pkl               # 학습된 파이프라인 번들
├─ reports/
│  └─ mae.csv                 # 검증 MAE 리포트
└─ src/
   ├─ __init__.py
   ├─ baselines.py            # 타입별 Baseline 정의
   ├─ evaluate.py             # 검증(MAE 산출)
   ├─ predict_cli.py          # CLI 추론
   ├─ prepare_data.py         # 전처리/병합/분할 (raw→processed)
   ├─ serve_api.py            # (선택) FastAPI 서빙
   ├─ train_baseline.py       # 학습(Residual XGB + TF-IDF)
   └─ type_mapping.py         # 메뉴명→dish_type 규칙 매핑
```
---

## 🗃️ Expected Data

See `data/schema.md` for column definitions. Minimal columns:
- `menu_id` (str/int)
- `name` (str): menu name
- `description` (str, optional)
- `price` (float, optional)
- `category` (str, optional)
- `region` (str, optional)
- Targets (floats): `kcal, carb_g, protein_g, fat_g, sodium_mg`

Place your source files as:
- `data/raw/menu.csv` – contains features (name/description/price/...)
- `data/raw/nutrition.csv` – contains targets per `menu_id`

---

## 🚀 Quickstart

```bash
# 0) (Optional) create venv
python -m venv .venv
source .venv/bin/activate

# 1) Install deps
pip install -r requirements.txt

# 2) Put your CSVs under data/raw/
#    - data/raw/menu.csv
#    - data/raw/nutrition.csv

# 3) Preprocess & split
python src/prepare_data.py
python3 src.prepare_data

# 4) Train baseline
python src/train_baseline.py
python3 -m src.train_baseline

# 5) Evaluate
python src/evaluate.py
python3 -m src.evaluate

# 6) Predict (CLI)
# 100g 기준
python -m src.predict_cli --name "치즈 돈가스" --price 9500 --category "돈가스" --region "서울"
# 1인분 환산(예: 280g)
python -m src.predict_cli --name "치즈 돈가스" --portion_g 280
python src/predict_cli.py --name "치즈 돈가스" --price 9500 --category "돈가스" --region "서울"
python3 -m src.predict_cli --name "치즈 돈가스" --price 9500 --category "돈가스" --region "서울"

# 7) Serve API
uvicorn src.serve_api:app --reload --port 8000
# POST to http://localhost:8000/predict with JSON:
# {"name":"치즈 돈가스","price":9500,"category":"돈가스","region":"서울"}
```

---

## 🧪 What to try next

- Replace TF–IDF with **Sentence-BERT** embeddings (+ PCA) for better generalization.
- Add **options parser** (e.g., "곱빼기", "치즈 추가", size) as binary/ordinal features.
- Train **category-specific models** (e.g., noodle vs. rice vs. dessert).
- Add **uncertainty**: bootstrap ensembles or conformal prediction.
- Split by restaurant (`GroupKFold`) to avoid leakage.