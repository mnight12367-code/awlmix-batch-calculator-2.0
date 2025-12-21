import streamlit as st
from db import get_materials, get_locations, add_txn, get_on_hand

st.title("Inventory")

materials = get_materials()
locations = get_locations()

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
            locations.loc[locations.LocationID==x,"LocationCode"].values[0]
    )

    lot = st.text_input("Lot / Batch #")
    qty = st.number_input("Quantity", min_value=0.0)
    uom = st.selectbox("UOM", ["LB", "KG", "GAL", "EA"])
    notes = st.text_area("Notes")

    if st.button("Post Receipt", type="primary"):
        if qty <= 0:
            st.error("Quantity must be greater than 0.")
        else:
            add_txn(mat, loc, lot, "RECEIPT", qty, uom, notes)
            st.success("Material received")
            st.rerun()

# ---------------- ISSUE ----------------
with tab2:
    st.subheader("Issue Material (Manual)")

    mat = st.selectbox(
        "Material",
        materials["MaterialID"],
        key="issue_mat",
        format_func=lambda x:
            f"{materials.loc[materials.MaterialID==x,'MaterialCode'].values[0]} - "
            f"{materials.loc[materials.MaterialID==x,'MaterialName'].values[0]}"
    )

    loc = st.selectbox(
        "Location",
        locations["LocationID"],
        key="issue_loc",
        format_func=lambda x:
            locations.loc[locations.LocationID==x,"LocationCode"].values[0]
    )

    lot = st.text_input("Lot / Batch #", key="issue_lot")
    qty = st.number_input("Quantity", min_value=0.0, key="issue_qty")
    uom = st.selectbox("UOM", ["LB", "KG", "GAL", "EA"], key="issue_uom")
    notes = st.text_area("Notes", key="issue_notes")

    if st.button("Post Issue", type="primary"):
        if qty <= 0:
            st.error("Quantity must be greater than 0.")
        else:
            add_txn(mat, loc, lot, "ISSUE", -qty, uom, notes)
            st.success("Material issued")
            st.rerun()

# ---------------- ON HAND ----------------
with tab3:
    st.subheader("On-Hand Report")
    st.dataframe(get_on_hand(), use_container_width=True)
    st.caption("On-hand = SUM of all receipts/issues (ledger method).")
