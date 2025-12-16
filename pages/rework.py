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
        "Put MaterialMaster.csv in the project root and include columns: MaterialCode, MaterialName."
    )
    st.caption(f"Debug: {e}")

# ---------- Core logic ----------
def compute_max_safe_fraction(rework: dict, target: dict):
    rows = []
    max_f = float("inf")
    limiting = None

    shared = sorted(set(rework.keys()) & set(target.keys()))
    for ing in shared:
        rw = float(rework.get(ing, 0) or 0)
        tg = float(target.get(ing, 0) or 0)
        if rw <= 0:
            continue

        f_i = tg / rw
        rows.append({"Ingredient": ing, "Target / Rework": f_i, "Target_g": tg, "Rework_g": rw})

        if f_i < max_f:
            max_f = f_i
            limiting = ing

    limits_df = pd.DataFrame(rows).sort_values("Target / Rework") if rows else pd.DataFrame(
        columns=["Ingredient", "Target / Rework", "Target_g", "Rework_g"]
    )

    if max_f == float("inf"):
        return 0.0, "N/A", limits_df

    return max_f, limiting, limits_df


def compute_plan(rework: dict, target: dict, reuse_fraction: float) -> pd.DataFrame:
    all_ings = sorted(set(rework.keys()) | set(target.keys()))
    rows = []

    for ing in all_ings:
        rw = float(rework.get(ing, 0) or 0)
        tg = float(target.get(ing, 0) or 0)
        used = reuse_fraction * rw
        add = tg - used

        rows.append({
            "Ingredient": ing,
            "Rework_g": rw,
            "Target_g": tg,
            "Used_from_Rework_g": used,
            "Add_Back_g": add,
            "Over_Target?": add < -1e-9
        })

    df = pd.DataFrame(rows)

    df["Type"] = df.apply(
        lambda r: "Shared" if (r["Rework_g"] > 0 and r["Target_g"] > 0)
        else ("Target-only" if r["Target_g"] > 0 else "Rework-only"),
        axis=1
    )
    return df.sort_values(["Type", "Ingredient"]).reset_index(drop=True)


def collect_lines(prefix: str, n: int):
    """
    Returns:
      grams_by_code: dict[str, float]  (duplicates are summed)
      names_by_code: dict[str, str]
      total_grams: float
    """
    grams_by_code = {}
    names_by_code = {}
    total = 0.0

    for i in range(int(n)):
        col_code, col_g = st.columns([1.3, 1.0])

        with col_code:
            if materials_loaded:
                code = st.selectbox(
                    f"{prefix} MaterialCode {i+1}",
                    options=codes_list,
                    key=f"{prefix}_code_{i}"
                )
                name = name_map.get(code, "") if code else ""
                if name:
                    st.caption(f"Name: {name}")
            else:
                code = st.text_input(
                    f"{prefix} MaterialCode {i+1}",
                    placeholder="e.g. OQ8154",
                    key=f"{prefix}_code_{i}"
                ).strip()
                name = ""

        with col_g:
            label = f"{code} (g)" if code else f"{prefix} Ingredient {i+1} (g)"
            g = st.number_input(
                label,
                min_value=0.0,
                step=1.0,
                format="%.4f",
                key=f"{prefix}_g_{i}"
            )

        if code:
            grams_by_code[code] = grams_by_code.get(code, 0.0) + float(g)
            if code not in names_by_code:
                names_by_code[code] = name
            total += float(g)

    return grams_by_code, names_by_code, total


# ---------- Sidebar ----------
with st.sidebar:
    st.header("Settings")
    n_rework = st.number_input("Rework lines", min_value=1, max_value=60, value=4, step=1)
    n_target = st.number_input("Target lines", min_value=1, max_value=60, value=4, step=1)

    st.divider()
    st.caption("Reuse % control")
    mode = st.selectbox("Reuse mode", ["Auto (max safe)", "Manual"], index=0)
    manual_reuse_pct = st.number_input("Manual reuse %", min_value=0.0, max_value=200.0, value=80.0, step=0.5)

# ---------- Inputs ----------
st.subheader("1) Enter Rework (Old Batch)")
rework_dict, rework_names, rework_total = collect_lines("RW", n_rework)
st.write(f"**Rework total:** {rework_total:,.4f} g")

st.subheader("2) Enter Target (New Batch)")
target_dict, target_names, target_total = collect_lines("TG", n_target)
st.write(f"**Target total:** {target_total:,.4f} g")

# ---------- Calculate ----------
st.subheader("3) Results")

if st.button("Calculate rework plan"):
    if rework_total <= 0:
        st.error("Rework total must be greater than zero.")
        st.stop()
    if target_total <= 0:
        st.error("Target total must be greater than zero.")
        st.stop()

    max_f, limiting_ing, limits_df = compute_max_safe_fraction(rework_dict, target_dict)

    c1, c2, c3 = st.columns(3)
    c1.metric("Max safe reuse (fraction)", f"{max_f:.4f}")
    c2.metric("Max safe reuse (%)", f"{max_f*100:.2f}%")
    c3.metric("Limiting ingredient", limiting_ing)

    with st.expander("See limiting ratios (Target / Rework)"):
        st.dataframe(limits_df, use_container_width=True)

    if mode == "Auto (max safe)":
        reuse_pct = max_f * 100
    else:
        reuse_pct = manual_reuse_pct

    reuse_fraction = reuse_pct / 100.0
    st.write(f"**Reuse selected:** {reuse_pct:.2f}%")

    plan_df = compute_plan(rework_dict, target_dict, reuse_fraction)

    total_rework_used = plan_df["Used_from_Rework_g"].sum()
    total_addbacks = plan_df["Add_Back_g"].sum()
    total_target = plan_df["Target_g"].sum()

    s1, s2, s3 = st.columns(3)
    s1.metric("Total from rework used (g)", f"{total_rework_used:,.2f}")
    s2.metric("Total add-backs (g)", f"{total_addbacks:,.2f}")
    s3.metric("Target total (g)", f"{total_target:,.2f}")

    over_df = plan_df[plan_df["Over_Target?"] == True]
    if not over_df.empty:
        st.error(
            "Over-target detected (negative add-back). "
            "This reuse % is NOT safe because you can’t subtract material.\n"
            f"Reduce reuse % to ≤ {max_f*100:.2f}% (limited by {limiting_ing})."
        )
        st.dataframe(over_df[["Ingredient", "Target_g", "Used_from_Rework_g", "Add_Back_g"]], use_container_width=True)

    st.dataframe(plan_df, use_container_width=True)

    st.download_button(
        "Download plan as CSV",
        data=plan_df.to_csv(index=False).encode("utf-8"),
        file_name="awlmix_rework_plan.csv",
        mime="text/csv"
    )

