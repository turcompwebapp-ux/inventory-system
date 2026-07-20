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
    "GOOD", "DAMAGED", "DAMAGED (NOT WORKING)",
    "DAMAGED (WORKING)", "LOST", "MINOR ISSUE", "SERVICE DUE"
]
STATUS_OPTIONS = ["AVAILABLE", "OUT", "RETURNED", "UNDER MAINTENANCE"]
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
    "DAMAGED":               ("🔴", "#fef2f2", "#991b1b"),
    "DAMAGED (NOT WORKING)": ("🔴", "#fef2f2", "#991b1b"),
    "DAMAGED (WORKING)":     ("🟠", "#fff7ed", "#9a3412"),
    "LOST":                  ("🟣", "#f5f3ff", "#5b21b6"),
    "MINOR ISSUE":           ("🔵", "#eff6ff", "#1e40af"),
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
    # value_render_option="FORMATTED_VALUE" keeps leading zeros as strings
    data = ws.get_all_records(
        value_render_option="FORMATTED_VALUE",
        expected_headers=[]
    )
    df = pd.DataFrame(data)
    df = df.replace("", None)
    df["QUANTITY"] = pd.to_numeric(df["QUANTITY"], errors="coerce").fillna(0)
    # Force identifier columns to plain string
    for col in ["SERIAL NUMBER", "TAGGING NUMBER", "MODEL", "NO"]:
        if col in df.columns:
            df[col] = df[col].apply(
                lambda x: str(int(float(x))) if str(x).replace('.','').isdigit() else str(x)
            ).replace("None", "").replace("nan", "")
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

    st.dataframe(
        dff.style.apply(highlight_row, axis=1),
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
    tab1, tab2, tab3 = st.tabs(["🚚 Issue Item Out", "✅ Return Item", "📋 Currently Out"])

    # ── TAB 1: ISSUE OUT ──────────────────────────────────────────────────────
    with tab1:
        c_search, c_form = st.columns([1, 1])
        with c_search:
            st.markdown("#### Find Item to Issue")
            row, row_num = search_item(df, label="issue_out")

        with c_form:
            if row is not None:
                if str(row.get("STATUS","")).upper() == "OUT":
                    st.warning("⚠️ This item is already OUT on loan.")
                else:
                    st.markdown("#### Issue Details")
                    with st.form("out_form"):
                        date_out  = st.date_input("Date Out", value=datetime.today())
                        requestor = st.text_input("Requestor Name ✱")
                        job_no    = st.text_input("Job No ✱")
                        project   = st.text_input("Project / Usage")
                        location  = st.text_input("Location")
                        cur_co    = str(row.get("ACTUAL CONDITION","GOOD")).upper()
                        co_idx    = CONDITION_OUT_OPTIONS.index(cur_co) if cur_co in CONDITION_OUT_OPTIONS else 0
                        cond_out  = st.selectbox("Condition Out", CONDITION_OUT_OPTIONS, index=co_idx)

                        if st.form_submit_button("🚚 Issue Out", type="primary"):
                            if not requestor:
                                st.error("❌ Requestor name is required.")
                            elif not job_no:
                                st.error("❌ Job No is required.")
                            else:
                                ws.update(f"P{row_num}:Y{row_num}", [[
                                    str(date_out), "", requestor, project,
                                    location, cond_out, "", job_no,
                                    "OUT", str(row.get("REMARKS","") or "")
                                ]])
                                st.success(f"✅ Issued to **{requestor}** | Job: {job_no} | {date_out}")
                                reload()

    # ── TAB 2: RETURN ─────────────────────────────────────────────────────────
    with tab2:
        c_search, c_form = st.columns([1, 1])
        with c_search:
            st.markdown("#### Find Item to Return")
            row, row_num = search_item(df, label="return")

        with c_form:
            if row is not None:
                if str(row.get("STATUS","")).upper() != "OUT":
                    st.warning("⚠️ This item is not currently OUT.")
                else:
                    st.markdown("#### Return Details")
                    st.info(
                        f"Borrowed by **{row.get('REQUESTOR','')}** | "
                        f"Job: **{row.get('JOB NO','')}** | "
                        f"Out since: {row.get('DATE OUT','')}"
                    )
                    with st.form("return_form"):
                        date_ret = st.date_input("Date Returned", value=datetime.today())
                        cur_cr   = str(row.get("CONDITION RETURNED","GOOD")).upper()
                        cr_idx   = CONDITION_FULL_OPTIONS.index(cur_cr) if cur_cr in CONDITION_FULL_OPTIONS else 0
                        cond_ret = st.selectbox("Condition Returned", CONDITION_FULL_OPTIONS, index=cr_idx)
                        cur_ac   = str(row.get("ACTUAL CONDITION","GOOD")).upper()
                        ac_idx   = CONDITION_FULL_OPTIONS.index(cur_ac) if cur_ac in CONDITION_FULL_OPTIONS else 0
                        new_cond = st.selectbox("Update Actual Condition", CONDITION_FULL_OPTIONS, index=ac_idx)
                        remarks  = st.text_input("Remarks", value=str(row.get("REMARKS","") or ""))

                        if st.form_submit_button("✅ Confirm Return", type="primary"):
                            ws.update(f"P{row_num}:Y{row_num}", [[
                                str(row.get("DATE OUT","")), str(date_ret),
                                row.get("REQUESTOR",""), row.get("PROJECT / USAGE",""),
                                row.get("LOCATION",""), row.get("CONDITION OUT",""),
                                cond_ret, row.get("JOB NO",""),
                                "AVAILABLE", remarks
                            ]])
                            ws.update(f"O{row_num}", [[new_cond]])
                            st.success(f"✅ Returned on {date_ret} | Condition: {cond_ret}")
                            reload()

    # ── TAB 3: CURRENTLY OUT ──────────────────────────────────────────────────
    with tab3:
        out_df = df[df["STATUS"].fillna("").str.upper() == "OUT"]
        if out_df.empty:
            st.info("✅ No items currently out on loan.")
        else:
            st.markdown(f"#### {len(out_df)} Items Currently Out")
            show_cols = [c for c in [
                "SERIAL NUMBER","TAGGING NUMBER","DESCRIPTION","CATEGORY",
                "BRAND","REQUESTOR","JOB NO","DATE OUT",
                "PROJECT / USAGE","LOCATION","CONDITION OUT"
            ] if c in out_df.columns]
            st.dataframe(out_df[show_cols], height=500, width='stretch')