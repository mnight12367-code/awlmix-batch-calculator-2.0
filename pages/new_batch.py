import os
import streamlit as st
import pandas as pd

from io import BytesIO
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

st.title("Dynamic Batch Ingredient Calculator (grams)")

# ---------- PDF helper ----------
def build_batch_ticket_pdf(df: pd.DataFrame, new_total: float, title: str = "AWLMIX Batch Ticket") -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(title, styles["Title"]))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles["Normal"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph(f"<b>Target Total:</b> {float(new_total):,.4f} g", styles["Normal"]))
    story.append(Spacer(1, 12))

    cols = ["MaterialCode", "MaterialName", "Ratio", "New (g)"]
    table_data = [cols] + df[cols].astype(str).values.tolist()

    t = Table(table_data, hAlign="LEFT", colWidths=[90, 230, 80, 90])
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

    check_sum = float(pd.to_numeric(df["New (g)"], errors="coerce").fillna(0).sum())
    story.append(Paragraph(f"<b>Check Sum:</b> {check_sum:,.4f} g", styles["Normal"]))

    story.append(Spacer(1, 14))

    # ---- QC Results (Operator Fill) ----
    story.append(Paragraph("<b>QC Results (Operator Fill)</b>", styles["Normal"]))
    story.append(Spacer(1, 6))

    qc_table = Table(
        [
            ["Last Batch ΔE00 (CIEDE2000):", "__________"],
            ["Last Batch Δa:", "__________"],
            ["Last Batch Δb:", "__________"],
        ],
        hAlign="LEFT",
        colWidths=[220, 220],
    )

    qc_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.whitesmoke, colors.white]),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    story.append(qc_table)

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


# ---------- Reference TXT loaders (optional BOM compare) ----------
@st.cache_data
def load_ref_txt(path: str, cols: list[str]) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame(columns=cols)
    df = pd.read_csv(path, header=None, names=cols)
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].astype(str).str.replace('"', "", regex=False).str.strip()
    return df


@st.cache_data
def load_reference_tables() -> dict[str, pd.DataFrame]:
    ref = {}
    ref["product_master"] = load_ref_txt("ProductMaster.txt", ["ProductID", "ProductCode", "ProductName"])
    ref["usage"] = load_ref_txt("ProductMaterialUsage.txt", ["RowID", "ProductID", "MaterialID", "UsageFraction"])
    ref["units"] = load_ref_txt("ProductUnits.txt", ["RowID", "ProductID", "UnitType"])
    ref["wt"] = load_ref_txt("ProductWeightTargets.txt", ["RowID", "ProductID", "TargetWeightLB", "Notes"])
    ref["material_master_ref"] = load_ref_txt("MaterialMaster.txt", ["MaterialID", "MaterialCode", "MaterialName"])
    return ref


def build_reference_bom(ref: dict[str, pd.DataFrame], product_id: int) -> pd.DataFrame:
    usage = ref["usage"]
    mat = ref["material_master_ref"]

    if usage.empty or mat.empty:
        return pd.DataFrame(columns=["MaterialCode", "MaterialName", "RefPercent"])

    usage = usage.copy()
    usage["ProductID"] = pd.to_numeric(usage["ProductID"], errors="coerce")
    usage = usage[usage["ProductID"] == product_id]

    bom = usage.merge(mat, on="MaterialID", how="left")
    bom["UsageFraction"] = pd.to_numeric(bom["UsageFraction"], errors="coerce").fillna(0.0)
    bom["RefPercent"] = bom["UsageFraction"] * 100.0

    bom = bom.groupby(["MaterialCode", "MaterialName"], as_index=False)["RefPercent"].sum()
    bom = bom.sort_values("RefPercent", ascending=False).reset_index(drop=True)
    return bom


# ---------- Initialize material dropdown ----------
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
        "Make sure MaterialMaster.csv is in the project root and contains columns: MaterialCode, MaterialName."
    )
    st.caption(f"Debug: {e}")


# ---------- Sidebar ----------
with st.sidebar:
    st.header("Settings")

    n = st.number_input("Number of ingredients", min_value=1, max_value=50, value=4, step=1)
    rounding = st.selectbox("Rounding", ["No rounding", "1 g", "0.1 g", "0.01 g"], index=1)

    st.divider()
    st.subheader("Reference (optional)")

    tol_pct = st.slider(
        "Reference tolerance (±%)",
        min_value=0.0,
        max_value=10.0,
        value=0.50,
        step=0.05,
        help="Highlights ingredients where |Manual% - Ref%| is greater than this tolerance."
    )

    ref = load_reference_tables()
    pm = ref["product_master"]
    pu = ref["units"]
    wt = ref["wt"]

    ref_product_id = None

    if pm.empty:
        st.caption("Reference files not found (ProductMaster.txt / ProductMaterialUsage.txt / MaterialMaster.txt).")
    else:
        ref_product_code = st.selectbox(
            "Reference ProductCode",
            options=[""] + pm["ProductCode"].dropna().unique().tolist(),
            index=0
        )

        if ref_product_code:
            ref_product_id = int(pd.to_numeric(
                pm.loc[pm["ProductCode"] == ref_product_code, "ProductID"].iloc[0],
                errors="coerce"
            ))

            unit_options = pu.loc[pu["ProductID"] == ref_product_id, "UnitType"].dropna().unique().tolist()
            _ = st.selectbox("Reference Unit", options=[""] + unit_options, index=0)

            wt_row = wt.loc[wt["ProductID"] == ref_product_id]
            if not wt_row.empty:
                target_lb = float(pd.to_numeric(wt_row["TargetWeightLB"], errors="coerce").fillna(0).iloc[0])
                st.caption(f"Target weight (lb): {target_lb:,.4f}")

