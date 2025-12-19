# AWLMIX Batch Calculator 2.0

AWLMIX Batch Calculator is a Streamlit-based production tool for **manual batch creation, rework planning, and batch ticket generation** in a manufacturing / mixing-room environment.

This app is designed to mirror **real-world production workflows**, where operators manually enter ingredients, while master data tables are used strictly as **reference and source-of-truth** — not as forced automation.

---

## 🔧 Core Features

### ✅ New Batch
- Manual ingredient entry (grams)
- Automatic ratio scaling to a new batch size
- Rounding with drift correction
- **Batch Ticket PDF export**
- Optional **reference BOM comparison** (from ProductMaterialUsage)

### 🔁 Rework
- Calculates **maximum safe reuse %**
- Prevents over-target ingredients
- Computes required add-backs
- **Rework Batch Ticket PDF export**
- Designed for real rework decision-making

### 📦 Packaging-Aware Tickets
- Packaging information is sourced from **PackagingMaster**
- Batch Tickets reflect **product + packaging**, not just formulas
- Ensures correct labels, package codes, and audit traceability

---

## 🗂️ Repository Structure


---

## 📐 Design Philosophy (Important)

- **Manual entry is authoritative**
  - Operators type what they actually mix
  - The system does not auto-fill formulas

- **Reference data is advisory**
  - `ProductMaterialUsage` is used for comparison only
  - Differences are highlighted, not blocked

- **Packaging is a source of truth**
  - `PackagingMaster` defines how products are labeled and packed
  - Batch Tickets always reflect packaging reality

- **PDF batch tickets are legal records**
  - Tickets are generated exactly as mixed
  - Intended for QC, traceability, and audits

This mirrors how real ERP systems (SAP / Oracle) separate:
> Product identity → formula reference → packaging → execution

---

## 🖨️ Batch Ticket PDFs

Both **New Batch** and **Rework** generate PDFs that include:
- Timestamp
- Ingredient breakdown
- Totals and checks
- Reuse percentage (rework)
- Packaging context (via PackagingMaster)

These PDFs are intended to be:
- Printed
- Archived
- Audited

---

## ☁️ Deployment

This app is designed for **Streamlit Cloud**.

### Dependencies
Listed in `requirements.txt`:

No local server is required.  
When deployed on Streamlit Cloud, the app runs independently of the user’s computer.

---

## 🚀 Roadmap (Planned)

- Inventory feasibility checks
- SQLite / MySQL backend
- Batch history & reporting
- User roles / approvals
- Packaging + production integration

---

## 🧠 Author Notes

This project is intentionally built to:
- Reflect real production constraints
- Avoid over-automation
- Maintain human accountability
- Support gradual ERP evolution

Add project README and architecture overview
