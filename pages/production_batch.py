import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime
import sys

# Ensure repo root on path
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from db import get_conn  # uses your existing SQLite connection


st.title("Production Batch (Progress)")

# ----------------------------
# Status -> % mapping (FINAL v1)
# ----------------------------
STATUS_TO_PROGRESS = {
    "PRE-BATCH": 25,
    "MAKING": 50,
    "QC": 75,
    "LABELING & PACKING": 90,
    "READY TO SHIP": 100,
}
STATUSES = list(STATUS_TO_PROGRESS.keys())

# ----------------------------
# Files (no changes to New Batch)
# ----------------------------
PRODUCT_MASTER_PATH = ROOT_DIR / "ProductMaster.txt"
WEIGHT_TARGETS_PATH = ROOT_DIR / "ProductWeightTargets.txt"

# ----------------------------
# Load TXT (CSV) files
# ----------------------------
@st.cache_data
def load_product_master(path: Path, mtime: float) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)

@st.cache_data
def load_weight_targets(path: Path, mtime: float) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)

pm_mtime = PRODUCT_MASTER_PATH.stat().st_mtime if PRODUCT_MASTER_PATH.exists() else 0
wt_mtime = WEIGHT_TARGETS_PATH.stat().st_mtime if WEIGHT_TARGETS_PATH.exists() else 0

pm = load_product_master(PRODUCT_MASTER_PATH, pm_mtime)
wt = load_weight_targets(WEIGHT_TARGETS_PATH, wt_mtime)


def ensure_production_batch_table():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS ProductionBatch (
        BatchID INTEGER PRIMARY KEY AUTOINCREMENT,
        BatchNumber TEXT UNIQUE,
        ProductID INTEGER,
        ProductCode TEXT,
        ProductName TEXT,
        UnitType TEXT,

        QtyUnits REAL,

        TargetPerUnitLB REAL,
        TargetPerUnitG REAL,
        TotalTargetLB REAL,
        TotalTargetG REAL,

        Status TEXT,

        Customer TEXT,
        Notes TEXT,

        CreatedAt TEXT,
        CreatedBy TEXT,
        UpdatedAt TEXT,
        UpdatedBy TEXT
    );
    """)
    conn.commit()
    conn.close()

def insert_batch(record: dict):
    conn = get_conn()
    conn.execute("""
        INSERT INTO ProductionBatch
        (BatchNumber, ProductID, ProductCode, ProductName, UnitType,
         QtyUnits, TargetPerUnitLB, TargetPerUnitG, TotalTargetLB, TotalTargetG,
         Status, Customer, Notes, CreatedAt, CreatedBy, UpdatedAt, UpdatedBy)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        record["BatchNumber"],
        record["ProductID"],
        record["ProductCode"],
        record["ProductName"],
        record["UnitType"],
        record["QtyUnits"],
        record["TargetPerUnitLB"],
        record["TargetPerUnitG"],
        record["TotalTargetLB"],
        record["TotalTargetG"],
        record["Status"],
        record["Customer"],
        record["Notes"],
        record["CreatedAt"],
        record["CreatedBy"],
        record["UpdatedAt"],
        record["UpdatedBy"],
    ))
    conn.commit()
    conn.close()

def update_batch_status(batch_id: int, new_status: str, user: str):
    conn = get_conn()
    conn.execute("""
        UPDATE ProductionBatch
        SET Status = ?, UpdatedAt = ?, UpdatedBy = ?
        WHERE BatchID = ?
    """, (new_status, datetime.now().isoformat(timespec="seconds"), user, batch_id))
    conn.commit()
    conn.close()

def get_recent_batches(limit: int = 50) -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query(f"""
        SELECT
            BatchID, BatchNumber, ProductCode, ProductName, UnitType,
            QtyUnits, Status, UpdatedAt, UpdatedBy,
            TargetPerUnitLB, TargetPerUnitG, TotalTargetLB, TotalTargetG,
            Customer, Notes
        FROM ProductionBatch
        ORDER BY UpdatedAt DESC
        LIMIT {int(limit)}
    """, conn)
    conn.close()
    return df


# ----------------------------
# Init
# ----------------------------


if pm.empty:
    st.error(f"ProductMaster.txt not found or empty: {PRODUCT_MASTER_PATH}")
    st.stop()

if wt.empty:
    st.error(f"ProductWeightTargets.txt not found or empty: {WEIGHT_TARGETS_PATH}")
    st.stop()

# Ensure types
pm["ProductID"] = pm["ProductID"].astype(int)
wt["ProductID"] = wt["ProductID"].astype(int)

# Normalize UnitType so GLUS/QTUS behave correctly
wt["UnitType"] = (
    wt["UnitType"]
    .astype(str)
    .str.replace('"', '', regex=False)
    .str.strip()
    .str.upper()
)


# ----------------------------
# Create Batch
# ----------------------------
st.subheader("Create Production Batch (standalone)")

user = st.text_input("Your name (required)", value="", placeholder="e.g., Michael")
batch_number = st.text_input("Batch Number (required)", value="", placeholder="e.g., 0224295091")
customer = st.text_input("Customer (optional)", value="")
notes = st.text_area("Notes (optional)", value="")

