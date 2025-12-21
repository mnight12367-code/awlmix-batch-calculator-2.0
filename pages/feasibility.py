import streamlit as st
import sys
from pathlib import Path
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from db import get_on_hand_by_location

st.title("Feasibility Check (Inventory vs BOM)")

PRODUCT_MASTER_PATH = ROOT_DIR / "ProductMaster.txt"
BOM_PATH = ROOT_DIR / "ProductMaterialUsage.txt"
WEIGHT_TARGETS_PATH = ROOT_DIR / "ProductWeightTargets.txt"


def load_table_flexible(path: Path) -> pd.DataFrame:
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


prod_df = load_table_flexible(PRODUCT_MASTER_PATH)
bom_df = load_table_flexible(BOM_PATH)
wt_df = load_table_flexible(WEIGHT_TARGETS_PATH)

st.subheader("Detected columns")
st.write("ProductMaster.txt:", list(prod_df.columns))
st.write("ProductMaterialUsage.txt:", list(bom_df.columns))
st.write("ProductWeightTargets.txt:", list(wt_df.columns))

st.info("If you see the columns listed above, the SyntaxError is fixed. Next we’ll add the dropdown mapping back safely.")
