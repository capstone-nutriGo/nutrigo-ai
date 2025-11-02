import pandas as pd
from sklearn.model_selection import train_test_split
from pathlib import Path

RAW_MENU = Path("data/raw/menu.csv")
RAW_NUTR = Path("data/raw/nutrition.csv")
OUT_DIR = Path("data/processed")
OUT_DIR.mkdir(parents=True, exist_ok=True)

def main():
    if not RAW_MENU.exists() or not RAW_NUTR.exists():
        raise FileNotFoundError("Put data/raw/menu.csv and data/raw/nutrition.csv first.")
    menu = pd.read_csv(RAW_MENU)
    nutr = pd.read_csv(RAW_NUTR)
    df = pd.merge(menu, nutr, on="menu_id", how="inner")
    # Basic cleaning
    for col in ["name", "description", "category", "region"]:
        if col in df.columns:
            df[col] = df[col].fillna("")
    if "price" in df.columns:
        df["price"] = df["price"].fillna(df["price"].median())
    # Train/val split
    train_df, val_df = train_test_split(df, test_size=0.2, random_state=42)
    train_df.to_csv(OUT_DIR / "train.csv", index=False)
    val_df.to_csv(OUT_DIR / "val.csv", index=False)
    print(f"Saved {len(train_df)} train and {len(val_df)} val rows to {OUT_DIR}")

if __name__ == "__main__":
    main()