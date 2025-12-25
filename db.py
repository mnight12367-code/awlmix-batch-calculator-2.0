import sqlite3
from pathlib import Path
import shutil
from datetime import datetime
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent
REPO_DB = ROOT_DIR / "awlmix.db"

RUNTIME_DIR = Path("/tmp") / "awlmix"
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = RUNTIME_DIR / "awlmix.db"

def ensure_db():
    # Copy packaged DB into writable runtime location if not present yet
    if not DB_PATH.exists():
        if REPO_DB.exists():
            shutil.copy2(REPO_DB, DB_PATH)

def get_conn():
    ensure_db()
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn



def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS MaterialMaster (
        MaterialID INTEGER PRIMARY KEY AUTOINCREMENT,
        MaterialCode TEXT UNIQUE,
        MaterialName TEXT
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS Locations (
        LocationID INTEGER PRIMARY KEY AUTOINCREMENT,
        LocationCode TEXT UNIQUE
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS InventoryTxn (
        TxnID INTEGER PRIMARY KEY AUTOINCREMENT,
        TxnTime TEXT,
        MaterialID INTEGER,
        LocationID INTEGER,
        LotNumber TEXT,
        TxnType TEXT,
        Qty REAL,
        UOM TEXT,
        Notes TEXT,
        FOREIGN KEY(MaterialID) REFERENCES MaterialMaster(MaterialID),
        FOREIGN KEY(LocationID) REFERENCES Locations(LocationID)
    );
    """)

    for loc in ["AWLMIX", "CENTRAL", "F_WAREHOUSE"]:
        cur.execute("INSERT OR IGNORE INTO Locations(LocationCode) VALUES (?);", (loc,))

    conn.commit()
    conn.close()


def load_materials_from_csv(csv_path="MaterialMaster.csv"):
    conn = get_conn()
    df = pd.read_csv(csv_path)

    for _, r in df.iterrows():
        conn.execute("""
            INSERT OR IGNORE INTO MaterialMaster (MaterialCode, MaterialName)
            VALUES (?, ?)
        """, (r["MaterialCode"], r["MaterialName"]))

    conn.commit()
    conn.close()


def get_materials():
    conn = get_conn()
    df = pd.read_sql_query(
        """
        SELECT MaterialID, MaterialCode, MaterialName
        FROM MaterialMaster
        ORDER BY MaterialID
        """,
        conn,
    )
    conn.close()
    return df


def get_locations():
    conn = get_conn()
    df = pd.read_sql("SELECT * FROM Locations ORDER BY LocationCode", conn)
    conn.close()
    return df


def add_txn(material_id, location_id, lot, txn_type, qty, uom, notes):
    conn = get_conn()
    conn.execute("""
        INSERT INTO InventoryTxn
        (TxnTime, MaterialID, LocationID, LotNumber, TxnType, Qty, UOM, Notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.now().isoformat(timespec="seconds"),
        material_id,
        location_id,
        lot,
        txn_type,
        qty,
        uom,
        notes
    ))
    conn.commit()
    conn.close()


def get_on_hand():
    conn = get_conn()
    df = pd.read_sql("""
        SELECT
          m.MaterialCode,
          m.MaterialName,
          l.LocationCode,
          t.UOM,
          ROUND(SUM(t.Qty), 4) AS OnHand
        FROM InventoryTxn t
        JOIN MaterialMaster m ON m.MaterialID = t.MaterialID
        JOIN Locations l ON l.LocationID = t.LocationID
        GROUP BY m.MaterialCode, m.MaterialName, l.LocationCode, t.UOM
        HAVING SUM(t.Qty) <> 0
        ORDER BY m.MaterialCode, l.LocationCode;
    """, conn)
    conn.close()
    return df


def get_on_hand_by_location(location_code: str, uom: str = "LB"):
    conn = get_conn()
    df = pd.read_sql("""
        SELECT
          m.MaterialCode AS MaterialCode,
          ROUND(SUM(t.Qty), 4) AS OnHand
        FROM InventoryTxn t
        JOIN MaterialMaster m ON m.MaterialID = t.MaterialID
        JOIN Locations l ON l.LocationID = t.LocationID
        WHERE l.LocationCode = ?
          AND t.UOM = ?
        GROUP BY m.MaterialCode
    """, conn, params=(location_code, uom))
    conn.close()
    return df

