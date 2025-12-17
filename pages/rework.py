import streamlit as st
import pandas as pd

from io import BytesIO
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

st.title("AWLMIX Rework to Target (Dynamic)")

st.write("This tool calculates max safe reuse percent, add-backs to target, and exports a PDF batch ticket.")


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


def build_rework_ticket_pdf(plan_df: pd.DataFrame, reuse_pct: float) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)

    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("AWLMIX Batch Ticket - Rework", styles["Title"]))
    story.append(Paragraph("Generated: " + datetime.now().strftime("%Y-%m-%d %H:%M"), styles["Normal"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph(f"<b>Reuse selected:</b> {reuse_pct:.2f}%", styles["Normal"]))
    story.append(Spacer(1, 12))

    pdf_df = plan_df.copy()
    for c in ["Used_from_Rework_g", "Add_Back_g", "Target_g"]:
        if c in pdf_df.columns:
            pdf_df[c] = pd.to_numeric(pdf_df[c], errors="coerce").fillna(0)

    cols = ["Ingredient", "Used_from_Rework_g", "Add_Back_g", "Target_g"]
    table_data = [cols]
    for _, r in pdf_df.iterrows():
        table_data.append([
            str(r.get("Ingredient", "")),
            f"{float(r.get('Used_from_Rework_g', 0)):,.4f}",
            f"{float(r.get('Add_Back_g', 0)):,.4f}",
            f"{float(r.get('Target_g', 0)):,.4f}",
        ])

    t = Table(table_data, hAlign="LEFT", colWidths=[140, 130, 120, 110])
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

    used_sum = float(pdf_df["Used_from_Rework_g"].sum()) if "Used_from_Rework_g" in pdf_df.columns else 0.0
    add_sum = float(pdf_df["Add_Back_g"].sum()) if "Add_Back_g" in pdf_df.columns else 0.0
    tgt_sum = float(pdf_df["Target_g"].sum()) if "Target_g" in pdf_df.columns else 0.0

    story.append(Paragraph(f"<b>Total from rework used:</b> {used_sum:,.4f} g", styles["Normal"]))
    story.append(Paragraph(f"<b>Total add-backs:</b> {add_sum:,.4f} g", styles["Normal"]))
    story.append(Paragraph(f"<b>Target total:</b> {tgt_sum:,.4f} g", styles["Normal"]))

    doc.build(story)
    return buf.getvalue()


def compute_max_safe_fraction(rework: dict, target: dict):
    max_f = float("inf")
    limiting = None
    rows = []

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
    out = []
    for ing in all_ings:
        rw = float(rework.get(ing, 0) or 0)
        tg = float(target.get(ing, 0) or 0)
        used = reuse_fraction * rw
        add = tg - used
        out.append({
            "Ingredient": ing,
            "Rework_g": rw,
            "Target_g": tg,
            "Used_from_Rework_g": used,
            "Add_Back_g": add,
            "Over_Target?": add < -1e-9,
        })
    return pd.DataFrame(out)


materials_loaded = False
codes_list = [""]
name_map = {}

try:
    materials = load_materials_csv("MaterialMaster.csv")
    codes_list = [""] + materials["MaterialCode"].tolist()
    name_map = dict(zip(materials["MaterialCode"], materials["MaterialName"]))
    materials_loaded = True
except Exception as e:
    st.warning("MaterialMaster.csv not found or invalid.")
    st.caption(f"Debug: {e}")


def collect_lines(prefix: str, n: int):
    d = {}
    total = 0.0
    for i in range(int(n)):
        c1, c2 = st.columns([1.3, 1.0])

        with c1:
            if materials_loaded:
                code = st.selectbox(f"{prefix} MaterialCode {i+1}", options=codes_list, key=f"{prefix}_code_{i}")
                nm = name_map.get(code, "") if code else ""
                if nm:
                    st.caption("Name: " + nm)
            else:
                code = st.text_input(f"{prefix} MaterialCode {i+1}", key=f"{prefix}_code_{i}").strip()

        with c2:
            g = st.number_input(f"{code} (g)" if code else f"{prefix} grams", min_value=0.0, step=1.0,
                                format="%.4f", key=f"{prefix}_g_{i}")

        if code:
            d[code] = d.get(code, 0.0) + float(g)
            total += float(g)

    return d, total


with st.sidebar:
    st.header("Settings")
    n_rework = st.number_input("Rework lines", min_value=1, max_value=60, value=4, step=1)
    n_target = st.number_input("Target lines", min_value=1, max_value=60, value=4, step=1)
    mode = st.selectbox("Reuse mode", ["Auto (max safe)", "Manual"], index=0)
    manual_pct = st.number_input("Manual reuse percent", min_value=0.0, max_value=100.0, value=80.0, step=0.5)


st.subheader("1) Rework (Old Batch)")
rework_dict, rework_total = collect_lines("RW", n_rework)
st.write(f"Rework total: {rework_total:,.4f} g")

st.subheader("2) Target (New Batch)")
target_dict, target_total = collect_lines("TG", n_target)
st.write(f"Target total: {target_total:,.4f} g")

st.subheader("3) Results")

if st.button("Calculate rework plan"):
    if rework_total <= 0 or target_total <= 0:
        st.error("Rework and target totals must be greater than zero.")
        st.stop()

    max_f, limiting, limits_df = compute_max_safe_fraction(rework_dict, target_dict)
    safe_pct = min(100.0, max_f * 100)

    c1, c2, c3 = st.columns(3)
    c1.metric("Max safe fraction", f"{max_f:.4f}")
    c2.metric("Max safe percent", f"{safe_pct:.2f}%")
    c3.metric("Limiting ingredient", "None (100% OK)" if max_f >= 1.0 else str(limiting))

    with st.expander("Limiting ratios (Target / Rework)"):
        st.dataframe(limits_df, use_container_width=True)

    reuse_pct = safe_pct if mode == "Auto (max safe)" else manual_pct
    reuse_fraction = reuse_pct / 100.0

    plan_df = compute_plan(rework_dict, target_dict, reuse_fraction)
    st.dataframe(plan_df, use_container_width=True)

    pdf_bytes = build_rework_ticket_pdf(plan_df, reuse_pct)
    st.download_button(
        "Download Rework Batch Ticket (PDF)",
        data=pdf_bytes,
        file_name="AWLMIX_Batch_Ticket_Rework.pdf",
        mime="application/pdf",
    )


