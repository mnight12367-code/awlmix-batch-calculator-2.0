# pages/new_batch.py
import os
from io import BytesIO
from datetime import datetime

import streamlit as st
import pandas as pd

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle


st.title("New Batch (Manual) — AWLMIX")


# =========================
# Helpers: file loaders
# =========================
@st.cache_data
def load_materials_csv(path: str = "MaterialMaster.csv") -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame(columns=["MaterialCode", "MaterialName"])

    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]

    if "MaterialCode" not in df.columns or "MaterialName" not in df.columns:
        return pd.DataFrame(columns=["MaterialCode", "MaterialName"])

    df["MaterialCode"] = df["MaterialCode"].astype(str).str.strip()
    df["MaterialName"] = df["MaterialName"].astype(str).str.strip()
    df = df.dropna(subset=["MaterialCode"]).drop_duplicates(subset=["MaterialCode"])
    return df.sort_values("MaterialCode").reset_index(drop=True)


@st.cache_data
def load_ref_txt(path: str, cols: list[str]) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame(columns=cols)

    df = pd.read_csv(path, header=None, names=cols, quotechar='"', skipinitialspace=True)
    # Clean strings
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].astype(str).str.replace('"', "", regex=False).str.strip()
    return df


@st.cache_data
def load_product_weight_targets(path: str = "ProductWeightTargets.txt") -> pd.DataFrame:
    # RowID, ProductID, "UnitType", TargetWeightLB, TargetWeightG
    if not os.path.exists(path):
        return pd.DataFrame(columns=["RowID", "ProductID", "UnitType", "TargetWeightLB", "TargetWeightG"])

    df = pd.read_csv(
        path,
        header=None,
        names=["RowID", "ProductID", "UnitType", "TargetWeightLB", "TargetWeightG"],
        quotechar='"',
        skipinitialspace=True,
    )
    df["ProductID"] = pd.to_numeric(df["ProductID"], errors="coerce")
    df["UnitType"] = df["UnitType"].astype(str).str.replace('"', "", regex=False).str.strip()
    df["TargetWeightLB"] = pd.to_numeric(df["TargetWeightLB"], errors="coerce")
    df["TargetWeightG"] = pd.to_numeric(df["TargetWeightG"], errors="coerce")
    return df.dropna(subset=["ProductID", "UnitType"]).reset_index(drop=True)


@st.cache_data
def load_packaging_master(path: str = "PackagingMaster.txt") -> pd.DataFrame:
    """
    Expected format (no header):
    RowID, ProductID, "LabelUPC", "CaseUPC", "PackDescription", "PackageCode"
    """
    if not os.path.exists(path):
        return pd.DataFrame(columns=["RowID", "ProductID", "LabelUPC", "CaseUPC", "PackDescription", "PackageCode"])

    df = pd.read_csv(
        path,
        header=None,
        names=["RowID", "ProductID", "LabelUPC", "CaseUPC", "PackDescription", "PackageCode"],
        quotechar='"',
        skipinitialspace=True,
    )
    df["ProductID"] = pd.to_numeric(df["ProductID"], errors="coerce")
    for c in ["LabelUPC", "CaseUPC", "PackDescription", "PackageCode"]:
        df[c] = df[c].astype(str).str.replace('"', "", regex=False).str.strip()
    return df.dropna(subset=["ProductID"]).reset_index(drop=True)


