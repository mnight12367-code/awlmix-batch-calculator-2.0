import streamlit as st
import sys
from pathlib import Path
import pandas as pd

# Streamlit Cloud safe import
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from db import get_on_hand_by_location

st.title("Feasibility Check (Inventory vs BOM)")

# ---------- File paths ----------
PRODUCT_MASTER_PATH = ROOT_DIR / "ProductMaster.txt"
BOM_PATH = ROOT_DIR / "ProductMaterialUsage.txt"
WEIGHT_TARGETS_PATH = ROOT_DIR / "ProductWeightTargets.txt"
MATERIAL_MASTER_CSV = ROOT_DIR / "MaterialMaster.csv"


def read_csv_flexible(path: Path) -> pd.DataFrame:
    """Tries common delimiters and returns best result."""
    if not path.exists():
        st.error(f"Missing file: {path.name}")
        st.stop()

    seps = [",", "\t", "|", ";"]
    best_df = None
    best_cols = 0

    for sep in seps:
        try:
            df = pd.read_csv(path, sep=sep, engine="python")
            if df.shape[1] > best_cols:
                best_cols = df.shape[1]
                best_df = df
        except Exception:
            continue

    if best_df is None:
        best_df = pd.read_csv(path, engine="python")

    best_df.columns = [str(c).strip() for c in best_df.columns]
    return best_df


def require_columns(df: pd.DataFrame, required: list, filename: str):
    missing = [c for c in required if c not in df.columns]
    if missing:
        st.error(f"{filename} is missing required columns: {missing}")
        st.write("Detected columns:", list(df.columns))
        st.stop()


# ---------- Load tables ----------
prod_df = read_csv_flexible(PRODUCT_MASTER_PATH)
bom_df = pd.read_csv(BOM_PATH, sep=",", engine="python") 
bom_df.columns = [str(c).strip() for c in bom_df.columns]
wt_df = read_csv_flexible(WEIGHT_TARGETS_PATH)

# Material mapping (MaterialID -> MaterialCode)
mat_id_to_code = {}
if MATERIAL_MASTER_CSV.exists():
    mm = read_csv_flexible(MATERIAL_MASTER_CSV)
    # accept a few common column spellings
    colmap = {c.lower(): c for c in mm.columns}
    if "materialid" in colmap and "materialcode" in colmap:
        mid = colmap["materialid"]
        mcode = colmap["materialcode"]
        mat_id_to_code = dict(zip(mm[mid].astype(str), mm[mcode].astype(str)))

# ---------- Validate schema ----------
require_columns(prod_df, ["ProductID", "ProductCode", "ProductName"], "ProductMaster.txt")
require_columns(bom_df, ["ProductID", "MaterialCode", "Percent"], "ProductMaterialUsage.txt")
require_columns(
    wt_df,
    ["ProductID", "TotalWeightPerUnitLB", "TotalWeightPerUnitG"],
    "ProductWeightTargets.txt"
)

# ---------- UI ----------
prod_df = prod_df.copy()
prod_df["__label"] = prod_df["ProductCode"].astype(str) + " - " + prod_df["ProductName"].astype(str)

product_label = st.selectbox("Product", prod_df["__label"].tolist())
sel = prod_df.loc[prod_df["__label"] == product_label].iloc[0]
product_id = str(sel["ProductID"])
product_code = str(sel["ProductCode"])

c1, c2, c3 = st.columns(3)
with c1:
    units = st.number_input("Units to make", min_value=0.0, step=1.0, value=1.0)
with c2:
    location_code = st.selectbox("Location", ["AWLMIX", "CENTRAL", "F_WAREHOUSE"], index=0)
with c3:
    compare_uom = st.selectbox("Inventory UOM", ["LB"], index=0)  # lock to LB for now

# ---------- Weight target ----------
wt_match = wt_df.loc[wt_df["ProductID"].astype(str) == product_id]
if wt_match.empty:
    st.error(f"No weight target found for ProductID {product_id} ({product_code}).")
    st.stop()

w_lb = pd.to_numeric(wt_match.iloc[0]["TotalWeightPerUnitLB"], errors="coerce")
w_g = pd.to_numeric(wt_match.iloc[0]["TotalWeightPerUnitG"], errors="coerce")

if pd.isna(w_lb) or float(w_lb) <= 0:
    st.error("TotalWeightPerUnitLB is missing or invalid for this product.")
    st.stop()

total_weight_lb = float(units) * float(w_lb)
total_weight_g = float(units) * float(w_g) if not pd.isna(w_g) else None

if total_weight_g is None:
    st.write(f"**Total batch weight:** {total_weight_lb:.4f} LB")
else:
    st.write(f"**Total batch weight:** {total_weight_lb:.4f} LB / {total_weight_g:.2f} G")

# ---------- BOM requirements ----------
bom_rows = bom_df.loc[bom_df["ProductID"].astype(str) == product_id].copy()
if bom_rows.empty:
    st.error(f"No BOM rows found for ProductID {product_id} ({product_code}).")
    st.stop()

# Your "Percent" is a FRACTION (0..1). Do NOT divide by 100.
bom_rows["Frac"] = pd.to_numeric(bom_rows["Percent"], errors="coerce")
bom_rows = bom_rows.dropna(subset=["Frac"])

# MaterialCode in BOM currently appears numeric (MaterialID). Map to OGxxxx using MaterialMaster.csv if possible.
bom_rows["MaterialKey"] = bom_rows["MaterialCode"].astype(str).str.strip()

if mat_id_to_code:
    bom_rows["Material"] = bom_rows["MaterialKey"].apply(lambda k: mat_id_to_code.get(k, k))
else:
    # If no mapping exists, we just use whatever is in BOM
    bom_rows["Material"] = bom_rows["MaterialKey"]

# Required in LB
bom_rows["RequiredLB"] = total_weight_lb * bom_rows["Frac"]
required_df = bom_rows.groupby("Material", as_index=False)["RequiredLB"].sum()

# ---------- On-hand ----------
onhand_df = get_on_hand_by_location(location_code, uom=compare_uom)
if onhand_df.empty:
    onhand_df = pd.DataFrame({"MaterialCode": [], "OnHand": []})

merged = required_df.merge(onhand_df, how="left", left_on="Material", right_on="MaterialCode")
merged["OnHand"] = merged["OnHand"].fillna(0.0)

merged["Shortage"] = (merged["RequiredLB"] - merged["OnHand"]).round(4)
merged["Status"] = merged["Shortage"].apply(lambda x: "FAIL" if x > 0 else "PASS")

# ---------- Output ----------
st.subheader("Feasibility Results (LB)")

out = merged[["Material", "RequiredLB", "OnHand", "Shortage", "Status"]].copy()
out = out.rename(columns={"RequiredLB": "Required (LB)"})
st.dataframe(out, use_container_width=True, hide_index=True)

fails = int((out["Status"] == "FAIL").sum())
if fails == 0:
    st.success("✅ FEASIBLE: Inventory is sufficient for this batch.")
else:
    st.error(f"❌ NOT FEASIBLE: {fails} material(s) are short. See Shortage column.")
    st.caption("Tip: Receive inventory for the missing materials, or reduce units.")


