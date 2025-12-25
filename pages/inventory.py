import streamlit as st
import pandas as pd
import sys
from pathlib import Path
from datetime import datetime

from pdf_utils import generate_multi_issue_pdf
import os
import streamlit as st

DEBUG = os.getenv("DEBUG", "0") == "1"

if DEBUG:
    # your st.write(...) debug block here
    ...


# Ensure repo root is on Python path (fixes ModuleNotFoundError on Streamlit Cloud)
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from db import get_materials, get_locations, add_txn, get_on_hand

st.title("Inventory")
import streamlit as st
import sqlite3
from pathlib import Path

st.write("cwd:", Path.cwd())
st.write("__file__:", Path(__file__).resolve())

# If you keep the DB in the repo, point to it explicitly:
DB_PATH = Path(__file__).resolve().parents[1] / "awlmix.db"   # <-- adjust name if different
st.write("DB_PATH:", DB_PATH)
st.write("DB exists:", DB_PATH.exists(), "size:", DB_PATH.stat().st_size if DB_PATH.exists() else None)

try:
    conn = sqlite3.connect(DB_PATH)
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;").fetchall()
    st.write("Tables:", tables)
    conn.close()
except Exception as e:
    st.exception(e)
    st.stop()


materials = get_materials()
locations = get_locations()

# Safety checks
if materials.empty:
    st.error("MaterialMaster is empty. Check MaterialMaster.csv and db load step.")
    st.stop()

if locations.empty:
    st.error("Locations table is empty.")
    st.stop()

tab1, tab2, tab3 = st.tabs(["Receive Material", "Issue Material", "On-Hand"])