@st.cache_data
def load_reference_tables() -> dict[str, pd.DataFrame]:
    """
    ProductMaterialUsage is advisory only.
    """
    ref = {
        "product_master": load_ref_txt("ProductMaster.txt", ["ProductID", "ProductCode", "ProductName"]),
        "usage": load_ref_txt("ProductMaterialUsage.txt", ["RowID", "ProductID", "MaterialID", "UsageFraction"]),
        "units": load_ref_txt("ProductUnits.txt", ["RowID", "ProductID", "UnitType"]),
        "material_master_ref": load_ref_txt("MaterialMaster.txt", ["MaterialID", "MaterialCode", "MaterialName"]),
    }

    # numeric casts where needed
    if not ref["product_master"].empty:
        ref["product_master"]["ProductID"] = pd.to_numeric(ref["product_master"]["ProductID"], errors="coerce")
        ref["product_master"] = ref["product_master"].dropna(subset=["ProductID"])

    if not ref["usage"].empty:
        ref["usage"]["ProductID"] = pd.to_numeric(ref["usage"]["ProductID"], errors="coerce")
        ref["usage"]["MaterialID"] = pd.to_numeric(ref["usage"]["MaterialID"], errors="coerce")
        ref["usage"]["UsageFraction"] = pd.to_numeric(ref["usage"]["UsageFraction"], errors="coerce")

    if not ref["units"].empty:
        ref["units"]["ProductID"] = pd.to_numeric(ref["units"]["ProductID"], errors="coerce")
        ref["units"]["UnitType"] = ref["units"]["UnitType"].astype(str).str.strip()

    if not ref["material_master_ref"].empty:
        ref["material_master_ref"]["MaterialID"] = pd.to_numeric(ref["material_master_ref"]["MaterialID"], errors="coerce")
        ref["material_master_ref"]["MaterialCode"] = ref["material_master_ref"]["MaterialCode"].astype(str).str.strip()
        ref["material_master_ref"]["MaterialName"] = ref["material_master_ref"]["MaterialName"].astype(str).str.strip()

    return ref


def build_reference_bom(ref: dict[str, pd.DataFrame], product_id: int) -> pd.DataFrame:
    usage = ref.get("usage", pd.DataFrame())
    mat = ref.get("material_master_ref", pd.DataFrame())

    if usage.empty or mat.empty:
        return pd.DataFrame(columns=["MaterialCode", "MaterialName", "RefPercent"])

    u = usage.copy()
    u = u[u["ProductID"] == product_id].copy()
    if u.empty:
        return pd.DataFrame(columns=["MaterialCode", "MaterialName", "RefPercent"])

    bom = u.merge(mat, on="MaterialID", how="left")
    bom["UsageFraction"] = pd.to_numeric(bom["UsageFraction"], errors="coerce").fillna(0.0)
    bom["RefPercent"] = bom["UsageFraction"] * 100.0

    bom = (
        bom.groupby(["MaterialCode", "MaterialName"], as_index=False)["RefPercent"]
        .sum()
        .sort_values("RefPercent", ascending=False)
        .reset_index(drop=True)
    )
    return bom


# =========================
# PDF builder
# =========================
def build_batch_ticket_pdf(
    df: pd.DataFrame,
    new_total_g: float,
    title: str,
    product_code: str | None = None,
    unit_type: str | None = None,
    target_lb: float | None = None,
    packaging: dict | None = None,
) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()
    story: list = []

    story.append(Paragraph(title, styles["Title"]))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles["Normal"]))
    story.append(Spacer(1, 10))

    meta_lines = []
    if product_code:
        meta_lines.append(f"<b>Product:</b> {product_code}")
    if unit_type:
        meta_lines.append(f"<b>Unit:</b> {unit_type}")
    if target_lb is not None:
        meta_lines.append(f"<b>Target Weight:</b> {target_lb:,.4f} lb")
    meta_lines.append(f"<b>Batch Total:</b> {float(new_total_g):,.2f} g")

    for line in meta_lines:
        story.append(Paragraph(line, styles["Normal"]))
    story.append(Spacer(1, 10))

    # Ingredient table
    cols = ["MaterialCode", "MaterialName", "Ratio", "New (g)"]
    safe = df.copy()
    for c in cols:
        if c not in safe.columns:
            safe[c] = ""

    table_data = [cols] + safe[cols].astype(str).values.tolist()
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
    story.append(Spacer(1, 10))

    check_sum = float(pd.to_numeric(safe["New (g)"], errors="coerce").fillna(0).sum())
    story.append(Paragraph(f"<b>Check Sum:</b> {check_sum:,.2f} g", styles["Normal"]))
    story.append(Spacer(1, 12))

    # Packaging section (replaces QC)
    if packaging:
        story.append(Paragraph("<b>Packaging</b>", styles["Normal"]))
        story.append(Spacer(1, 6))

        pack_table = Table(
            [
                ["Package Code:", str(packaging.get("PackageCode", ""))],
                ["Pack Description:", str(packaging.get("PackDescription", ""))],
                ["Label UPC:", str(packaging.get("LabelUPC", ""))],
                ["Case UPC:", str(packaging.get("CaseUPC", ""))],
            ],
            hAlign="LEFT",
            colWidths=[140, 300],
        )
        pack_table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.whitesmoke, colors.white]),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(pack_table)

    doc.build(story)
    return buf.getvalue()


