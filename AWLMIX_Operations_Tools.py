import streamlit as st
from db import init_db, load_materials_from_csv

# --- Initialize database ---
init_db()
load_materials_from_csv()

# --- Page config ---
st.set_page_config(
    page_title="AWLMIX Operations Tools",
    layout="wide"
)

st.title("AWLMIX Operations Tools")
st.caption("Manufacturing • Inventory • Feasibility • Batch Control")

st.markdown("""
### Welcome

Select a tool from the sidebar to get started:

- **New Batch**  
  Scale product formulas to a required total using accurate weight targets.

- **Rework**  
  Calculate maximum safe reuse and required add-backs to hit specification.

- **Feasibility**  
  Check inventory availability against BOM requirements (GLUS / QTUS supported).

- **Inventory**  
  Receive, issue, and view on-hand inventory by location with full traceability.

- **Production Batch**  
  Create and track production batches from **PRE-BATCH** through **READY TO SHIP**.

---

🛠️ **Built for real manufacturing operations**  
Variant-aware units • Ledger-based inventory • BOM-driven feasibility • Batch traceability
""")


