import streamlit as st
from db import init_db, load_materials_from_csv

init_db()
load_materials_from_csv()

st.set_page_config(page_title="AWLMIX", layout="wide")
st.title("AWLMIX Tools")

st.markdown("""
Choose a tool from the sidebar:

- **New Batch** – scale formulas to a new total
- **Rework** – max safe reuse + add-backs to target
- **Feasibility** – coming soon
- **Inventory** – coming soon
""")