# =========================
# Data: Material dropdown
# =========================
materials = load_materials_csv("MaterialMaster.csv")
materials_loaded = not materials.empty
codes_list = [""] + (materials["MaterialCode"].tolist() if materials_loaded else [])
name_map = dict(zip(materials["MaterialCode"], materials["MaterialName"])) if materials_loaded else {}


# =========================
# Sidebar: Settings + Reference
# =========================
ref = load_reference_tables()
pm = ref["product_master"]
pu = ref["units"]
wt = load_product_weight_targets("ProductWeightTargets.txt")
pkg = load_packaging_master("PackagingMaster.txt")

with st.sidebar:
    st.header("Settings")
    n = st.number_input("Number of ingredients", min_value=1, max_value=60, value=4, step=1)
    rounding = st.selectbox("Rounding", ["No rounding", "1 g", "0.1 g", "0.01 g"], index=1)

    st.divider()

    ref_product_id = None
    ref_product_code = ""
    selected_unit = ""
    target_lb = None
    target_g = None

    if pm.empty:
        st.caption("Reference tables not found (ProductMaster.txt / ProductUnits.txt / etc.).")
    else:
        ref_product_code = st.selectbox(
            "Reference ProductCode",
            options=[""] + sorted(pm["ProductCode"].dropna().unique().tolist()),
            index=0
        )

        if ref_product_code:
            ref_product_id = int(pd.to_numeric(
                pm.loc[pm["ProductCode"] == ref_product_code, "ProductID"].iloc[0],
                errors="coerce"
            ))

            unit_options = (
                pu.loc[pu["ProductID"] == ref_product_id, "UnitType"]
                .dropna()
                .astype(str)
                .str.strip()
                .unique()
                .tolist()
            )
            selected_unit = st.selectbox("Reference Unit", options=[""] + sorted(unit_options), index=0)

            if selected_unit:
                wt_row = wt[(wt["ProductID"] == ref_product_id) & (wt["UnitType"] == selected_unit)]
                if wt_row.empty:
                    st.warning("No target weight found for this Product + Unit.")
                else:
                    target_lb = float(wt_row["TargetWeightLB"].iloc[0])
                    target_g = float(wt_row["TargetWeightG"].iloc[0])
                    st.caption(f"Target weight: {target_lb:,.4f} lb | {target_g:,.2f} g ({selected_unit})")

            # Packaging dropdown (driven by ProductID)
            st.subheader("Packaging (optional)")
            selected_pkg = None
            if not pkg.empty and ref_product_id is not None:
                pkg_opts = pkg[pkg["ProductID"] == ref_product_id].copy()
                if pkg_opts.empty:
                    st.caption("No packaging found for this ProductID.")
                else:
                    package_code = st.selectbox(
                        "PackageCode",
                        options=[""] + pkg_opts["PackageCode"].dropna().astype(str).tolist(),
                        index=0
                    )
                    if package_code:
                        selected_pkg = pkg_opts[pkg_opts["PackageCode"] == package_code].iloc[0].to_dict()
                        st.caption(
                            f'Pack: {selected_pkg.get("PackDescription","")} | '
                            f'LabelUPC: {selected_pkg.get("LabelUPC","")} | '
                            f'CaseUPC: {selected_pkg.get("CaseUPC","")}'
                        )
            else:
                selected_pkg = None

