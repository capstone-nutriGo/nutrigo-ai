# src/type_mapping.py
import re

def norm(s: str) -> str:
    return (s or "").strip().lower()

def map_to_type(name: str, category: str) -> str:
    n = norm(name)
    c = norm(category)

    # burger
    if any(k in n for k in ["버거","와퍼","햄버거","치즈버거"]) or "burger" in n:
        return "burger"

    # fried rice / rice dishes
    if any(k in n for k in ["볶음밥","비빔밥","덮밥","카레밥","김치볶음밥"]):
        return "fried_rice"

    # stew/soup
    if any(k in n for k in ["찌개","탕","국","전골"]) or any(k in c for k in ["국","탕","찌개"]):
        return "stew"

    # noodle/pasta/ramen
    if any(k in n for k in ["라면","라멘","우동","국수","칼국수","쌀국수","파스타","짜장","짬뽕","비빔면"]):
        return "noodle"

    # cutlet/tonkatsu
    if any(k in n for k in ["돈가스","돈까스","가츠","카츠"]):
        return "cutlet"

    # kimbap
    if "김밥" in n:
        return "kimbap"

    # chicken
    if any(k in n for k in ["치킨","닭강정","후라이드","양념치킨","순살치킨"]):
        return "chicken"

    # pizza
    if "피자" in n:
        return "pizza"

    # dessert & beverage (간략)
    if any(k in n for k in ["디저트","케이크","케익","마카롱","쿠키","빵","케익","롤케이크","도넛","도너츠"]):
        return "dessert"
    if any(k in n for k in ["주스","에이드","라떼","커피","스무디","음료","콜라","사이다"]):
        return "beverage"

    # 카테고리에서 힌트 (없으면 general)
    if any(k in c for k in ["버거","와퍼"]): return "burger"
    if any(k in c for k in ["볶음밥","비빔밥","덮밥"]): return "fried_rice"
    if any(k in c for k in ["찌개","탕","국","전골"]): return "stew"
    if any(k in c for k in ["면","라면","우동","국수","파스타"]): return "noodle"
    if any(k in c for k in ["돈가스","돈까스"]): return "cutlet"
    if "김밥" in c: return "kimbap"
    if "피자" in c: return "pizza"
    if "치킨" in c: return "chicken"

    return "general"
