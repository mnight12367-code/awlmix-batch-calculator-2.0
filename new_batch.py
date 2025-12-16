import streamlit as st
import pandas as pd

st.title("Dynamic Batch Ingredient Calculator (grams)")

# ---------- Load materials from CSV ----------
@st.cache_data
def load_materials_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)

    # Clean column names (remove extra spaces)
    df.columns = [c.strip() for c in df.columns]

    # Required columns check
    if "MaterialCode" not in df.columns or "MaterialName" not in df.columns:
        raise ValueError("CSV must contain columns: MaterialCode, MaterialName")

    # Clean values
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
        "Make sure MaterialMaster.csv is in the same folder as this app "
        "and contains columns: MaterialCode, MaterialName."
    )
    st.caption(f"Debug: {e}")

# ---------- Sidebar ----------
with st.sidebar:
    st.header("Settings")
    n = st.number_input("Number of ingredients", min_value=1, max_value=50, value=4, step=1)
    rounding = st.selectbox("Rounding", ["No rounding", "1 g", "0.1 g", "0.01 g"], index=1)

round_step = 0.0 if rounding == "No rounding" else float(rounding.split()[0])

# ---------- Inputs ----------
st.subheader("Batch Formula (RFT)")

selected_codes = []
selected_names = []
old_g = []

for i in range(int(n)):
    col_code, col_weight = st.columns([1.3, 1.0])

    with col_code:
        if materials_loaded:
            code = st.selectbox(
                f"MaterialCode {i+1}",
                options=codes_list,
                key=f"code_{i}"
            )
            name = name_map.get(code, "") if code else ""
            if name:
                st.caption(f"Name: {name}")
        else:
            code = st.text_input(
                f"MaterialCode {i+1}",
                placeholder="e.g. OQ8154",
                key=f"code_{i}"
            )
            name = ""

    with col_weight:
        label = f"{code} (g)" if code else f"Ingredient {i+1} (g)"
        g = st.number_input(
            label,
            min_value=0.0,
            step=1.0,
            format="%.4f",
            key=f"g_{i}"
        )

    selected_codes.append(code if code else f"Ingredient {i+1}")
    selected_names.append(name)
    old_g.append(float(g))

total_g = sum(old_g)
st.write(f"**RFT total:** {total_g:,.4f} g")

new_total = st.number_input(
    "New batch total (g)",
    min_value=0.0,
    value=total_g if total_g > 0 else 0.0,
    step=1.0,
    format="%.4f",
    key="new_total_g"
)

# ---------- Calculate ----------
if st.button("Calculate batch"):
    if total_g <= 0:
        st.error("RFT total must be greater than zero.")
    else:
        ratios = [x / total_g for x in old_g]
        raw = [r * new_total for r in ratios]

        # Rounding + drift correction
        if round_step == 0.0:
            final = raw
        else:
            final = [round(x / round_step) * round_step for x in raw]
            drift = new_total - sum(final)
            biggest_idx = max(range(len(final)), key=lambda i: final[i])
            final[biggest_idx] += drift

        st.subheader("New batch results")

        df = pd.DataFrame({
            "MaterialCode": selected_codes,
            "MaterialName": selected_names,
            "Ratio": [round(r, 10) for r in ratios],
            "New (g)": [round(x, 4) for x in final],
        })

        st.dataframe(df, hide_index=True, use_container_width=True)
        st.write(f"**Check sum:** {sum(final):,.4f} g")

