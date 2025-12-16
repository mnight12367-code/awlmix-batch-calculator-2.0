import streamlit as st
import pandas as pd

st.title("AWLMIX Rework → Target Calculator")

st.markdown("""
This tool calculates:
- **Maximum safe reuse %** (so no ingredient ends up over the target)
- **Add-backs** needed to hit the target exactly (by ingredient)
""")

# ----------------------------
# Core logic
# ----------------------------
def compute_max_safe_fraction(rework: dict, target: dict) -> tuple[float, str, pd.DataFrame]:
    """
    Max safe fraction f is the minimum across shared ingredients:
        f <= target_i / rework_i   for all i where rework_i > 0 and target_i is defined.

    Returns:
      (max_f, limiting_ingredient, limits_df)
    """
    rows = []
    max_f = float("inf")
    limiting = None

    shared = sorted(set(rework.keys()) & set(target.keys()))
    for ing in shared:
        rw = float(rework.get(ing, 0) or 0)
        tg = float(target.get(ing, 0) or 0)

        if rw <= 0:
            continue  # doesn't constrain

        f_i = tg / rw
        rows.append({"Ingredient": ing, "Target / Rework": f_i, "Target_g": tg, "Rework_g": rw})

        if f_i < max_f:
            max_f = f_i
            limiting = ing

    limits_df = pd.DataFrame(rows).sort_values("Target / Rework")
    if max_f == float("inf"):
        max_f = 0.0
        limiting = "N/A"

    return max_f, limiting, limits_df


def compute_plan(rework: dict, target: dict, reuse_fraction: float) -> pd.DataFrame:
    """
    For chosen reuse_fraction f:
      used_from_rework_i = f * rework_i
      add_back_i = target_i - used_from_rework_i

    If add_back_i < 0 -> over-target problem (cannot subtract).
    """
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
    # nicer ordering: shared first, then target-only, then rework-only
    df["Type"] = df.apply(
        lambda r: "Shared" if (r["Rework_g"] > 0 and r["Target_g"] > 0)
        else ("Target-only" if r["Target_g"] > 0 else "Rework-only"),
        axis=1
    )
    df = df.sort_values(["Type", "Ingredient"]).reset_index(drop=True)
    return df


# ----------------------------
# Default example (your case)
# NOTE: totals in your message don't match sums; we base math on ingredient lines.
# ----------------------------
default_rework = {
    "OQ8154": 7890,
    "OG7002": 5,
    "OG2001": 25,
    "OG9004": 60,
}
default_target = {
    "OQ8154": 14776,
    "OG7002": 4,
    "OG9004": 180,
    "OG2001": 744,
}

# ----------------------------
# UI: input tables
# ----------------------------
st.subheader("1) Enter Rework (Old Batch) and Target (New Batch)")

col1, col2 = st.columns(2)

with col1:
    st.caption("Rework (Old) - grams by ingredient")
    rw_df = st.data_editor(
        pd.DataFrame([{"Ingredient": k, "Grams": v} for k, v in default_rework.items()]),
        num_rows="dynamic",
        use_container_width=True,
        key="rw_editor"
    )

with col2:
    st.caption("Target (New) - grams by ingredient")
    tg_df = st.data_editor(
        pd.DataFrame([{"Ingredient": k, "Grams": v} for k, v in default_target.items()]),
        num_rows="dynamic",
        use_container_width=True,
        key="tg_editor"
    )

def df_to_dict(df: pd.DataFrame) -> dict:
    d = {}
    for _, row in df.iterrows():
        ing = str(row.get("Ingredient", "")).strip()
        if not ing:
            continue
        grams = row.get("Grams", 0)
        try:
            grams = float(grams)
        except Exception:
            grams = 0.0
        if grams != 0:
            d[ing] = grams
    return d

rework = df_to_dict(rw_df)
target = df_to_dict(tg_df)

# ----------------------------
# Max safe reuse calculation
# ----------------------------
st.subheader("2) Maximum Safe Reuse %")
max_f, limiting_ing, limits_df = compute_max_safe_fraction(rework, target)

c1, c2, c3 = st.columns(3)
c1.metric("Max safe reuse (fraction)", f"{max_f:.4f}")
c2.metric("Max safe reuse (%)", f"{max_f*100:.2f}%")
c3.metric("Limiting ingredient", limiting_ing)

with st.expander("See limiting ratios (Target / Rework) by shared ingredient"):
    st.dataframe(limits_df, use_container_width=True)

# ----------------------------
# Choose reuse %
# ----------------------------
st.subheader("3) Choose reuse % (auto-defaults to max safe)")
use_safe_default = st.checkbox("Use max safe % automatically", value=True)

if use_safe_default:
    reuse_pct = max_f * 100
else:
    reuse_pct = st.number_input("Reuse %", min_value=0.0, max_value=200.0, value=float(max_f * 100), step=0.5)

reuse_fraction = reuse_pct / 100.0

# ----------------------------
# Compute plan
# ----------------------------
st.subheader("4) Rework Plan (Used from Rework + Add-backs)")
plan_df = compute_plan(rework, target, reuse_fraction)

# Summary totals
total_rework_used = plan_df["Used_from_Rework_g"].sum()
total_addbacks = plan_df["Add_Back_g"].sum()
total_target = plan_df["Target_g"].sum()

s1, s2, s3 = st.columns(3)
s1.metric("Total from rework used (g)", f"{total_rework_used:,.2f}")
s2.metric("Total add-backs (g)", f"{total_addbacks:,.2f}")
s3.metric("Target total (g)", f"{total_target:,.2f}")

# Flag over-target issues
over_df = plan_df[plan_df["Over_Target?"] == True]
if not over_df.empty:
    st.error(
        "Over-target detected (negative add-back). "
        "This reuse % is NOT safe because you can’t subtract material.\n"
        f"Reduce reuse % to ≤ {max_f*100:.2f}% (limited by {limiting_ing})."
    )
    st.dataframe(over_df[["Ingredient", "Target_g", "Used_from_Rework_g", "Add_Back_g"]], use_container_width=True)

# Display full plan
st.dataframe(plan_df, use_container_width=True)

# Optional: export CSV
st.download_button(
    "Download plan as CSV",
    data=plan_df.to_csv(index=False).encode("utf-8"),
    file_name="awlmix_rework_plan.csv",
    mime="text/csv"
)