pm["Display"] = pm["ProductCode"].astype(str) + " — " + pm["ProductName"].astype(str)
selected_display = st.selectbox("Product", pm["Display"].tolist())

selected = pm.loc[pm["Display"] == selected_display].iloc[0]
product_id = int(selected["ProductID"])
product_code = str(selected["ProductCode"])
product_name = str(selected["ProductName"])

# UnitType options for this ProductID (from ProductWeightTargets)
wt_rows = wt.loc[wt["ProductID"] == product_id].copy()
if wt_rows.empty:
    st.error("No weight targets found for this ProductID in ProductWeightTargets.txt")
    st.stop()
# DEBUG: show available unit types for this product   
st.write(wt_rows[["ProductID", "UnitType"]])
 

unit_options = sorted(
    wt_rows["UnitType"]
    .dropna()
    .astype(str)
    .str.replace('"', '', regex=False)
    .str.strip()
    .str.upper()
    .unique()
    .tolist()
)

default_idx = unit_options.index("GLUS") if "GLUS" in unit_options else 0
unit_type = st.selectbox("UnitType", unit_options, index=default_idx)

row_u = wt_rows.loc[
    wt_rows["UnitType"].astype(str).str.strip().str.upper() == unit_type
].iloc[0]

target_lb_per_unit = float(row_u.get("TotalWeightPerUnitLB", 0.0) or 0.0)
target_g_per_unit = float(row_u.get("TotalWeightPerUnitG", 0.0) or 0.0)

qty_units = st.number_input("Qty (Units)", min_value=0.0, step=1.0, format="%.4f")

total_target_lb = target_lb_per_unit * float(qty_units)
total_target_g = target_g_per_unit * float(qty_units)

c1, c2, c3 = st.columns(3)
with c1:
    st.metric("Target per Unit (LB)", f"{target_lb_per_unit:.4f}")
with c2:
    st.metric("Target per Unit (G)", f"{target_g_per_unit:.2f}")
with c3:
    st.metric("Total Target (LB)", f"{total_target_lb:.4f}")

st.write(f"**Total Target (G):** {total_target_g:.2f}")

if st.button("Create Batch", type="primary"):
    if not user.strip():
        st.error("Enter your name.")
    elif not batch_number.strip():
        st.error("Enter a Batch Number.")
    elif qty_units <= 0:
        st.error("Qty (Units) must be greater than 0.")
    else:
        now = datetime.now().isoformat(timespec="seconds")
        record = {
            "BatchNumber": batch_number.strip(),
            "ProductID": product_id,
            "ProductCode": product_code,
            "ProductName": product_name,
            "UnitType": unit_type,
            "QtyUnits": float(qty_units),
            "TargetPerUnitLB": float(target_lb_per_unit),
            "TargetPerUnitG": float(target_g_per_unit),
            "TotalTargetLB": float(total_target_lb),
            "TotalTargetG": float(total_target_g),
            "Status": "PRE-BATCH",
            "Customer": customer.strip(),
            "Notes": notes.strip(),
            "CreatedAt": now,
            "CreatedBy": user.strip(),
            "UpdatedAt": now,
            "UpdatedBy": user.strip(),
        }
        try:
            insert_batch(record)
            st.success("Batch created → PRE-BATCH (25%).")
            st.rerun()
        except Exception as e:
            st.error(f"Could not create batch (duplicate BatchNumber?): {e}")

# ----------------------------
# Progress Bar View
# ----------------------------
st.divider()
st.subheader("Batch Progress")

recent = get_recent_batches(limit=50)
if recent.empty:
    st.info("No production batches created yet.")
    st.stop()

batch_id = st.selectbox(
    "Select batch",
    recent["BatchID"].tolist(),
    format_func=lambda x: f"{recent.loc[recent.BatchID==x,'BatchNumber'].values[0]} — "
                          f"{recent.loc[recent.BatchID==x,'ProductCode'].values[0]}",
)

b = recent.loc[recent["BatchID"] == batch_id].iloc[0]
status = str(b.get("Status") or "PRE-BATCH").upper().strip()
progress = STATUS_TO_PROGRESS.get(status, 0)

st.write(f"**Stage:** {status}  (**{progress}%**)")
st.progress(progress)

st.caption(f"Last update: {b.get('UpdatedAt','')} by {b.get('UpdatedBy','')}")

new_status = st.selectbox(
    "Update stage",
    STATUSES,
    index=STATUSES.index(status) if status in STATUSES else 0
)

if st.button("Save Stage", type="primary"):
    if not user.strip():
        st.error("Enter your name (top of page).")
    else:
        update_batch_status(int(batch_id), new_status, user.strip())
        st.success(f"Updated → {new_status} ({STATUS_TO_PROGRESS[new_status]}%).")
        st.rerun()

st.divider()
st.subheader("Recent Batches (table)")
st.dataframe(
    recent[["BatchNumber","ProductCode","ProductName","UnitType","QtyUnits","Status","UpdatedAt","UpdatedBy"]],
    use_container_width=True,
    hide_index=True
)
















