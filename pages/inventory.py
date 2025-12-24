import streamlit as st
import sys
from pathlib import Path
from datetime import datetime
from pdf_utils import generate_manual_issue_pdf

# Ensure repo root is on Python path (fixes ModuleNotFoundError on Streamlit Cloud)
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from db import get_materials, get_locations, add_txn, get_on_hand

st.title("Inventory")

materials = get_materials()
locations = get_locations()

# Safety checks
if materials.empty:
    st.error("MaterialMaster is empty. Check MaterialMaster.csv and db load step.")
    st.stop()

if locations.empty:
    st.error("Locations table is empty.")
    st.stop()

# ✅ Tabs must be created BEFORE using tab1/tab2/tab3
tab1, tab2, tab3 = st.tabs(["Receive Material", "Issue Material", "On-Hand"])

# ---------------- RECEIVE ----------------
with tab1:
    st.subheader("Receive Material")

    mat = st.selectbox(
        "Material",
        materials["MaterialID"],
        format_func=lambda x:
            f"{materials.loc[materials.MaterialID==x,'MaterialCode'].values[0]} - "
            f"{materials.loc[materials.MaterialID==x,'MaterialName'].values[0]}"
    )

    loc = st.selectbox(
        "Location",
        locations["LocationID"],
        format_func=lambda x:
            locations.loc[locations.LocationID==x, "LocationCode"].values[0]
    )

    lot = st.text_input("Lot / Batch # (optional)", value="")
    qty = st.number_input("Quantity Received (positive)", min_value=0.0, step=1.0, format="%.4f")
    uom = st.selectbox("UOM", ["LB", "KG", "GAL", "EA"])
    notes = st.text_area("Notes (optional)", value="")

    if st.button("Post Receipt", type="primary"):
        if qty <= 0:
            st.error("Quantity must be greater than 0.")
        else:
            add_txn(mat, loc, lot.strip(), "RECEIPT", float(qty), uom, notes.strip())
            st.success("Receipt posted.")
            st.rerun()

# ---------------- ISSUE ----------------
with tab2:
    st.subheader("Issue Material (Manual)")

    mat2 = st.selectbox(
        "Material",
        materials["MaterialID"],
        key="issue_mat",
        format_func=lambda x:
            f"{materials.loc[materials.MaterialID==x,'MaterialCode'].values[0]} - "
            f"{materials.loc[materials.MaterialID==x,'MaterialName'].values[0]}"
    )

    loc2 = st.selectbox(
        "Location",
        locations["LocationID"],
        key="issue_loc",
        format_func=lambda x:
            locations.loc[locations.LocationID==x, "LocationCode"].values[0]
    )

    lot2 = st.text_input("Lot / Batch # (optional)", key="issue_lot", value="")
    qty2 = st.number_input("Quantity Issued (positive)", key="issue_qty", min_value=0.0, step=1.0, format="%.4f")
    uom2 = st.selectbox("UOM", ["LB", "KG", "GAL", "EA"], key="issue_uom")
    notes2 = st.text_area("Notes (optional)", key="issue_notes", value="")

    issued_by = st.text_input("Issued By (name)", key="issue_by", value="")

    if st.button("Post Issue + Generate PDF", type="primary"):
        if qty2 <= 0:
            st.error("Quantity must be greater than 0.")
        else:
            # Post transaction (negative quantity)
            add_txn(mat2, loc2, lot2.strip(), "ISSUE", float(-qty2), uom2, notes2.strip())

            # Look up codes/names for PDF
            material_code = materials.loc[materials.MaterialID == mat2, "MaterialCode"].values[0]
            material_name = materials.loc[materials.MaterialID == mat2, "MaterialName"].values[0]
            location_code = locations.loc[locations.LocationID == loc2, "LocationCode"].values[0]

            pdf_buf = generate_manual_issue_pdf(
                material_code=material_code,
                material_name=material_name,
                location_code=location_code,
                lot=lot2.strip(),
                qty=float(qty2),
                uom=uom2,
                notes=notes2.strip(),
                issued_by=issued_by.strip() or "Unknown",
                issued_at=datetime.now(),
            )

            st.success("Issue posted. Download the PDF record below.")

            st.download_button(
                label="📄 Download Manual Issue Record (PDF)",
                data=pdf_buf,
                file_name=f"manual_issue_{material_code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
   


if st.button("Issue Material (Manual)"):
    pdf_buffer = generate_manual_issue_pdf(
        material_rows=[
            {
                "MaterialCode": "OQ8154",
                "MaterialName": "White (4906991 / 5504940)",
                "LB": issued_lb,
                "KG": issued_lb * 0.453592,
            }
        ],
        location=location_code,
        issued_by="Michael",
        reason=st.session_state.get("issue_reason", "")
    )

    st.download_button(
        label="📄 Download Issue Record (PDF)",
        data=pdf_buffer,
        file_name=f"manual_issue_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
        mime="application/pdf",
    )

    st.success("Manual issue recorded. PDF generated.")

# ---------------- ON HAND ----------------
with tab3:
    st.subheader("On-Hand Report")
    st.dataframe(get_on_hand(), use_container_width=True)
    st.caption("On-hand = SUM of all receipts/issues (ledger method).")



