# Data Schema (Minimal)

## data/raw/menu.csv
- `menu_id` (str/int) — unique id
- `name` (str) — menu name
- `description` (str, optional)
- `price` (float, optional)
- `category` (str, optional) — e.g., "치킨", "피자", "돈가스"
- `region` (str, optional) — e.g., "서울", "부산"

## data/raw/nutrition.csv
- `menu_id`
- `kcal` (float)
- `carb_g` (float)
- `protein_g` (float)
- `fat_g` (float)
- `sodium_mg` (float)

Notes:
- Join key is `menu_id`.
- You may add more targets (sugar_g, etc.) and list them in `TARGETS` inside scripts.