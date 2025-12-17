import streamlit as st
import pandas as pd

from io import BytesIO
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

st.title("AWLMIX Rework → Target (Dynamic)")

st.markdown("""
This tool calculates:
- **Maximum safe reuse %** (so no ingredient ends up over the target)
- **Add-backs** needed to hit the target exactly
- **Batch Ticket PDF** export
""")


# ---------- PDF helper ----------
def build_rework_ticket_pdf(plan_df: pd.DataFrame, reuse_pct: float, title: str = "AWLMIX Batch Ticket - Rework") -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)

    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(title, styles["Title"]))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles["Normal"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph(f"<b>Reuse selected:</b> {reuse_pct:.2f}%", styles["Normal"]))
    story.append(Spacer(1, 12))

    pdf_df = plan_df.copy()
    # Format numbers for display
    for c in ["Rework_g", "Target_g", "Used_from_Rework_g", "Add_Back_g"]:
        if c in pdf_df.columns:
            pdf_df[c] = pd.to_numeric(pdf_df[c], errors="coerce").fillna(0).map(lambda x: f"{x:,.4f}")

    cols = ["Ingredient", "Used_from_Rework_g", "Add_Back_g", "Target_g"]
    cols = [c for c in cols if c in pdf_df.columns]

    table_data = [cols] + pdf_df[cols].astype(str).values.tolist()

    t = Table(table_data, hAlign="LEFT", colWidths=[120, 130, 120, 110])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
    ]))

    story.append(t)
    story.append(Spacer(1, 12))

    used_sum = float(pd.to_numeric(plan_df.get("Used_from_Rework_g", 0), errors="coerce").fillna(0).sum())
    add_sum = float(pd.to_numeric(plan_df.get("Add_Back_g", 0), errors="coerce").fillna(0).sum())
    tgt_sum = float(pd.to_numeric(plan_df.get("Target_g", 0), errors="coerce").fillna(0).sum())

    story.append(Paragraph(f"<b>Total from rework used:</b> {used_sum:,.4f} g", styles["Normal"]))
    story.append(Paragraph(f"<b>Total add-backs:</b> {add_sum:,.4f} g", styles["Normal"]))
    story.append(Paragraph(f"<b>Target total:</b> {tgt_sum:,.4f} g", styles["Normal"]))

    doc.build(story)
    return buf.getvalue()


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

    limits_df = (
        pd.DataFrame(rows).sort_values("Target / Rework")
        if rows else
        pd.DataFrame(columns=["Ingredient", "Target / Rework", "Target_g", "Rework_g"])
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
    grams_by_code = {}
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
            total += float(g)

    return grams_by_code, total


# ---------- Sidebar ----------
with st.sidebar:
    st.header("Settings")
    n_rework = st.number_input("Rework lines", min_value=1, max_value=60, value=4, step=1)
    n_target = st.number_input("Target lines", min_value=1, max_value=60, value=4, step=1)

    st.divider()
    mode = st.selectbox("Reuse mode", ["Auto (max safe)", "Manual"], index=0)
    manual_reuse_pct = st.number_input("Manual reuse %", min_value=0.0, max_value=100.0, value=80.0, step=0.5)


# ---------- Inputs ----------
st.subheader("1) Enter Rework (Old Batch)")
rework_dict, rework_total = collect_lines("RW", n_rework)
st.write(f"**Rework total:** {rework_total:,.4f} g")

st.subheader("2) Enter Target (New Batch)")
target_dict, target_total = collect_lines("TG", n_target)
st.write(f"**Target total:** {target_total:,.4f} g")


# ---------- Calculate ----------
st.subheader("3) Results")

if st.button("
