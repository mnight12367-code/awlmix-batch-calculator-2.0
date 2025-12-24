import streamlit as st
import pandas as pd
import sys
from pathlib import Path
from datetime import datetime
from pdf_utils import generate_manual_issue_pdf
from datetime import datetime
from io import BytesIO


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
    st.subheader("Issue Material (Manual) — Multiple Materials")

    # --- session cart ---
    if "issue_cart" not in st.session_state:
        st.session_state.issue_cart = []

    # --- pick ONE line to add ---
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
    notes2 = st.text_area("Line notes (optional)", key="issue_notes", value="")

    colA, colB = st.columns([1, 1])
    with colA:
        if st.button("➕ Add line to issue list"):
            if qty2 <= 0:
                st.error("Quantity must be greater than 0.")
            else:
                material_code = materials.loc[materials.MaterialID == mat2, "MaterialCode"].values[0]
                material_name = materials.loc[materials.MaterialID == mat2, "MaterialName"].values[0]
                location_code = locations.loc[locations.LocationID == loc2, "LocationCode"].values[0]

                st.session_state.issue_cart.append({
                    "MaterialID": mat2,
                    "MaterialCode": material_code,
                    "MaterialName": material_name,
                    "LocationID": loc2,
                    "LocationCode": location_code,
                    "Lot": lot2.strip(),
                    "Qty": float(qty2),
                    "UOM": uom2,
                    "Notes": notes2.strip(),
                })
                st.success(f"Added: {material_code} ({qty2} {uom2})")

    with colB:
        if st.button("🧹 Clear list"):
            st.session_state.issue_cart = []
            st.rerun()

    st.divider()

    # --- show current cart ---
    st.subheader("Issue list (will post all lines)")
    if len(st.session_state.issue_cart) == 0:
        st.info("No lines added yet. Add materials above.")
    else:
        df_cart = pd.DataFrame(st.session_state.issue_cart)[
    ["MaterialCode", "MaterialName", "LocationCode", "Lot", "Qty", "UOM", "Notes"]
]

        st.dataframe(df_cart, width="stretch", hide_index=True)


        issued_by = st.text_input("Issued By (name)", key="issue_by", value="")
        header_notes = st.text_area("Header notes (optional)", key="issue_header_notes", value="")

        # --- post all lines ---
        if st.button("Post Issue (ALL lines)", type="primary", use_container_width=True):
            # safety: prevent empty
            if len(st.session_state.issue_cart) == 0:
                st.error("Nothing to post.")
                st.stop()
                st.session_state.last_issue_pdf = pdf_buf.getvalue()
                

            # post each line as a ledger txn
            for line in st.session_state.issue_cart:
                add_txn(
                    line["MaterialID"],
                    line["LocationID"],
                    line["Lot"],
                    "ISSUE",
                    float(-line["Qty"]),          # negative for issue
                    line["UOM"],
                    (line["Notes"] or header_notes).strip()
                )

            st.success(f"Posted {len(st.session_state.issue_cart)} issue line(s).")

            # OPTIONAL: generate ONE PDF for all lines
            # If you already have a PDF generator, this is where you call it:
            # pdf_buf = generate_multi_issue_pdf(lines=st.session_state.issue_cart, issued_by=issued_by, header_notes=header_notes)
            # st.download_button("📄 Download Issue PDF", pdf_buf, f"manual_issue_{datetime.now():%Y%m%d_%H%M%S}.pdf", "application/pdf")

            # reset cart after posting
            st.session_state.issue_cart = []
            st.rerun()

# ---------------- ON HAND ----------------
with tab3:
    st.subheader("On-Hand Report")
    st.dataframe(get_on_hand(), use_container_width=True)
    st.caption("On-hand = SUM of all receipts/issues (ledger method).")










