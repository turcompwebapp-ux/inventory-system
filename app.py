import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(
    page_title="TURCOMP Inventory",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)
# ── PASSWORD ──────────────────────────────────────────────────────────────────
def check_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        st.markdown("## 🔒 TURCOMP Inventory System")
        st.markdown("Please enter the access password to continue.")
        pwd = st.text_input("Password", type="password")
        if st.button("Login"):
            if pwd == st.secrets["APP_PASSWORD"]:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("❌ Incorrect password.")
        st.stop()

check_password()
# ── STYLING ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stSidebar"] {
    background-color: #0f1e38;
}
[data-testid="stSidebar"] * {
    color: #cbd5e1 !important;
}
[data-testid="stSidebar"] .stRadio label {
    font-size: 15px !important;
    padding: 6px 0;
}
[data-testid="stSidebar"] [aria-checked="true"] + div {
    color: #ffffff !important;
    font-weight: 600 !important;
}
.kpi-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 18px 20px;
    display: flex;
    align-items: center;
    gap: 16px;
}
.kpi-icon {
    width: 48px; height: 48px;
    border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    font-size: 22px; flex-shrink: 0;
}
.kpi-label { font-size: 12px; color: #64748b; margin-bottom: 2px; }
.kpi-value { font-size: 26px; font-weight: 700; color: #0f1e38; line-height:1; }
.kpi-sub   { font-size: 11px; color: #94a3b8; margin-top: 2px; }
.cond-pill {
    border-radius: 10px; padding: 14px 10px;
    text-align: center; font-size: 13px; font-weight: 600;
}
.section-title {
    font-size: 15px; font-weight: 600;
    color: #0f1e38; margin: 18px 0 10px;
}
.chart-card {
    background: #ffffff; border: 1px solid #e2e8f0;
    border-radius: 12px; padding: 16px;
}
div[data-testid="stForm"] {
    border: 1px solid #e2e8f0;
    border-radius: 12px; padding: 20px;
    background: #ffffff;
}
.item-detail-card {
    background: #f8fafc; border: 1px solid #e2e8f0;
    border-radius: 10px; padding: 14px 18px; margin: 10px 0;
}
.stTabs [data-baseweb="tab"] {
    font-size: 14px; font-weight: 500;
}
</style>
""", unsafe_allow_html=True)

# ── CONSTANTS ─────────────────────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
CONDITION_OUT_OPTIONS   = ["GOOD", "DAMAGED (WORKING)"]
CONDITION_FULL_OPTIONS  = [
    "GOOD", "DAMAGED (WORKING)", "DAMAGED (NOT WORKING)",
    "UNDER REPAIR", "LOST", "DISPOSED", "SERVICE DUE"
]
RETURN_STATUS_OPTIONS = [
    "FULLY RETURNED", "PARTIALLY RETURNED", "LOST", "DAMAGED", "OUTSTANDING"
]
STATUS_OPTIONS = ["AVAILABLE", "OUT", "RETURNED", "PARTIALLY RETURNED", "UNDER MAINTENANCE", "LOST"]
COLOR_MAP_COND = {
    "GOOD":                  "#3B6D11",
    "DAMAGED":               "#E24B4A",
    "DAMAGED (NOT WORKING)": "#A32D2D",
    "DAMAGED (WORKING)":     "#BA7517",
    "LOST":                  "#534AB7",
    "MINOR ISSUE":           "#378ADD",
    "SERVICE DUE":           "#888780",
}
PILL_STYLE = {
    "GOOD":                  ("🟢", "#f0fdf4", "#166534"),
    "DAMAGED (WORKING)":     ("🟠", "#fff7ed", "#9a3412"),
    "DAMAGED (NOT WORKING)": ("🔴", "#fef2f2", "#991b1b"),
    "UNDER REPAIR":          ("🔵", "#eff6ff", "#1e40af"),
    "LOST":                  ("🟣", "#f5f3ff", "#5b21b6"),
    "DISPOSED":              ("⚫", "#f1f5f9", "#334155"),
    "SERVICE DUE":           ("⚪", "#f8fafc", "#475569"),
}

# ── GOOGLE SHEETS ─────────────────────────────────────────────────────────────
@st.cache_resource
def get_worksheet():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=SCOPES
    )
    client = gspread.authorize(creds)
    return client.open("inventorydata").worksheet("inventorydata")

@st.cache_data(ttl=30)
def load_data():
    ws   = get_worksheet()
    # Get raw string values to preserve leading zeros
    all_values = ws.get_all_values()
    if not all_values:
        return pd.DataFrame()
    headers = all_values[0]
    rows    = all_values[1:]
    df      = pd.DataFrame(rows, columns=headers)
    df      = df.replace("", None)
    df["QUANTITY"] = pd.to_numeric(df["QUANTITY"], errors="coerce").fillna(0)
    return df

def reload():
    st.cache_data.clear()
    st.rerun()

# ── SEARCH HELPER ─────────────────────────────────────────────────────────────
def search_item(df, label="search"):
    search_by = st.selectbox(
        "Search by",
        ["Serial Number", "Tagging Number", "Description", "Brand", "Category"],
        key=f"sb_{label}"
    )
    query = st.text_input(
        f"Enter {search_by} (or part of it)",
        key=f"q_{label}"
    )
    if not query:
        return None, None

    col_map = {
        "Serial Number":  "SERIAL NUMBER",
        "Tagging Number": "TAGGING NUMBER",
        "Description":    "DESCRIPTION",
        "Brand":          "BRAND",
        "Category":       "CATEGORY",
    }
    col     = col_map[search_by]
    matches = df[
        df[col].fillna("").astype(str).str.strip().str.upper()
        .str.contains(query.strip().upper(), regex=False)
    ]

    if matches.empty:
        st.error(f"❌ No items found matching '{query}' in {search_by}.")
        return None, None

    # Optional category filter if many results
    if len(matches) > 5:
        cats = ["All"] + sorted(matches["CATEGORY"].dropna().unique().tolist())
        cat_filter = st.selectbox("Narrow by Category", cats, key=f"cat_{label}")
        if cat_filter != "All":
            matches = matches[matches["CATEGORY"] == cat_filter]

    if len(matches) == 0:
        st.error("No items found after filtering.")
        return None, None

    # Build readable option labels
    def make_label(r):
        parts = []
        for field in ["SERIAL NUMBER", "TAGGING NUMBER", "DESCRIPTION", "BRAND", "CATEGORY", "SIZE"]:
            val = r.get(field)
            if val and str(val).strip() not in ["-", "None", ""]:
                parts.append(f"{field.title()}: {val}")
        return " | ".join(parts) if parts else f"Row {r.name + 2}"

    options    = matches.apply(make_label, axis=1).tolist()
    chosen     = st.selectbox(
        f"{len(matches)} item(s) found — select one",
        options, key=f"pick_{label}"
    )
    idx        = options.index(chosen)
    row        = matches.iloc[idx]
    row_num    = matches.index[idx] + 2

    # Detail card
    st.markdown(f"""
    <div class="item-detail-card">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:13px;">
            <div><b>Description:</b> {row.get('DESCRIPTION') or '—'}</div>
            <div><b>Brand:</b> {row.get('BRAND') or '—'}</div>
            <div><b>Type/Spec:</b> {row.get('TYPE/SPEC') or '—'}</div>
            <div><b>Size:</b> {row.get('SIZE') or '—'}</div>
            <div><b>Serial No:</b> {row.get('SERIAL NUMBER') or '—'}</div>
            <div><b>Tagging No:</b> {row.get('TAGGING NUMBER') or '—'}</div>
            <div><b>Category:</b> {row.get('CATEGORY') or '—'}</div>
            <div><b>Remarks:</b> {row.get('REMARKS') or '—'}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    return row, row_num
# ── PDF GENERATORS ────────────────────────────────────────────────────────────
def generate_issue_pdf(data):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    import io

    buf    = io.BytesIO()
    doc    = SimpleDocTemplate(buf, pagesize=A4,
                               topMargin=10*mm, bottomMargin=10*mm,
                               leftMargin=15*mm, rightMargin=15*mm)
    styles = getSampleStyleSheet()
    story  = []

    bold   = ParagraphStyle("bold", parent=styles["Normal"], fontName="Helvetica-Bold")
    center = ParagraphStyle("center", parent=styles["Normal"], alignment=TA_CENTER)
    title  = ParagraphStyle("title", parent=styles["Normal"],
                             fontName="Helvetica-Bold", fontSize=11, alignment=TA_CENTER)
    small  = ParagraphStyle("small", parent=styles["Normal"], fontSize=8)

    # Header table
    header_data = [[
        Paragraph("<b>TURCOMP ENGINEERING SERVICES SDN. BHD.</b>", title),
        Paragraph("Form No.", small),
        Paragraph("Rev. No.", small),
    ],[
        Paragraph("<b>WAREHOUSE ISSUE FORM</b>", title),
        Paragraph("Issue Date:", small),
        Paragraph("Page No.", small),
    ]]
    ht = Table(header_data, colWidths=[120*mm, 30*mm, 30*mm])
    ht.setStyle(TableStyle([
        ("BOX",        (0,0), (-1,-1), 0.5, colors.black),
        ("INNERGRID",  (0,0), (-1,-1), 0.5, colors.black),
        ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [colors.white]),
    ]))
    story.append(ht)
    story.append(Spacer(1, 4*mm))

    # Section A — Requestor Info
    story.append(Paragraph("<b>A. REQUESTOR INFORMATION</b>", bold))
    story.append(Spacer(1, 2*mm))
    req_data = [
        ["Name", data.get("req_name",""), "Contact No", data.get("req_contact","")],
        ["Position", data.get("req_position",""), "Department", data.get("req_dept","")],
        ["Project Name", data.get("req_project",""), "Project / Job No", data.get("req_jobno","")],
        ["Usage Location", data.get("req_location",""), "", ""],
        ["Date Requested", data.get("req_date",""), "Required Return Date", data.get("req_retdate","")],
    ]
    rt = Table(req_data, colWidths=[35*mm, 65*mm, 40*mm, 40*mm])
    rt.setStyle(TableStyle([
        ("BOX",       (0,0), (-1,-1), 0.5, colors.black),
        ("INNERGRID", (0,0), (-1,-1), 0.5, colors.black),
        ("FONTNAME",  (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME",  (2,0), (2,-1), "Helvetica-Bold"),
        ("FONTSIZE",  (0,0), (-1,-1), 8),
        ("VALIGN",    (0,0), (-1,-1), "MIDDLE"),
        ("SPAN",      (1,3), (3,3)),
    ]))
    story.append(rt)
    story.append(Spacer(1, 4*mm))

    # Section B — Asset Details
    story.append(Paragraph("<b>B. ASSET ISSUE DETAILS</b>", bold))
    story.append(Spacer(1, 2*mm))

    asset_header = [["No", "Asset Tag No.", "Description", "Serial No.",
                      "Qty Issued", "Date Out", "Condition Out", "Status"]]
    items = data.get("items", [])
    for i, item in enumerate(items, 1):
        asset_header.append([
            str(i),
            str(item.get("TAGGING NUMBER","") or "-"),
            str(item.get("DESCRIPTION","") or "-"),
            str(item.get("SERIAL NUMBER","") or "-"),
            "1",
            data.get("date_out",""),
            data.get("cond_out","GOOD"),
            "Issued"
        ])
    # Add blank rows up to 10
    while len(asset_header) < 11:
        asset_header.append(["", "", "", "", "", "", "", ""])

    at = Table(asset_header, colWidths=[10*mm, 30*mm, 45*mm, 30*mm, 15*mm, 22*mm, 18*mm, 10*mm])
    at.setStyle(TableStyle([
        ("BOX",         (0,0), (-1,-1), 0.5, colors.black),
        ("INNERGRID",   (0,0), (-1,-1), 0.5, colors.black),
        ("BACKGROUND",  (0,0), (-1,0),  colors.HexColor("#1e3a5f")),
        ("TEXTCOLOR",   (0,0), (-1,0),  colors.white),
        ("FONTNAME",    (0,0), (-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",    (0,0), (-1,-1), 7.5),
        ("ALIGN",       (0,0), (-1,-1), "CENTER"),
        ("VALIGN",      (0,0), (-1,-1), "MIDDLE"),
        ("ROWHEIGHT",   (0,1), (-1,-1), 8*mm),
    ]))
    story.append(at)
    story.append(Spacer(1, 6*mm))

    # Section E — Issue Sign-Off
    story.append(Paragraph("<b>E. ISSUE SIGN-OFF</b>", bold))
    story.append(Spacer(1, 2*mm))
    sign_data = [
        [Paragraph("<b>Prepared by\n(Storekeeper)</b>", small),
         Paragraph("<b>Checked & approved by\n(Material Controller/Warehouse Coordinator)</b>", small),
         Paragraph("<b>Received by\n(Requestor/Receiver)</b>", small)],
        ["Name:\n\nSignature:\n\nDate:", "Name:\n\nSignature:\n\nDate:", "Name:\n\nSignature:\n\nDate:"],
    ]
    st_table = Table(sign_data, colWidths=[60*mm, 60*mm, 60*mm])
    st_table.setStyle(TableStyle([
        ("BOX",       (0,0), (-1,-1), 0.5, colors.black),
        ("INNERGRID", (0,0), (-1,-1), 0.5, colors.black),
        ("FONTSIZE",  (0,0), (-1,-1), 8),
        ("VALIGN",    (0,0), (-1,-1), "TOP"),
        ("ROWHEIGHT", (0,1), (-1,1),  25*mm),
    ]))
    story.append(st_table)
    story.append(Spacer(1, 4*mm))

    # Note
    story.append(Paragraph(
        "<b>Note:</b> All issued assets remain the property of the Company and must be returned "
        "in good condition. Any loss or damage must be reported immediately to the Warehouse. "
        "Lost or damaged assets may be chargeable in accordance with the Company's policy.",
        small
    ))

    doc.build(story)
    return buf.getvalue()


def generate_return_pdf(data):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    import io

    buf    = io.BytesIO()
    doc    = SimpleDocTemplate(buf, pagesize=A4,
                               topMargin=10*mm, bottomMargin=10*mm,
                               leftMargin=15*mm, rightMargin=15*mm)
    styles = getSampleStyleSheet()
    story  = []

    bold   = ParagraphStyle("bold",   parent=styles["Normal"], fontName="Helvetica-Bold")
    title  = ParagraphStyle("title",  parent=styles["Normal"],
                             fontName="Helvetica-Bold", fontSize=11, alignment=TA_CENTER)
    small  = ParagraphStyle("small",  parent=styles["Normal"], fontSize=8)

    # Header
    header_data = [[
        Paragraph("<b>TURCOMP ENGINEERING SERVICES SDN. BHD.</b>", title),
        Paragraph("Form No.", small),
        Paragraph("Rev. No.", small),
    ],[
        Paragraph("<b>WAREHOUSE RETURN FORM</b>", title),
        Paragraph("Issue Date:", small),
        Paragraph("Page No.", small),
    ]]
    ht = Table(header_data, colWidths=[120*mm, 30*mm, 30*mm])
    ht.setStyle(TableStyle([
        ("BOX",       (0,0), (-1,-1), 0.5, colors.black),
        ("INNERGRID", (0,0), (-1,-1), 0.5, colors.black),
        ("VALIGN",    (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(ht)
    story.append(Spacer(1, 4*mm))

    # Requestor info
    story.append(Paragraph("<b>A. REQUESTOR INFORMATION</b>", bold))
    story.append(Spacer(1, 2*mm))
    req_data = [
        ["Name", data.get("req_name",""), "Project / Job No", data.get("req_jobno","")],
        ["Project Name", data.get("req_project",""), "Usage Location", data.get("req_location","")],
        ["Date Out", data.get("date_out",""), "Date Returned", data.get("date_ret","")],
    ]
    rt = Table(req_data, colWidths=[35*mm, 65*mm, 40*mm, 40*mm])
    rt.setStyle(TableStyle([
        ("BOX",       (0,0), (-1,-1), 0.5, colors.black),
        ("INNERGRID", (0,0), (-1,-1), 0.5, colors.black),
        ("FONTNAME",  (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME",  (2,0), (2,-1), "Helvetica-Bold"),
        ("FONTSIZE",  (0,0), (-1,-1), 8),
        ("VALIGN",    (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(rt)
    story.append(Spacer(1, 4*mm))

    # Asset return details
    story.append(Paragraph("<b>B. ASSET RETURN DETAILS</b>", bold))
    story.append(Spacer(1, 2*mm))
    asset_header = [["No", "Asset Tag No.", "Description", "Serial No.",
                      "Qty Returned", "Condition Out", "Condition Returned", "Status"]]
    items = data.get("items", [])
    for i, item in enumerate(items, 1):
        asset_header.append([
            str(i),
            str(item.get("TAGGING NUMBER","") or "-"),
            str(item.get("DESCRIPTION","") or "-"),
            str(item.get("SERIAL NUMBER","") or "-"),
            "1",
            str(item.get("CONDITION OUT","") or "-"),
            data.get("cond_ret",""),
            data.get("ret_status","FULLY RETURNED"),
        ])
    while len(asset_header) < 11:
        asset_header.append(["","","","","","","",""])

    at = Table(asset_header, colWidths=[10*mm, 28*mm, 42*mm, 28*mm, 15*mm, 22*mm, 22*mm, 13*mm])
    at.setStyle(TableStyle([
        ("BOX",        (0,0), (-1,-1), 0.5, colors.black),
        ("INNERGRID",  (0,0), (-1,-1), 0.5, colors.black),
        ("BACKGROUND", (0,0), (-1,0),  colors.HexColor("#1e3a5f")),
        ("TEXTCOLOR",  (0,0), (-1,0),  colors.white),
        ("FONTNAME",   (0,0), (-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",   (0,0), (-1,-1), 7.5),
        ("ALIGN",      (0,0), (-1,-1), "CENTER"),
        ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
        ("ROWHEIGHT",  (0,1), (-1,-1), 8*mm),
    ]))
    story.append(at)
    story.append(Spacer(1, 4*mm))

    # Remarks
    story.append(Paragraph("<b>C. REMARKS / DISCREPANCIES</b>", bold))
    rem_table = Table([[data.get("remarks","")]], colWidths=[180*mm])
    rem_table.setStyle(TableStyle([
        ("BOX",      (0,0), (-1,-1), 0.5, colors.black),
        ("FONTSIZE", (0,0), (-1,-1), 8),
        ("MINROWHEIGHT", (0,0), (-1,-1), 20*mm),
    ]))
    story.append(rem_table)
    story.append(Spacer(1, 4*mm))

    # Overall return status
    story.append(Paragraph("<b>G. OVERALL RETURN STATUS</b>", bold))
    status_options = ["Fully Returned","Partially Returned","Outstanding","Damaged","Lost"]
    ret_stat = data.get("ret_status","FULLY RETURNED").title()
    status_row = [f"☑ {s}" if s == ret_stat else f"☐ {s}" for s in status_options]
    st2 = Table([status_row], colWidths=[36*mm]*5)
    st2.setStyle(TableStyle([
        ("BOX",      (0,0), (-1,-1), 0.5, colors.black),
        ("FONTSIZE", (0,0), (-1,-1), 8),
        ("ALIGN",    (0,0), (-1,-1), "CENTER"),
    ]))
    story.append(st2)
    story.append(Spacer(1, 4*mm))

    # Return sign-off
    story.append(Paragraph("<b>F. RETURN SIGN-OFF</b>", bold))
    story.append(Spacer(1, 2*mm))
    sign_data = [
        [Paragraph("<b>Returned by\n(Requestor)</b>", small),
         Paragraph("<b>Received by\n(Storekeeper)</b>", small),
         Paragraph("<b>Verified by\n(Material Controller/Warehouse Coordinator)</b>", small)],
        ["Name:\n\nSignature:\n\nDate:", "Name:\n\nSignature:\n\nDate:", "Name:\n\nSignature:\n\nDate:"],
    ]
    st3 = Table(sign_data, colWidths=[60*mm, 60*mm, 60*mm])
    st3.setStyle(TableStyle([
        ("BOX",       (0,0), (-1,-1), 0.5, colors.black),
        ("INNERGRID", (0,0), (-1,-1), 0.5, colors.black),
        ("FONTSIZE",  (0,0), (-1,-1), 8),
        ("VALIGN",    (0,0), (-1,-1), "TOP"),
        ("ROWHEIGHT", (0,1), (-1,1),  25*mm),
    ]))
    story.append(st3)
    story.append(Spacer(1, 4*mm))

    story.append(Paragraph(
        "<b>Note:</b> All issued assets remain the property of the Company and must be returned "
        "in good condition. Any loss or damage must be reported immediately to the Warehouse.",
        small
    ))

    doc.build(story)
    return buf.getvalue()

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="padding:16px 0 24px;border-bottom:1px solid #1e3a5f;margin-bottom:20px;">
        <div style="font-size:20px;font-weight:700;color:#ffffff;letter-spacing:0.5px;">
            📦 TURCOMP
        </div>
        <div style="font-size:11px;color:#64748b;margin-top:2px;">
            Inventory Management System
        </div>
    </div>
    """, unsafe_allow_html=True)
    page = st.radio("", [
        "📊 Dashboard",
        "📋 Ledger & Export",
        "✏️ Management",
        "🔄 Loan Tracker"
    ], label_visibility="collapsed")
    st.markdown(f"""
    <div style="position:fixed;bottom:20px;font-size:11px;color:#475569;">
        Last refreshed<br>{datetime.now().strftime('%b %d, %Y %I:%M %p')}
    </div>
    """, unsafe_allow_html=True)

df = load_data()

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 1 — DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
if page == "📊 Dashboard":
    col_title, col_filter = st.columns([3, 1])
    with col_title:
        st.markdown("## Dashboard")
        st.caption("Overview of inventory performance")
    with col_filter:
        cats     = ["All Categories"] + sorted(df["CATEGORY"].dropna().unique().tolist())
        selected = st.selectbox("Category Filter", cats, label_visibility="collapsed")

    dff = df if selected == "All Categories" else df[df["CATEGORY"] == selected]

    total     = len(dff)
    total_qty = int(dff["QUANTITY"].sum())
    out_count = int((dff["STATUS"].fillna("").str.upper() == "OUT").sum())
    available = int((dff["STATUS"].fillna("").str.upper() == "AVAILABLE").sum())

    # ── KPI CARDS ─────────────────────────────────────────────────────────────
    k1, k2, k3, k4 = st.columns(4)
    kpis = [
        (k1, "📦", "#eff6ff", "Total Items",    f"{total:,}",     "Total rows"),
        (k2, "🗂️", "#f0fdf4", "Total Quantity", f"{total_qty:,}", "Sum of quantity"),
        (k3, "📤", "#fff7ed", "Currently Out",  f"{out_count:,}", "Items on loan"),
        (k4, "✅", "#f0fdf4", "Available",      f"{available:,}", "Items available"),
    ]
    for col, icon, bg, label, val, sub in kpis:
        with col:
            st.markdown(f"""
            <div class="kpi-card">
                <div class="kpi-icon" style="background:{bg}">{icon}</div>
                <div>
                    <div class="kpi-label">{label}</div>
                    <div class="kpi-value">{val}</div>
                    <div class="kpi-sub">{sub}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    # ── CONDITION PILLS ────────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Condition Summary</div>', unsafe_allow_html=True)
    cond_series = dff["ACTUAL CONDITION"].fillna("UNKNOWN").str.upper()
    cond_counts = cond_series.value_counts().to_dict()

    pill_cols = st.columns(7)
    for i, cond in enumerate(CONDITION_FULL_OPTIONS):
        count       = cond_counts.get(cond, 0)
        icon, bg, fg = PILL_STYLE.get(cond, ("⚫", "#f1f5f9", "#334155"))
        with pill_cols[i]:
            st.markdown(f"""
            <div class="cond-pill" style="background:{bg};color:{fg};">
                <div style="font-size:11px;margin-bottom:4px;">{cond}</div>
                <div style="font-size:22px;font-weight:700;">{count:,}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")

    # ── CHARTS ROW 1: Treemap + Bar ────────────────────────────────────────────
    cat_summary = (
        dff.groupby("CATEGORY")
        .agg(Count=("DESCRIPTION", "count"),
             Quantity=("QUANTITY", "sum"))
        .reset_index()
    )

    c_left, c_mid, c_right = st.columns([1.2, 1, 1])

    with c_left:
        st.markdown('<div class="section-title">Items by Category (Treemap)</div>', unsafe_allow_html=True)
        fig_tree = px.treemap(
            cat_summary, path=["CATEGORY"], values="Count",
            custom_data=["Count", "Quantity"],
            color="Count", color_continuous_scale="Blues"
        )
        fig_tree.update_traces(
            texttemplate="<b>%{label}</b><br>%{customdata[0]}<br>(%{percentRoot:.1%})",
            hovertemplate="<b>%{label}</b><br>Items: %{customdata[0]}<br>Qty: %{customdata[1]}<extra></extra>",
            textfont_size=12
        )
        fig_tree.update_layout(
            margin=dict(t=0,l=0,r=0,b=0), height=260,
            coloraxis_showscale=False
        )
        st.plotly_chart(fig_tree, width='stretch')

    with c_mid:
        st.markdown('<div class="section-title">Quantity per Category</div>', unsafe_allow_html=True)
        fig_bar = px.bar(
            cat_summary.sort_values("Quantity", ascending=True),
            x="Quantity", y="CATEGORY", orientation="h",
            text="Quantity", color_discrete_sequence=["#2563eb"]
        )
        fig_bar.update_traces(texttemplate="%{text:,}", textposition="outside")
        fig_bar.update_layout(
            margin=dict(t=0,l=0,r=40,b=0), height=260,
            yaxis_title="", xaxis_title="",
            plot_bgcolor="white", paper_bgcolor="white",
            xaxis=dict(showgrid=True, gridcolor="#f1f5f9"),
            yaxis=dict(tickfont=dict(size=10))
        )
        st.plotly_chart(fig_bar, width='stretch')

    with c_right:
        st.markdown('<div class="section-title">Condition Breakdown</div>', unsafe_allow_html=True)
        cond_df = (
            dff["ACTUAL CONDITION"].fillna("UNKNOWN").str.upper()
            .value_counts().reset_index()
        )
        cond_df.columns = ["Condition", "Count"]
        fig_donut = go.Figure(go.Pie(
            labels=cond_df["Condition"], values=cond_df["Count"],
            hole=0.6,
            marker_colors=[COLOR_MAP_COND.get(c, "#B4B2A9") for c in cond_df["Condition"]],
            textinfo="percent",
            hovertemplate="%{label}: %{value} items (%{percent})<extra></extra>"
        ))
        fig_donut.add_annotation(
            text=f"<b>{total:,}</b><br><span style='font-size:10px'>Total Items</span>",
            x=0.5, y=0.5, showarrow=False, font_size=14
        )
        fig_donut.update_layout(
            margin=dict(t=0,l=0,r=0,b=0), height=260,
            legend=dict(font=dict(size=10), orientation="v", x=1, y=0.5),
            showlegend=True
        )
        st.plotly_chart(fig_donut, width='stretch')

    # ── LOAN STATUS ────────────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Loan Status Overview</div>', unsafe_allow_html=True)
    stat_df = (
        dff["STATUS"].fillna("NOT SET").str.upper()
        .value_counts().reset_index()
    )
    stat_df.columns = ["Status", "Count"]
    stat_color = {
        "AVAILABLE":         "#16a34a",
        "OUT":               "#d97706",
        "RETURNED":          "#2563eb",
        "UNDER MAINTENANCE": "#dc2626",
        "NOT SET":           "#94a3b8",
    }
    fig_stat = px.bar(
        stat_df, x="Status", y="Count",
        color="Status",
        color_discrete_map=stat_color,
        text="Count"
    )
    fig_stat.update_traces(textposition="outside")
    fig_stat.update_layout(
        margin=dict(t=10,l=0,r=0,b=0), height=240,
        showlegend=False, plot_bgcolor="white", paper_bgcolor="white",
        yaxis=dict(showgrid=True, gridcolor="#f1f5f9"),
        xaxis_title="", yaxis_title="Number of Items"
    )
    st.plotly_chart(fig_stat, width='stretch')

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 2 — LEDGER & EXPORT
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📋 Ledger & Export":
    st.markdown("## Inventory Ledger & Export")

    f1, f2, f3, f4 = st.columns([2.5, 1.5, 1.5, 1])
    with f1:
        search = st.text_input("🔍 Search Brand, Model, Serial...", label_visibility="collapsed",
                               placeholder="Search Brand, Model, Serial...")
    with f2:
        cats  = ["All"] + sorted(df["CATEGORY"].dropna().unique().tolist())
        cat_f = st.selectbox("Category", cats, label_visibility="collapsed")
    with f3:
        stat_f = st.selectbox("Status", ["All Statuses"] + STATUS_OPTIONS,
                              label_visibility="collapsed")
    with f4:
        st.markdown("<br>", unsafe_allow_html=True)

    dff = df.copy()
    if cat_f  != "All":
        dff = dff[dff["CATEGORY"] == cat_f]
    if stat_f != "All Statuses":
        dff = dff[dff["STATUS"].fillna("").str.upper() == stat_f]
    if search:
        mask = dff.apply(
            lambda r: r.astype(str).str.contains(search, case=False, na=False).any(), axis=1
        )
        dff = dff[mask]

    csv = dff.to_csv(index=False).encode("utf-8")
    f1b, f2b, f3b, f4b = st.columns([2.5, 1.5, 1.5, 1])
    with f1b:
        st.caption(f"Showing {len(dff):,} of {len(df):,} items")
    with f4b:
        st.download_button(
            "⬇️ Download CSV", data=csv,
            file_name=f"inventory_{cat_f}_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv", type="primary"
        )

    def highlight_row(row):
        cond   = str(row.get("ACTUAL CONDITION","")).upper()
        status = str(row.get("STATUS","")).upper()
        if cond in ["DAMAGED","DAMAGED (NOT WORKING)","LOST"]:
            return ["background-color:#fff0f0"] * len(row)
        if status == "OUT":
            return ["background-color:#fffbeb"] * len(row)
        if cond in ["DAMAGED (WORKING)","MINOR ISSUE","SERVICE DUE"]:
            return ["background-color:#fff7ed"] * len(row)
        return [""] * len(row)

    display_cols = [c for c in dff.columns if c != "NO"]
    st.dataframe(
        dff[display_cols].style.apply(highlight_row, axis=1),
        height=560, width='stretch'
    )

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 3 — MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════
elif page == "✏️ Management":
    st.markdown("## Inventory Management")
    ws   = get_worksheet()
    tab1, tab2, tab3 = st.tabs(["➕ Add New Item", "🔧 Edit Existing Item", "🗑️ Delete Item"])

    # ── TAB 1: ADD ─────────────────────────────────────────────────────────────
    with tab1:
        with st.form("add_form"):
            st.markdown("#### New Item Details")
            c1, c2 = st.columns(2)
            with c1:
                no          = st.number_input("NO", min_value=1, value=int(df["NO"].max())+1)
                category    = st.selectbox("Category", [""] + sorted(df["CATEGORY"].dropna().unique().tolist()))
                type_spec   = st.text_input("Type/Spec")
                brand       = st.text_input("Brand")
                model       = st.text_input("Model")
                serial      = st.text_input("Serial Number", placeholder="Optional")
                tagging     = st.text_input("Tagging Number")
                description = st.text_input("Description ✱", placeholder="Required")
            with c2:
                size        = st.text_input("Size")
                watt        = st.text_input("Watt")
                thickness   = st.text_input("Thickness")
                quantity    = st.number_input("Quantity", min_value=0, value=1)
                uom         = st.text_input("UOM", value="UNIT")
                storage_loc = st.text_input("Storage Location")
                condition   = st.selectbox("Actual Condition", CONDITION_FULL_OPTIONS)
                remarks     = st.text_input("Remarks")

            st.info("ℹ️ New items will be automatically set to STATUS = AVAILABLE")

            if st.form_submit_button("➕ Add Item", type="primary"):
                if not description:
                    st.error("❌ Description is required.")
                elif serial and serial in df["SERIAL NUMBER"].fillna("").astype(str).values:
                    st.error(f"❌ Serial Number '{serial}' already exists.")
                else:
                    ws.append_row([
                        no, category, type_spec, brand, model,
                        serial, tagging, description, size, watt, thickness,
                        quantity, uom, storage_loc, condition,
                        "", "", "", "", "", "", "", "", "AVAILABLE", remarks
                    ])
                    st.success(f"✅ Item added at {datetime.now().strftime('%Y-%m-%d %H:%M')}")
                    reload()

    # ── TAB 2: EDIT ─────────────────────────────────────────────────────────────
    with tab2:
        st.markdown("#### Find & Edit Item")
        row, row_num = search_item(df, label="edit")

        if row is not None:
            with st.form("edit_form"):
                st.markdown("**Inventory Details**")
                c1, c2 = st.columns(2)
                with c1:
                    e_no = st.number_input("NO", value=int(row.get("NO") or 0), min_value=0)
                    e_cat    = st.text_input("Category",        value=str(row.get("CATEGORY")     or ""))
                    e_type   = st.text_input("Type/Spec",       value=str(row.get("TYPE/SPEC")    or ""))
                    e_brand  = st.text_input("Brand",           value=str(row.get("BRAND")        or ""))
                    e_model  = st.text_input("Model",           value=str(row.get("MODEL")        or ""))
                    e_serial = st.text_input("Serial Number",   value=str(row.get("SERIAL NUMBER")or ""))
                    e_tag    = st.text_input("Tagging Number",  value=str(row.get("TAGGING NUMBER")or ""))
                    e_desc   = st.text_input("Description",     value=str(row.get("DESCRIPTION")  or ""))
                with c2:
                    e_size   = st.text_input("Size",            value=str(row.get("SIZE")         or ""))
                    e_watt   = st.text_input("Watt",            value=str(row.get("WATT")         or ""))
                    e_thick  = st.text_input("Thickness",       value=str(row.get("THICKNESS")    or ""))
                    e_qty    = st.number_input("Quantity",      value=int(row.get("QUANTITY")     or 0))
                    e_uom    = st.text_input("UOM",             value=str(row.get("UOM")          or ""))
                    e_stor   = st.text_input("Storage Location",value=str(row.get("STORAGE LOCATION") or ""))
                    cur_ac   = str(row.get("ACTUAL CONDITION","GOOD")).upper()
                    ac_idx   = CONDITION_FULL_OPTIONS.index(cur_ac) if cur_ac in CONDITION_FULL_OPTIONS else 0
                    e_cond   = st.selectbox("Actual Condition", CONDITION_FULL_OPTIONS, index=ac_idx)
                    e_rem    = st.text_input("Remarks",         value=str(row.get("REMARKS")      or ""))

                st.markdown("---")
                st.markdown("**Loan Status (Admin Override)**")
                a1, a2 = st.columns(2)
                with a1:
                    cur_stat = str(row.get("STATUS","AVAILABLE")).upper()
                    st._idx  = STATUS_OPTIONS.index(cur_stat) if cur_stat in STATUS_OPTIONS else 0
                    e_status = st.selectbox("Status", STATUS_OPTIONS, index=st._idx)
                    e_dateout= st.text_input("Date Out",       value=str(row.get("DATE OUT")      or ""))
                    e_dateret= st.text_input("Date Returned",  value=str(row.get("DATE RETURNED") or ""))
                    e_jobno  = st.text_input("Job No",         value=str(row.get("JOB NO")        or ""))
                with a2:
                    e_req    = st.text_input("Requestor",      value=str(row.get("REQUESTOR")     or ""))
                    e_proj   = st.text_input("Project/Usage",  value=str(row.get("PROJECT / USAGE") or ""))
                    e_loc    = st.text_input("Location",       value=str(row.get("LOCATION")      or ""))
                    cur_co   = str(row.get("CONDITION OUT","GOOD")).upper()
                    co_idx   = CONDITION_OUT_OPTIONS.index(cur_co) if cur_co in CONDITION_OUT_OPTIONS else 0
                    e_co     = st.selectbox("Condition Out", CONDITION_OUT_OPTIONS, index=co_idx)
                    cur_cr   = str(row.get("CONDITION RETURNED","GOOD")).upper()
                    cr_idx   = CONDITION_FULL_OPTIONS.index(cur_cr) if cur_cr in CONDITION_FULL_OPTIONS else 0
                    e_cr     = st.selectbox("Condition Returned", CONDITION_FULL_OPTIONS, index=cr_idx)

                if st.form_submit_button("💾 Save All Changes", type="primary"):
                    updated = [
                        e_no, e_cat, e_type, e_brand, e_model,
                        e_serial, e_tag, e_desc, e_size, e_watt, e_thick,
                        e_qty, e_uom, e_stor, e_cond,
                        e_dateout, e_dateret, e_req, e_proj,
                        e_loc, e_co, e_cr, e_jobno, e_status, e_rem
                    ]
                    ws.update(f"A{row_num}:Y{row_num}", [updated])
                    st.success(f"✅ Saved at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    reload()

    # ── TAB 3: DELETE ─────────────────────────────────────────────────────────
    with tab3:
        st.markdown("#### Delete Item")
        st.warning("⚠️ Deleted rows are **permanently removed** from the Google Sheet and cannot be recovered.")
        row, row_num = search_item(df, label="delete")

        if row is not None:
            st.error(f"""
            **You are about to permanently delete this item:**

            - Description: {row.get('DESCRIPTION','—')}
            - Serial Number: {row.get('SERIAL NUMBER','—')}
            - Tagging Number: {row.get('TAGGING NUMBER','—')}
            - Category: {row.get('CATEGORY','—')}
            - Current Status: {row.get('STATUS','—')}
            """)

            confirm = st.checkbox("I understand this action is permanent and cannot be undone")
            if confirm:
                if st.button("🗑️ Permanently Delete This Item", type="primary"):
                    ws.delete_rows(row_num)
                    st.success("✅ Item deleted successfully.")
                    reload()

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 4 — LOAN TRACKER
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🔄 Loan Tracker":
    st.markdown("## Loan Tracker")
    ws   = get_worksheet()
    tab1, tab2, tab3 = st.tabs([
        "🚚 Issue Items Out",
        "✅ Return Item",
        "📋 Currently Out"
    ])

    # ── TAB 1: BULK ISSUE OUT ─────────────────────────────────────────────────
    with tab1:
        st.markdown("#### Step 1 — Requestor Information")
        ri1, ri2 = st.columns(2)
        with ri1:
            req_name     = st.text_input("Name ✱")
            req_position = st.text_input("Position")
            req_project  = st.text_input("Project Name")
            req_location = st.text_input("Usage Location")
        with ri2:
            req_contact  = st.text_input("Contact No")
            req_dept     = st.text_input("Department")
            req_jobno    = st.text_input("Project / Job No ✱")
            req_date     = st.date_input("Date Requested", value=datetime.today())
            req_retdate  = st.date_input("Required Return Date")

        st.markdown("---")
        st.markdown("#### Step 2 — Select Items to Issue")

        # Filter helpers
        fc1, fc2 = st.columns(2)
        with fc1:
            filter_cat = st.selectbox(
                "Filter by Category",
                ["All"] + sorted(df["CATEGORY"].dropna().unique().tolist()),
                key="issue_cat_filter"
            )
        with fc2:
            filter_search = st.text_input("Search Description / Serial / Tagging", key="issue_search")

        available_df = df[df["STATUS"].fillna("").str.upper().isin(["AVAILABLE", ""])]
        if filter_cat != "All":
            available_df = available_df[available_df["CATEGORY"] == filter_cat]
        if filter_search:
            mask = available_df.apply(
                lambda r: r.astype(str).str.contains(filter_search, case=False, na=False).any(), axis=1
            )
            available_df = available_df[mask]

        if available_df.empty:
            st.info("No available items matching your filter.")
        else:
            st.caption(f"{len(available_df)} available items shown")

            # Build checkbox table
            show_cols = ["CATEGORY", "TAGGING NUMBER", "DESCRIPTION",
                        "SERIAL NUMBER", "BRAND", "SIZE", "ACTUAL CONDITION"]
            show_cols = [c for c in show_cols if c in available_df.columns]

            selected_indices = []
            header_cols = st.columns([0.3] + [1] * len(show_cols))
            header_cols[0].markdown("**✓**")
            for i, col in enumerate(show_cols):
                header_cols[i+1].markdown(f"**{col}**")

            st.markdown("<hr style='margin:4px 0'>", unsafe_allow_html=True)

            for idx, row_data in available_df.iterrows():
                row_cols = st.columns([0.3] + [1] * len(show_cols))
                checked = row_cols[0].checkbox(
                    "", key=f"chk_{idx}", label_visibility="collapsed"
                )
                for i, col in enumerate(show_cols):
                    val = str(row_data.get(col, "") or "")
                    row_cols[i+1].caption(val if val not in ["None","nan",""] else "-")
                if checked:
                    selected_indices.append(idx)

        st.markdown("---")
        st.markdown(f"#### Step 3 — Issue Out ({len(selected_indices) if 'selected_indices' in dir() else 0} items selected)")

        if selected_indices:
            selected_items = df.loc[selected_indices]
            st.success(f"✅ {len(selected_indices)} item(s) selected")

            # Show summary
            sum_cols = ["TAGGING NUMBER", "DESCRIPTION", "SERIAL NUMBER"]
            sum_cols = [c for c in sum_cols if c in selected_items.columns]
            st.dataframe(selected_items[sum_cols], use_container_width=True)

            ic1, ic2 = st.columns(2)
            with ic1:
                date_out = st.date_input("Date Out", value=datetime.today(), key="bulk_date_out")
            with ic2:
                cond_out = st.selectbox("Condition Out (applies to all)", CONDITION_OUT_OPTIONS, key="bulk_cond_out")

            col_issue, col_pdf = st.columns(2)

            with col_issue:
                if st.button("🚚 Issue All Selected Items", type="primary"):
                    if not req_name:
                        st.error("❌ Requestor name is required.")
                    elif not req_jobno:
                        st.error("❌ Job No is required.")
                    else:
                        errors = []
                        for idx in selected_indices:
                            row_data = df.loc[idx]
                            row_num  = idx + 2
                            try:
                                ws.update(f"P{row_num}:Y{row_num}", [[
                                    str(date_out), "",
                                    req_name, req_project,
                                    req_location, cond_out,
                                    "", req_jobno,
                                    "OUT", str(row_data.get("REMARKS","") or "")
                                ]])
                            except Exception as e:
                                errors.append(str(e))
                        if errors:
                            st.error(f"Some items failed: {errors}")
                        else:
                            st.success(f"✅ {len(selected_indices)} items issued to {req_name} | Job: {req_jobno}")
                            reload()

            with col_pdf:
                if st.button("📄 Preview & Download Issue Form PDF"):
                    if not req_name:
                        st.error("❌ Fill in requestor name first.")
                    elif not req_jobno:
                        st.error("❌ Fill in Job No first.")
                    elif not selected_indices:
                        st.error("❌ Select at least one item.")
                    else:
                        st.session_state["pdf_preview"] = {
                            "type": "issue",
                            "req_name": req_name,
                            "req_contact": req_contact,
                            "req_position": req_position,
                            "req_dept": req_dept,
                            "req_project": req_project,
                            "req_jobno": req_jobno,
                            "req_location": req_location,
                            "req_date": str(req_date),
                            "req_retdate": str(req_retdate),
                            "date_out": str(date_out),
                            "cond_out": cond_out,
                            "items": df.loc[selected_indices].to_dict("records")
                        }
                        st.rerun()

        # ── PDF PREVIEW MODAL ─────────────────────────────────────────────────
        if "pdf_preview" in st.session_state and st.session_state["pdf_preview"]:
            data = st.session_state["pdf_preview"]
            st.markdown("---")
            st.markdown("### 📋 Confirm Before Downloading")

            st.markdown(f"""
            **Requestor:** {data['req_name']} | **Job No:** {data['req_jobno']}
            **Project:** {data['req_project']} | **Date Out:** {data['date_out']}
            """)

            st.markdown("**Items to be issued:**")
            preview_df = pd.DataFrame(data["items"])
            pcols = ["TAGGING NUMBER","DESCRIPTION","SERIAL NUMBER","ACTUAL CONDITION"]
            pcols = [c for c in pcols if c in preview_df.columns]
            st.dataframe(preview_df[pcols], use_container_width=True)

            pc1, pc2 = st.columns(2)
            with pc1:
                if st.button("✅ Details Correct — Download PDF", type="primary"):
                    pdf_bytes = generate_issue_pdf(data)
                    st.download_button(
                        label="⬇️ Download Issue Form PDF",
                        data=pdf_bytes,
                        file_name=f"Issue_Form_{data['req_name']}_{data['date_out']}.pdf",
                        mime="application/pdf"
                    )
            with pc2:
                if st.button("❌ Go Back & Correct"):
                    del st.session_state["pdf_preview"]
                    st.rerun()

    # ── TAB 2: RETURN ─────────────────────────────────────────────────────────
    with tab2:
        c_search, c_form = st.columns([1, 1])
        with c_search:
            st.markdown("#### Find Item to Return")
            row, row_num = search_item(df, label="return")

        with c_form:
            if row is not None:
                if str(row.get("STATUS","")).upper() not in ["OUT", "PARTIALLY RETURNED"]:
                    st.warning("⚠️ This item is not currently OUT.")
                else:
                    st.markdown("#### Return Details")
                    st.info(
                        f"Borrowed by **{row.get('REQUESTOR','')}** | "
                        f"Job: **{row.get('JOB NO','')}** | "
                        f"Out since: {row.get('DATE OUT','')}"
                    )
                    with st.form("return_form"):
                        date_ret  = st.date_input("Date Returned", value=datetime.today())
                        ret_status = st.selectbox("Return Status", RETURN_STATUS_OPTIONS)
                        cur_cr    = str(row.get("CONDITION RETURNED","GOOD")).upper()
                        cr_idx    = CONDITION_FULL_OPTIONS.index(cur_cr) if cur_cr in CONDITION_FULL_OPTIONS else 0
                        cond_ret  = st.selectbox("Condition Returned", CONDITION_FULL_OPTIONS, index=cr_idx)
                        cur_ac    = str(row.get("ACTUAL CONDITION","GOOD")).upper()
                        ac_idx    = CONDITION_FULL_OPTIONS.index(cur_ac) if cur_ac in CONDITION_FULL_OPTIONS else 0
                        new_cond  = st.selectbox("Update Actual Condition", CONDITION_FULL_OPTIONS, index=ac_idx)
                        remarks   = st.text_input("Remarks", value=str(row.get("REMARKS","") or ""))

                        # Map return status to inventory status
                        status_map = {
                            "FULLY RETURNED":     "AVAILABLE",
                            "PARTIALLY RETURNED": "PARTIALLY RETURNED",
                            "LOST":               "LOST",
                            "DAMAGED":            "AVAILABLE",
                            "OUTSTANDING":        "OUT",
                        }
                        new_status = status_map.get(ret_status, "AVAILABLE")

                        rc1, rc2 = st.columns(2)
                        submit_ret = rc1.form_submit_button("✅ Confirm Return", type="primary")
                        pdf_ret    = rc2.form_submit_button("📄 Return Form PDF")

                        if submit_ret:
                            ws.update(f"P{row_num}:Y{row_num}", [[
                                str(row.get("DATE OUT","")), str(date_ret),
                                row.get("REQUESTOR",""), row.get("PROJECT / USAGE",""),
                                row.get("LOCATION",""), row.get("CONDITION OUT",""),
                                cond_ret, row.get("JOB NO",""),
                                new_status, remarks
                            ]])
                            ws.update(f"O{row_num}", [[new_cond]])
                            st.success(f"✅ Returned | Status: {ret_status} | Condition: {cond_ret}")
                            reload()

                        if pdf_ret:
                            ret_pdf_data = {
                                "type": "return",
                                "req_name":    row.get("REQUESTOR",""),
                                "req_jobno":   row.get("JOB NO",""),
                                "req_project": row.get("PROJECT / USAGE",""),
                                "req_location":row.get("LOCATION",""),
                                "date_out":    str(row.get("DATE OUT","")),
                                "date_ret":    str(date_ret),
                                "ret_status":  ret_status,
                                "cond_ret":    cond_ret,
                                "remarks":     remarks,
                                "items": [row.to_dict()]
                            }
                            pdf_bytes = generate_return_pdf(ret_pdf_data)
                            st.download_button(
                                label="⬇️ Download Return Form PDF",
                                data=pdf_bytes,
                                file_name=f"Return_Form_{row.get('REQUESTOR','')}_{date_ret}.pdf",
                                mime="application/pdf"
                            )

    # ── TAB 3: CURRENTLY OUT ──────────────────────────────────────────────────
    with tab3:
        out_df = df[df["STATUS"].fillna("").str.upper().isin(["OUT","PARTIALLY RETURNED"])]
        if out_df.empty:
            st.info("✅ No items currently out on loan.")
        else:
            st.markdown(f"#### {len(out_df)} Items Currently Out")
            show_cols = [c for c in [
                "TAGGING NUMBER","DESCRIPTION","SERIAL NUMBER","CATEGORY",
                "BRAND","REQUESTOR","JOB NO","DATE OUT",
                "PROJECT / USAGE","LOCATION","CONDITION OUT","STATUS"
            ] if c in out_df.columns]
            st.dataframe(out_df[show_cols], height=500, width='stretch')