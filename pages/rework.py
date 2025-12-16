import streamlit as st
import pandas as pd

st.title("AWLMIX Rework → Target (Dynamic)")

st.markdown("""
This tool calculates:
- **Maximum safe reuse %** (so no ingredient ends up over the target)
- **Add-backs** needed to hit the target exactly
""")

# ---------- Load materials from CSV ----------
@st.cache_data
def load_materials_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]

    if "MaterialCode" not in df.columns or "MaterialName" not in df.columns:
        raise ValueError("CSV must contain columns: MaterialCode, MaterialName")

    df["MaterialCode"] = df["MaterialCode"].astype(str).str.strip()
    df["MaterialName"] = df["MaterialName"].astype(str).str.strip()

    df = df.dropna(subset=["MaterialCode"])
    df = df.drop_duplicates(subset=["MaterialCode"]).sort_values("MaterialCode")
    return df


materials_loaded = False
codes_list = [""]
name_map = {}

try:
    materials = load_materials_csv("MaterialMaster.csv")
    codes_list = [""] + materials["MaterialCode"].tolist()
    name_map = dict(zip(materials["MaterialCode"], materials["MaterialName"]))
    materials_loaded = True
except Exception as e:
    st.warning(
        "MaterialMaster.csv not found or invalid. "
        "Put MaterialMaster.csv in the project root with columns: MaterialCode, MaterialName."
    )
    st.caption(f"Debug: {e}")

# ---------- Core logic ----------
def compute_max_safe_fraction(rework: dict, target: dict):
    rows = []
    max_f = float("inf")
    limiting = None

    shared = sorted(set(rework.keys()) & set(tar

