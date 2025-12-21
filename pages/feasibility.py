import streamlit as st
import sys
from pathlib import Path
import pandas as pd

# Ensure repo root is on Python path (Streamlit Cloud safe)
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from db import get_on_hand_by_location

st.title("Feasibility Check (Inventory vs BOM)")

# ---------- File paths ----------
PRODUCT_MASTER_PATH = ROOT_DIR / "ProductMaster.txt"
BOM_PATH = ROOT_DIR / "ProductMaterialUsage.txt"
WEIGHT_TARGETS_PATH = ROOT_DIR / "ProductWeightTargets.txt"

# ---------- Helpers ----------
def load_table(path: Path) -> pd.DataFrame:
    """
    Loads your .txt tables assuming they are CSV-style with a header row.
    """
    if not path.exists():
        st.error(f"Missing file: {path.name}")
        st.stop()
    try:
        return pd.read_csv(path)
    except Exception:
        # fallback in case the delimiter isn't detected
        return pd.read_csv(path, sep=",", engine="python")

def find_col(df: pd.DataFrame, candidates):
    for c in candidates:
        if c in df.columns:
            return c
    return None

# ---------- Load data ----------
prod_df = load_table(PRODUCT_MASTER_PATH)
bom_df = load_table(BOM_PATH)
wt_df = load_table(WEIGHT_TARGETS_PATH)

# ---------- Detect columns (flexible to your format) ----------
# ProductMaster
prod_id_col = find_col(prod_df, ["ProductID", "ProductId", "ID"])
prod_code_col = find_col(prod_df, ["ProductCode", "Code"])
prod_name_col = find_col(prod_df, ["ProductName", "Name"])

# BOM
bom_prod_id_col = find_col(bom_df, ["ProductID", "ProductId"])
bom_mat_code_col = find_col(bom_df, ["MaterialCode", "Material", "MaterialID", "MaterialId"])
bom_pct_col = find_col(bom_df, ["Percent", "Percentage", "UsagePercent", "PercentOfTotal", "Pct"])

# Weight Targets
wt_prod_id_col = find_col(wt_df, ["ProductID", "ProductId"])
wt_lb_col = find_col(wt_df, ["TotalWeightPerUnitLB", "TotalWeightLB", "WeightPerUnitLB", "TotalLB"])

# ---------- Validate required columns ----------
missing = []
for name, col in [
    ("ProductMaster ProductID", prod_id_col),
    ("ProductMaster ProductCode", prod_code_col),
    ("ProductMaster ProductName", prod_name_col),
    ("BOM ProductID", bom_prod_id_col),
    ("BOM Percent column", bom_pct_col),
    ("WeightTargets ProductID", wt_prod_id_col),
    ("WeightTargets TotalWeightPerUnitLB", wt_lb_col),
]:
    if col is None:
        missing.append(name)

# BOM material code: we need MaterialCode (preferred). If your BOM uses MaterialID, we can upgrade later.
if bom_mat_code_col is None:
    missing.append("BOM MaterialCode (or MaterialID)")

if missing:
    st.error("Feasibility setup needs these columns, but they weren't found:\n\n- " + "\n- ".join(missing))
    st.info("Open your .txt files and confirm the header names. Paste the first header row here and I’ll adjust instantly.")
    st.stop()

# ---------- UI controls ----------
# Build product selector
prod_df = prod_df.copy()
prod_df["__label"] = prod_df[prod_code_col].astype(str) + " - " + prod_df[prod_name_col].astype(str)

product_label = st.selectbox("Select Product", prod_df["__label"].tolist())
selected = prod_df.loc[prod_df["__label"] == product_label].iloc[0]
product_id = selected[prod_id_col]
product_code = selected[prod_code_col]

col1, col2, col3 = st.columns(3)
with col1:
    units = st.number_input("Units to make", min_value=0.0, step=1.0, value=1.0)
with col2:
    location_code = st.selectbox("Location", ["AWLMIX", "CENTRAL", "F_WAREHOUSE"])
with col3:
    uom = st.selectbox("Compare UOM", ["LB", "KG", "GAL", "EA"], index=0)

# Weight per unit (LB)
wt_match = wt_df.loc[wt_df[wt_prod_id_col] == product_id]
if wt_match.empty:
    st.warning(f"No weight target found for ProductID {product_id}. Add it in ProductWeightTargets.txt to enable feasibility.")
    st.stop()

weight_per_unit_lb = float(wt_match.iloc[0][wt_lb_col])
total_weight_lb = units * weight_per_unit_lb

st.write(f"**Total batch weight (LB)** = Units × Weight per unit = **{units:g} × {weight_per_unit_lb:g} = {total_weight_lb:g} LB**")
if uom != "LB":
    st.info("Right now feasibility compares exact UOM only. For best results, use LB until we add UOM conversion (LB↔KG↔GAL).")

# ---------- Build required materials from BOM ----------
bom_rows = bom_df.loc[bom_df[bom_prod_id_col] == product_id].copy()
if bom_rows.empty:
    st.error(f"No BOM rows found for product {product_code} (ProductID {product_id}). Check ProductMaterialUsage.txt.")
    st.stop()

# Percent to fraction
bom_rows["__pct"] = pd.to_numeric(bom_rows[bom_pct_col], errors="coerce")
bom_rows = bom_rows.dropna(subset=["__pct"])

# Required in LB (for now)
bom_rows["RequiredLB"] = total_weight_lb * (bom_rows["__pct"] / 100.0)

# Material identifier
# If BOM has MaterialCode, use it. If it has numeric MaterialID, it will still display but won't match inventory until we map it.
bom_rows["MaterialKey"] = bom_rows[bom_mat_code_col].astype(str)

required_df = bom_rows[["MaterialKey", "RequiredLB"]].groupby("MaterialKey", as_index=False).sum()

# ---------- Pull on-hand from SQLite ----------
onhand_df = get_on_hand_by_location(location_code, uom=uom)
if onhand_df.empty:
    st.warning(f"No inventory found in SQLite for Location={location_code} and UOM={uom}.")
    onhand_df = pd.DataFrame({"MaterialCode": [], "OnHand": []})

# ---------- Merge + compute status ----------
# Attempt to match MaterialKey to MaterialCode
merged = required_df.merge(
    onhand_df,
    how="left",
    left_on="MaterialKey",
    right_on="MaterialCode"
)

merged["OnHand"] = merged["OnHand"].fillna(0.0)
merged["Shortage"] = (merged["RequiredLB"] - merged["OnHand"]).round(4)
merged["Status"] = merged["Shortage"].apply(lambda x: "FAIL" if x > 0 else "PASS")

# Show results
st.subheader("Feasibility Results")
show = merged[["MaterialKey", "RequiredLB", "OnHand", "Shortage", "Status"]].copy()
show = show.rename(columns={"MaterialKey": "Material", "RequiredLB": f"Required ({uom})"})
st.dataframe(show, use_container_width=True, hide_index=True)

fails = (show["Status"] == "FAIL").sum()
if fails == 0:
    st.success("✅ FEASIBLE: Inventory is sufficient for this batch.")
else:
    st.error(f"❌ NOT FEASIBLE: {fails} material(s) are short. See Shortage column.")
