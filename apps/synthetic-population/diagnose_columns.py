"""Raw CES 2024 value distributions for validation outliers: is the synthetic
number a faithful reflection of CES (era/wording drift) or a coding distortion?"""
import pandas as pd

COLS = ["CC24_311a", "CC24_303", "CC24_326a", "CC24_308a_4", "CC24_308a_5",
        "CC24_300_2", "CC24_312i", "pid7"]
df = pd.read_csv("data/raw/ces/ces_2024_common.csv", usecols=COLS, low_memory=False)

for col in COLS[:-1]:
    print(f"\n{col} raw value counts (fraction):")
    print(df[col].value_counts(normalize=True).sort_index().round(3).to_string())

# Cross-tab partisan direction for the suspects: % giving answer 1 by party
df["party3"] = df["pid7"].map(lambda v: "dem" if v in (1, 2, 3) else
                              ("rep" if v in (5, 6, 7) else "ind"))
for col in ["CC24_311a", "CC24_303", "CC24_326a", "CC24_308a_4"]:
    sub = df.dropna(subset=[col])
    frac1 = sub.groupby("party3")[col].apply(lambda s: (s == 1).mean()).round(3)
    print(f"\n{col}: fraction answering 1, by party:\n{frac1.to_string()}")