# ---------------- RECEIVE ----------------
with tab1:
    st.subheader("Receive Material — Multiple Materials")

    if "receipt_cart" not in st.session_state:
        st.session_state.receipt_cart = []

    if "last_receipt_pdf" not in st.session_state:
        st.session_state.last_receipt_pdf = None
    if "last_receipt_pdf_name" not in st.session_state:
        st.session_state.last_receipt_pdf_name = ""

    mat_r = st.selectbox(
        "Material",
        materials["MaterialID"],
        key="rcv_mat",
        format_func=lambda x:
            f"{materials.loc[materials.MaterialID==x,'MaterialCode'].values[0]} - "
            f"{materials.loc[materials.MaterialID==x,'MaterialName'].values[0]}"
    )

    loc_r = st.selectbox(
        "Location",
        locations["LocationID"],
        key="rcv_loc",
        format_func=lambda x:
            locations.loc[locations.LocationID==x, "LocationCode"].values[0]
    )

    lot_r = st.text_input("Lot / Batch # (optional)", key="rcv_lot", value="")
    qty_r = st.number_input("Quantity Received (positive)", key="rcv_qty", min_value=0.0, step=1.0, format="%.4f")
    uom_r = st.selectbox("UOM", ["LB", "KG", "GAL", "EA"], key="rcv_uom")
    notes_r = st.text_area("Line notes (optional)", key="rcv_notes", value="")

    colA, colB = st.columns([1, 1])
    with colA:
        if st.button("➕ Add line to receive list"):
            if qty_r <= 0:
                st.error("Quantity must be greater than 0.")
            else:
                material_code = materials.loc[materials.MaterialID == mat_r, "MaterialCode"].values[0]
                material_name = materials.loc[materials.MaterialID == mat_r, "MaterialName"].values[0]
                location_code = locations.loc[locations.LocationID == loc_r, "LocationCode"].values[0]

                st.session_state.receipt_cart.append({
                    "MaterialID": mat_r,
                    "MaterialCode": material_code,
                    "MaterialName": material_name,
                    "LocationID": loc_r,
                    "LocationCode": location_code,
                    "Lot": lot_r.strip(),
                    "Qty": float(qty_r),
                    "UOM": uom_r,
                    "Notes": notes_r.strip(),
                })
                st.success(f"Added: {material_code} ({qty_r} {uom_r})")

    with colB:
        if st.button("🧹 Clear receive list"):
            st.session_state.receipt_cart = []
            st.rerun()

    st.divider()

    st.subheader("Receive list (will post all lines)")
    if len(st.session_state.receipt_cart) == 0:
        st.info("No lines added yet. Add materials above.")
    else:
        df_rcv = pd.DataFrame(st.session_state.receipt_cart)[
            ["MaterialCode", "MaterialName", "LocationCode", "Lot", "Qty", "UOM", "Notes"]
        ]
        st.dataframe(df_rcv, width="stretch", hide_index=True)

        received_by = st.text_input("Received By (name)", key="rcv_by", value="")
        header_notes = st.text_area("Header notes (optional)", key="rcv_header_notes", value="")

        if st.button("Post Receipt (ALL lines)", type="primary"):
            if len(st.session_state.receipt_cart) == 0:
                st.error("Nothing to post.")
                st.stop()

            for line in st.session_state.receipt_cart:
                add_txn(
                    line["MaterialID"],
                    line["LocationID"],
                    line["Lot"],
                    "RECEIPT",
                    float(line["Qty"]),
                    line["UOM"],
                    (line["Notes"] or header_notes).strip()
                )

            pdf_buf = generate_multi_issue_pdf(
                lines=st.session_state.receipt_cart,
                issued_by=received_by.strip() or "Unknown",
                header_notes=header_notes.strip(),
                issued_at=datetime.now(),
            )

            st.session_state.last_receipt_pdf = pdf_buf.getvalue()
            st.session_state.last_receipt_pdf_name = f"manual_receipt_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

            st.success(f"Posted {len(st.session_state.receipt_cart)} receipt line(s). PDF ready below.")

            st.session_state.receipt_cart = []
            st.rerun()

    if st.session_state.last_receipt_pdf:
        st.divider()
        st.subheader("Last posted receipt PDF")
        st.download_button(
            label="📄 Download Receipt Record (PDF)",
            data=st.session_state.last_receipt_pdf,
            file_name=st.session_state.last_receipt_pdf_name or "manual_receipt.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
        if st.button("Clear last receipt PDF"):
            st.session_state.last_receipt_pdf = None
            st.session_state.last_receipt_pdf_name = ""
            st.rerun()


# ---------------- ISSUE ----------------
with tab2:
    st.subheader("Issue Material (Manual) — Multiple Materials")

    if "issue_cart" not in st.session_state:
        st.session_state.issue_cart = []

    if "last_issue_pdf" not in st.session_state:
        st.session_state.last_issue_pdf = None
    if "last_issue_pdf_name" not in st.session_state:
        st.session_state.last_issue_pdf_name = ""

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

        if st.button("Post Issue (ALL lines)", type="primary"):
            if len(st.session_state.issue_cart) == 0:
                st.error("Nothing to post.")
                st.stop()

            lines_for_pdf = list(st.session_state.issue_cart)

            for line in lines_for_pdf:
                add_txn(
                    line["MaterialID"],
                    line["LocationID"],
                    line["Lot"],
                    "ISSUE",
                    float(-line["Qty"]),
                    line["UOM"],
                    (line["Notes"] or header_notes).strip()
                )

            pdf_buf = generate_multi_issue_pdf(
                lines=lines_for_pdf,
                issued_by=issued_by.strip() or "Unknown",
                header_notes=header_notes.strip(),
                issued_at=datetime.now(),
            )

            st.session_state.last_issue_pdf = pdf_buf.getvalue()
            st.session_state.last_issue_pdf_name = f"manual_issue_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

            st.success(f"Posted {len(lines_for_pdf)} issue line(s). PDF ready below.")

            st.session_state.issue_cart = []
            st.rerun()

    if st.session_state.last_issue_pdf:
        st.divider()
        st.subheader("Last posted issue PDF")
        st.download_button(
            label="📄 Download Issue Record (PDF)",
            data=st.session_state.last_issue_pdf,
            file_name=st.session_state.last_issue_pdf_name or "manual_issue.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
        if st.button("Clear last Issue PDF"):
            st.session_state.last_issue_pdf = None
            st.session_state.last_issue_pdf_name = ""
            st.rerun()


# ---------------- ON HAND ----------------
with tab3:
    st.subheader("On-Hand Report")
    st.dataframe(get_on_hand(), use_container_width=True)
    st.caption("On-hand = SUM of all receipts/issues (ledger method).")

   