round_step = 0.0 if rounding == "No rounding" else float(rounding.split()[0])


# ---------- Inputs ----------
st.subheader("Batch Formula (RFT)")

selected_codes: list[str] = []
selected_names: list[str] = []
old_g: list[float] = []

for i in range(int(n)):
    col_code, col_weight = st.columns([1.3, 1.0])

    with col_code:
        if materials_loaded:
            code = st.selectbox(f"MaterialCode {i+1}", options=codes_list, key=f"code_{i}")
            name = name_map.get(code, "") if code else ""
            if name:
                st.caption(f"Name: {name}")
        else:
            code = st.text_input(f"MaterialCode {i+1}", placeholder="e.g. OQ8154", key=f"code_{i}")
            name = ""

    with col_weight:
        label = f"{code} (g)" if code else f"Ingredient {i+1} (g)"
        g = st.number_input(label, min_value=0.0, step=1.0, format="%.4f", key=f"g_{i}")

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

        # ---- Optional Reference Compare ----
        if ref_product_id:
            bom = build_reference_bom(ref, ref_product_id)

            st.subheader("Reference BOM (advisory)")
            if bom.empty:
                st.info("Reference BOM not available (check MaterialMaster.txt mapping and ProductMaterialUsage.txt).")
            else:
                st.dataframe(bom, use_container_width=True)

                manual_df = pd.DataFrame({"MaterialCode": selected_codes, "Manual_g": final})
                manual_df["Manual_g"] = pd.to_numeric(manual_df["Manual_g"], errors="coerce").fillna(0.0)
                manual_df = manual_df.groupby("MaterialCode", as_index=False)["Manual_g"].sum()

                manual_total = float(manual_df["Manual_g"].sum()) if not manual_df.empty else 0.0
                manual_df["ManualPercent"] = (manual_df["Manual_g"] / manual_total * 100.0) if manual_total > 0 else 0.0

                comp = manual_df.merge(bom[["MaterialCode", "RefPercent"]], on="MaterialCode", how="outer")
                comp["Manual_g"] = pd.to_numeric(comp["Manual_g"], errors="coerce").fillna(0.0)
                comp["ManualPercent"] = pd.to_numeric(comp["ManualPercent"], errors="coerce").fillna(0.0)
                comp["RefPercent"] = pd.to_numeric(comp["RefPercent"], errors="coerce").fillna(0.0)
                comp["DeltaPercent"] = comp["ManualPercent"] - comp["RefPercent"]

                view = comp.sort_values("MaterialCode")[["MaterialCode", "Manual_g", "ManualPercent", "RefPercent", "DeltaPercent"]].copy()
                view["DeltaPercent_num"] = pd.to_numeric(view["DeltaPercent"], errors="coerce").fillna(0.0)

                # Format numeric columns for display
                view["Manual_g"] = view["Manual_g"].map(lambda x: f"{x:,.4f}")
                view["ManualPercent"] = view["ManualPercent"].map(lambda x: f"{x:,.4f}")
                view["RefPercent"] = view["RefPercent"].map(lambda x: f"{x:,.4f}")
                view["DeltaPercent"] = view["DeltaPercent_num"].map(lambda x: f"{x:,.4f}")

                def highlight_oos(row):
                    oos = abs(float(row["DeltaPercent_num"])) > float(tol_pct)
                    return ["font-weight: 700;" if oos else "" for _ in row.index]

                st.subheader("Manual vs Reference (%)")
                st.caption(f"Highlighted when |Delta%| > {tol_pct:.2f}%")

                st.dataframe(
                    view.style.apply(highlight_oos, axis=1),
                    use_container_width=True
                )

        # ---- PDF Download ----
        pdf_bytes = build_batch_ticket_pdf(df, float(new_total), title="AWLMIX Batch Ticket - New Batch")
        st.download_button(
            "Download Batch Ticket (PDF)",
            data=pdf_bytes,
            file_name="AWLMIX_Batch_Ticket_New_Batch.pdf",
            mime="application/pdf"
        )
