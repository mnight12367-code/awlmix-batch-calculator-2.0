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

PRODUCT_MASTER_PATH = ROOT_DIR / "ProductMaster.txt"
BOM_PATH = ROOT_DIR / "ProductMaterialUsage.txt"
WEIGHT_TARGETS_PATH = ROOT_DIR / "ProductWeightTargets.txt"

def load_table_flexible(path: Path) -> pd.DataFrame:
    """
    Tries common delimiters and returns the best-looking table.
    """
    if not path.exists():
        st.error(f"Missing file: {path.name}")
        st.stop()

    # Try these separators
    seps = [",", "\t", "|", ";"]
    best_df = None
    best_cols = 0

    for sep in seps:
        try:
            df = pd.read_csv(path, sep=sep, engine="python")
            # Keep the version with the most columns (usually the right delimiter)
            if df.shape[1] > best_cols:
                best_cols = df.shape[1]
                best_df = df
        except Exception:
            pass

    # Final fallback: pandas auto sniff (sometimes works)
    if best_df is None:
        best_df = pd.read_csv(path, engine="python")

    # Clean column names
    best_df.columns = [str(c).strip() for c in best_df.columns]
    return best_df

# Load your files
prod_df = load_table_flexible(PRODUCT_MASTER_PATH)
bom_df = load_table_flexible(BOM_PATH)
wt_df = load_table_flexible(WEIGHT_TARGETS_PATH)

# Show what we loaded (so you never have to guess)
with st.expander("Debug: Show detected columns", expanded=True):
    st.write("**ProductMaster.txt columns:**", list(prod_df.columns))
    st.dataframe(prod_df.head(5), use_container_width=True)

    st.write("**ProductMaterialUsage.txt columns:**", list(bom_df.columns))
    st.dataframe(bom_df.head(5), use_container_width=True)

    st.write("**ProductWeightTargets.txt columns:**", list(wt_df.columns))
    st.dataframe(wt_df.head(5), use_container_width=True)

st.divider()
st.subheader("Step 1: Map your columns (pick from dropdowns)")

# Column mapping UI (you choose)
colA, colB, colC = st.columns(3)

with colA:
    prod_id_col = st.selectbox("ProductMaster: Product ID column", options=prod_df.columns, index=0)
    prod_code_col = st.selectbox("ProductMaster: Product Code column", options=prod_df.columns, index=min(1, len(prod_df.columns)-1))
    prod_name_col = st.selectbox("ProductMaster: Product Name column", options=prod_df.columns, index=min(2, len(prod_df.columns)-1))

with colB:
    bom_prod_id_col = st.selectbox("BOM: Product ID column", options=bom_df.columns, index=0)
    bom_mat_col = st.selectbox("BOM: Material column (MaterialCode or MaterialID)", options=bom_df.columns, index=min(1, len(bom_df.columns)-1))
    bom_pct_col = st.selectbox("BOM: Percent column", options=bom_df.columns, index=min(2, len(bom_df.columns)-1))

with colC:
    wt_prod_id_col = st.selectbox("WeightTargets: Product ID column", options=wt_df.columns, index=0)
    wt_lb_col = st.selectbox("WeightTargets: Weight per unit (LB) column", options=wt_df.columns, index=min(1, len(wt_df.columns)-1))

st.divider()
st.subheader("Step 2: Run feasibility")

# Build product selector
prod_df = prod_df.copy()
prod_df["__label"] = prod_df[prod_code_col].astype(str) + " - " + prod_df[prod_name_col].astype(str)

product_label = st.selectbox("Select Product", options=prod_df["__label"].tolist())
sel = prod_df.loc[prod_df["__label"] == product_label].iloc[0]
product_id = sel[prod_id_col]
product_code = sel[prod_code_col]

c1, c2, c3 = st.columns(3)
with c1:
    units = st.number_input("Units to make", min_value=0.0, step=1.0, value=1.0)
with c2:
    location_code = st.selectbox("Location", ["AWLMIX", "CENTRAL", "F_WAREHOUSE"], index=0)
with c3:
    uom = st.selectbox("Compare UOM", ["LB", "KG", "GAL", "EA"], index=0)

# Weight per unit (LB)
wt_match = wt_df.loc[wt_df[wt_prod_id_col] == product_id]
if wt_match.empty:
    st.error(f"No weight target found for ProductID {product_id}.")
    st.stop()

weight_per_unit_lb = float(pd.to_numeric(wt_match.iloc[0][wt_lb_col], errors="coerce"))
if pd.isna(weight_per_unit_lb) or weight_per_unit_lb <= 0:
    st.error("Weight per unit LB is missing or invalid for this product.")
    st.stop()

total_weight_lb = float(units) * weight_per_unit_lb
st.write(f"**Total batch weight (LB)** = {units:g} × {weight_per_unit_lb:g} = **{total_weight_lb:g} LB**")

if uom != "LB":
    st.info("For now, feasibility matches exact UOM only. Use
