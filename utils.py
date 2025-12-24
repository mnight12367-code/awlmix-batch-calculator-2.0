from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import LETTER
from reportlab.lib import colors
from io import BytesIO
from datetime import datetime

def generate_manual_issue_pdf(
    material_rows,
    location,
    issued_by,
    reason=""
):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=LETTER)
    styles = getSampleStyleSheet()
    elements = []

    # Header
    elements.append(Paragraph("<b>AWLMIX – Manual Material Issue</b>", styles["Title"]))
    elements.append(Paragraph(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles["Normal"]))
    elements.append(Paragraph(f"Location: {location}", styles["Normal"]))
    elements.append(Paragraph(f"Issued By: {issued_by}", styles["Normal"]))
    elements.append(Paragraph("<br/>", styles["Normal"]))

    # Table data
    table_data = [["Material Code", "Material Name", "Issued (LB)", "Issued (KG)"]]
    for r in material_rows:
        table_data.append([
            r["MaterialCode"],
            r["MaterialName"],
            f'{r["LB"]:.4f}',
            f'{r["KG"]:.4f}',
        ])

    table = Table(table_data, colWidths=[100, 200, 80, 80])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("GRID", (0,0), (-1,-1), 1, colors.black),
        ("ALIGN", (2,1), (-1,-1), "RIGHT"),
    ]))

    elements.append(table)

    if reason:
        elements.append(Paragraph("<br/>Reason:", styles["Normal"]))
        elements.append(Paragraph(reason, styles["Normal"]))

    doc.build(elements)
    buffer.seek(0)
    return buffer