# rounding step
round_step = 0.0 if rounding == "No rounding" else float(rounding.split()[0])


# =========================
# Inputs: Manual RFT
# =========================
st.subheader("Batch Formula (Manual RFT — grams)")

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
            code = st.text_input(f"MaterialCode {i+1}", placeholder="e.g. OQ8154", key=f"code_{i}").strip()
            name = ""

    with col_weight:
        label = f"{code} (g)" if code else f"Ingredient {i+1} (g)"
        g = st.number_input(label, min_value=0.0, step=1.0, format="%.4f", key=f"g_{i}")

    selected_codes.append(code if code else f"Ingredient {i+1}")
    selected_names.append(name)
    old_g.append(float(g))

total_g = float(sum(old_g))
st.write(f"**RFT total:** {total_g:,.4f} g")

# Default new_total: use target_g if a reference target exists, otherwise use total_g
default_new_total = float(target_g) if target_g is not None and target_g > 0 else (total_g if total_g > 0 else 0.0)

new_total = st.number_input(
    "New batch total (g)",
    min_value=0.0,
    value=default_new_total,
    step=1.0,
    format="%.4f",
    key="new_total_g"
)


# =========================
# Calculate
# =========================
def highlight_oos(row, tol: float):
    oos = abs(float(row["DeltaPercent_num"])) > float(tol)
    style = "background-color: #ffe6e6; font-weight: 700;" if oos else ""
    return [style for _ in row.index]


if st.button("Calculate batch"):
    if total_g <= 0:
        st.error("RFT total must be greater than zero.")
        st.stop()

    ratios = [x / total_g for x in old_g]
    raw = [r * float(new_total) for r in ratios]

    # rounding + drift correction
    if round_step == 0.0:
        final = raw
    else:
        final = [round(x / round_step) * round_step for x in raw]
        drift = float(new_total) - float(sum(final))
        biggest_idx = int(max(range(len(final)), key=lambda k: final[k]))
        final[biggest_idx] += drift

    st.subheader("New batch results")

    out_df = pd.DataFrame({
        "MaterialCode": selected_codes,
        "MaterialName": selected_names,
        "Ratio": [round(r, 10) for r in ratios],
        "New (g)": [round(x, 4) for x in final],
    })

    st.dataframe(out_df, hide_index=True, use_container_width=True)
    st.write(f"**Check sum:** {sum(final):,.4f} g")

    # Reference BOM compare (advisory)
    if ref_product_id is not None:
        bom = build_reference_bom(ref, ref_product_id)

        st.subheader("Reference BOM (advisory)")
        if bom.empty:
            st.info("Reference BOM not available for this product.")
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

            view_disp = view.copy()
            view_disp["Manual_g"] = view_disp["Manual_g"].map(lambda x: f"{x:,.4f}")
            view_disp["ManualPercent"] = view_disp["ManualPercent"].map(lambda x: f"{x:,.4f}")
            view_disp["RefPercent"] = view_disp["RefPercent"].map(lambda x: f"{x:,.4f}")
            view_disp["DeltaPercent"] = view_disp["DeltaPercent_num"].map(lambda x: f"{x:,.4f}")

           

    # PDF download
    pdf_bytes = build_batch_ticket_pdf(
        out_df,
        float(new_total),
        title="AWLMIX Batch Ticket - New Batch",
        product_code=ref_product_code if ref_product_code else None,
        unit_type=selected_unit if selected_unit else None,
        target_lb=target_lb,
        packaging=selected_pkg if "selected_pkg" in globals() else None,
    )
    st.download_button(
        "Download Batch Ticket (PDF)",
        data=pdf_bytes,
        file_name="AWLMIX_Batch_Ticket_New_Batch.pdf",
        mime="application/pdf"
    )




