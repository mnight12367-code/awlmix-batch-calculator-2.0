import streamlit as st
from db import init_db, load_materials_from_csv

# --- Initialize database ---
init_db()
load_materials_from_csv()

# --- Page config ---
st.set_page_config(page_title="AWLMIX Operations Tools", layout="wide")

st.title("AWLMIX Operations Tools")
st.caption("Manufacturing • Inventory • Batch Control")

st.markdown("""
### Welcome

Select a tool from the sidebar to get started:

- **New Batch**  
  Scale product formulas to a target size with accurate weight calculations.

- **Rework Calculator**  
  Determine maximum safe reuse and required add-backs to hit target specs.

- **Feasibility Check (Inventory vs BOM)**  
  Verify material availability before production (GLUS / QTUS supported).

- **Inventory**  
  Receive, issue, and view on-hand inventory by location.

- **Production Batch**  
  Create and track production batches from PRE-BATCH through READY TO SHIP.

---

🛠️ **Built for real manufacturing workflows**  
Accurate weights • Variant-aware units • Ledger-based inventory • Batch traceability
""")

