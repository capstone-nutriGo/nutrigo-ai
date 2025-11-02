# src/baselines.py
from typing import Dict

# 100g 기준 대략값(앵커). 필요시 조정하세요.
BASELINE: Dict[str, Dict[str, float]] = {
    "burger":     {"kcal": 250, "carb_g": 24, "protein_g": 12, "fat_g": 15, "sodium_mg": 450},
    "fried_rice": {"kcal": 190, "carb_g": 26, "protein_g": 4,  "fat_g": 6,  "sodium_mg": 420},
    "stew":       {"kcal":  80, "carb_g":  4, "protein_g": 4,  "fat_g": 3,  "sodium_mg": 370},
    "noodle":     {"kcal": 110, "carb_g": 20, "protein_g": 4,  "fat_g": 2,  "sodium_mg": 400},
    "cutlet":     {"kcal": 240, "carb_g": 18, "protein_g":16,  "fat_g":14,  "sodium_mg": 400},
    "kimbap":     {"kcal": 180, "carb_g": 26, "protein_g": 6,  "fat_g": 5,  "sodium_mg": 500},
    "pizza":      {"kcal": 250, "carb_g": 28, "protein_g":11,  "fat_g":11,  "sodium_mg": 530},
    "chicken":    {"kcal": 240, "carb_g":  6, "protein_g":22,  "fat_g":14,  "sodium_mg": 450},
    "dessert":    {"kcal": 280, "carb_g": 42, "protein_g": 4,  "fat_g":12,  "sodium_mg": 130},
    "beverage":   {"kcal":  45, "carb_g": 11, "protein_g": 0,  "fat_g": 0,  "sodium_mg": 10},
    "general":    {"kcal": 150, "carb_g": 18, "protein_g": 6,  "fat_g": 5,  "sodium_mg": 250},
}

NUTS = ["kcal","carb_g","protein_g","fat_g","sodium_mg"]

def get_baseline(dish_type: str) -> Dict[str, float]:
    return BASELINE.get(dish_type, BASELINE["general"]).copy()
