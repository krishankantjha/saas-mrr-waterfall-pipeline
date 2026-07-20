import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from dateutil.relativedelta import relativedelta
from src.utils import get_db_connection
from src.config import SQL_VIEWS_PATH, DB_PATH
from src.pipeline import run_pipeline
from dataclasses import dataclass

# 1. Page Configuration and Premium Styling
st.set_page_config(
    page_title="SaaS MRR Waterfall Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inject custom CSS for premium typography, shadows, card borders, and spacing
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Outfit', sans-serif;
    }
    
    /* Card Container Styling */
    div.stMetric {
        background-color: #ffffff;
        border: 1px solid #f0f2f6;
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.02), 0 1px 3px rgba(0, 0, 0, 0.05);
        transition: transform 0.2s ease-in-out;
    }
    
    div.stMetric:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 12px rgba(0, 0, 0, 0.04), 0 2px 4px rgba(0, 0, 0, 0.05);
    }
    
    /* Section Headers */
    .section-header {
        font-size: 1.5rem;
        font-weight: 600;
        color: #1e293b;
        margin-top: 1.5rem;
        margin-bottom: 0.5rem;
        border-bottom: 2px solid #f1f5f9;
        padding-bottom: 8px;
    }
    
    /* Formula Box */
    .formula-container {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 15px;
        text-align: center;
        margin-top: 10px;
        margin-bottom: 20px;
    }
    </style>
""", unsafe_allow_html=True)

@dataclass(frozen=True)
class MRRMetrics:
    """Dataclass to capture standard SaaS metrics and prevent tuple unpacking bugs."""
    ending_mrr: float
    active_customers: int
    arpu: float
    nrr: float
    gross_churn: float
    starting_mrr: float
    new_mrr: float
    expansion: float
    reactivation: float
    contraction: float
    churn: float

# ==============================================================================
# Helper Functions (Data Queries and Mathematical Metrics Calculations)
# ==============================================================================

def calculate_mrr_metrics(df_month: pd.DataFrame) -> MRRMetrics:
    """Calculates standard SaaS metrics (Ending MRR, Active Customers, ARPU, NRR, Churn) for a dataframe."""
    if df_month.empty:
        return MRRMetrics(
            ending_mrr=0.0,
            active_customers=0,
            arpu=0.0,
            nrr=100.0,
            gross_churn=0.0,
            starting_mrr=0.0,
            new_mrr=0.0,
            expansion=0.0,
            reactivation=0.0,
            contraction=0.0,
            churn=0.0
        )
        
    ending_mrr = float(df_month["current_mrr"].sum())
    starting_mrr = float(df_month["prev_mrr"].sum())
    active_customers = int(df_month[df_month["current_mrr"] > 0]["customer_id"].nunique())
    arpu = ending_mrr / active_customers if active_customers > 0 else 0.0
    
    new_mrr = float(df_month[df_month["mrr_category"] == "New"]["mrr_change"].sum())
    expansion = float(df_month[df_month["mrr_category"] == "Expansion"]["mrr_change"].sum())
    reactivation = float(df_month[df_month["mrr_category"] == "Reactivation"]["mrr_change"].sum())
    contraction = float(df_month[df_month["mrr_category"] == "Contraction"]["mrr_change"].sum())
    churn = float(df_month[df_month["mrr_category"] == "Churn"]["mrr_change"].sum())
    
    # Net Revenue Retention: (Starting + Expansion + Reactivation + Contraction + Churn) / Starting
    # New MRR is excluded because NRR only measures retention and expansion of the existing cohort.
    nrr = ((starting_mrr + (expansion + reactivation + contraction + churn)) / starting_mrr * 100) if starting_mrr > 0 else 100.0
    
    # Gross Churn Rate: (|Churn| + |Contraction|) / Starting
    losses = abs(contraction + churn)
    gross_churn = (losses / starting_mrr * 100) if starting_mrr > 0 else 0.0
    
    return MRRMetrics(
        ending_mrr=ending_mrr,
        active_customers=active_customers,
        arpu=arpu,
        nrr=nrr,
        gross_churn=gross_churn,
        starting_mrr=starting_mrr,
        new_mrr=new_mrr,
        expansion=expansion,
        reactivation=reactivation,
        contraction=contraction,
        churn=churn
    )

@st.cache_data
def get_filter_options() -> tuple[list[str], list[str], list]:
    """Fetches unique filter values from the database for sidebar select boxes."""
    with get_db_connection(read_only=True) as conn:
        countries = conn.execute("SELECT DISTINCT country FROM v_mrr_movements ORDER BY country;").df()["country"].tolist()
        industries = conn.execute("SELECT DISTINCT industry FROM v_mrr_movements ORDER BY industry;").df()["industry"].tolist()
        # Sort months descending to place the latest month first
        months = conn.execute("SELECT DISTINCT month_date FROM v_mrr_movements ORDER BY month_date DESC;").df()["month_date"].tolist()
    return countries, industries, months

@st.cache_data
def fetch_mrr_data(countries_filter: list[str], industries_filter: list[str], month_filter_str: str) -> pd.DataFrame:
    """Fetches filtered customer movements data from DuckDB, cached by month and filters."""
    query_str = "SELECT * FROM v_mrr_movements WHERE 1=1"
    params_list = []
    
    if countries_filter:
        query_str += " AND country IN ?"
        params_list.append(countries_filter)
    if industries_filter:
        query_str += " AND industry IN ?"
        params_list.append(industries_filter)
        
    with get_db_connection(read_only=True) as conn:
        return conn.execute(query_str, params_list).df()

# Bootstrap the database inline if the DuckDB file is missing (crucial for zero-setup cloud deployments)
if not DB_PATH.exists():
    run_pipeline()

countries, industries, months_list = get_filter_options()

st.sidebar.title("📈 MRR Analytics")
st.sidebar.divider()

selected_countries = st.sidebar.multiselect(
    "Country Filter",
    options=countries,
    default=[],
    help="Leave empty to select all countries."
)

selected_industries = st.sidebar.multiselect(
    "Industry Filter",
    options=industries,
    default=[],
    help="Leave empty to select all industries."
)

selected_month = st.sidebar.selectbox(
    "Reporting Month",
    options=months_list,
    format_func=lambda x: x.strftime("%B %Y")
)

st.sidebar.divider()
st.sidebar.markdown("""
    ### About this Dashboard
    This application visualizes Monthly Recurring Revenue (MRR) movements using a **Date Spine** analytical data model.
    
    * **Database**: DuckDB (In-Memory View)
    * **Data Source**: Synthetically generated subscriber lifecycles (1,000 customers).
""")

# Load data and run calculations under a spinner
with st.spinner("Loading dashboard data..."):
    # Convert selected_month to ISO format for safe hashing in st.cache_data
    month_cache_key = selected_month.isoformat() if hasattr(selected_month, "isoformat") else str(selected_month)
    df_filtered = fetch_mrr_data(selected_countries, selected_industries, month_cache_key).copy()

    df_filtered["month_date"] = pd.to_datetime(df_filtered["month_date"])
    df_filtered["signup_date"] = pd.to_datetime(df_filtered["signup_date"])

    # Core metric calculations
    target_month = pd.to_datetime(selected_month)
    prior_month = target_month - relativedelta(months=1)

    df_active = df_filtered[df_filtered["month_date"] == target_month]
    df_prior = df_filtered[df_filtered["month_date"] == prior_month]

    m_metrics = calculate_mrr_metrics(df_active)
    m_ending = m_metrics.ending_mrr
    m_customers = m_metrics.active_customers
    m_arpu = m_metrics.arpu
    m_nrr = m_metrics.nrr
    m_churn = m_metrics.gross_churn
    m_starting = m_metrics.starting_mrr
    m_new = m_metrics.new_mrr
    m_expansion = m_metrics.expansion
    m_reactivation = m_metrics.reactivation
    m_contraction = m_metrics.contraction
    m_churn_val = m_metrics.churn

    p_metrics = calculate_mrr_metrics(df_prior)
    p_ending = p_metrics.ending_mrr
    p_customers = p_metrics.active_customers
    p_arpu = p_metrics.arpu
    p_nrr = p_metrics.nrr
    p_churn = p_metrics.gross_churn

    # Compute Deltas (current vs prior month)
    delta_mrr_pct = ((m_ending - p_ending) / p_ending * 100) if p_ending > 0 else 0.0
    delta_cust = m_customers - p_customers
    delta_arpu_pct = ((m_arpu - p_arpu) / p_arpu * 100) if p_arpu > 0 else 0.0
    delta_nrr = m_nrr - p_nrr
    delta_churn = m_churn - p_churn

# 6. UI Rendering - Dashboard Header
st.title("SaaS MRR Waterfall Dashboard")
st.markdown(f"**Timeline Period**: Monthly Recurring Revenue movements as of **{target_month.strftime('%B %Y')}**")

# Row 1: KPI Metric Cards
col1, col2, col3, col4, col5 = st.columns(5)

col1.metric(
    label="Ending MRR",
    value=f"${m_ending:,.2f}",
    delta=f"{delta_mrr_pct:+.1f}% vs last month" if p_ending > 0 else None
)

col2.metric(
    label="Active Customers",
    value=f"{m_customers:,}",
    delta=f"{delta_cust:+} customers vs last month" if p_ending > 0 else None
)

col3.metric(
    label="ARPU",
    value=f"${m_arpu:,.2f}",
    delta=f"{delta_arpu_pct:+.1f}% vs last month" if p_arpu > 0 else None
)

col4.metric(
    label="NRR (Net Retention)",
    value=f"{m_nrr:.2f}%",
    delta=f"{delta_nrr:+.2f} pp vs last month" if p_ending > 0 else None
)

col5.metric(
    label="Gross Churn Rate",
    value=f"{m_churn:.2f}%",
    delta=f"{delta_churn:+.2f} pp vs last month" if p_ending > 0 else None,
    delta_color="inverse"  # Churn increase is bad, decrease is good
)

# Row 2: Waterfall Chart & Equation summary
st.markdown('<div class="section-header">MRR Waterfall Movements</div>', unsafe_allow_html=True)

# Build standard Plotly Waterfall figure
waterfall_fig = go.Figure(go.Waterfall(
    name="MRR Waterfall",
    orientation="v",
    measure=["absolute", "relative", "relative", "relative", "relative", "relative", "total"],
    x=["Starting MRR", "New MRR", "Expansion", "Reactivation", "Contraction", "Churn", "Ending MRR"],
    text=[f"${x:,.0f}" for x in [m_starting, m_new, m_expansion, m_reactivation, m_contraction, m_churn_val, m_ending]],
    y=[m_starting, m_new, m_expansion, m_reactivation, m_contraction, m_churn_val, m_ending],
    textposition="outside",
    connector={"line": {"color": "rgb(148, 163, 184)", "width": 1, "dash": "dot"}},
    decreasing={"marker": {"color": "#ef4444"}},  # Slate Red
    increasing={"marker": {"color": "#10b981"}},  # Slate Green
    totals={"marker": {"color": "#3b82f6"}}       # Slate Blue
))

waterfall_fig.update_layout(
    title=f"MRR Reconciliation details for {target_month.strftime('%B %Y')}",
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    margin=dict(t=50, b=50, l=30, r=30),
    xaxis=dict(showgrid=False),
    yaxis=dict(showgrid=True, gridcolor="#f1f5f9", title="MRR (USD)")
)

st.plotly_chart(waterfall_fig, use_container_width=True)

# Reconciliation equation helper container
total_increases = m_new + m_expansion + m_reactivation
total_decreases = abs(m_contraction + m_churn_val)
st.markdown(f"""
    <div class="formula-container">
        <strong>Starting MRR</strong> (${m_starting:,.2f}) 
        <span style="color:#10b981;">+ <strong>Total Increases</strong> (${total_increases:,.2f})</span> 
        <span style="color:#ef4444;">- <strong>Total Decreases</strong> (${total_decreases:,.2f})</span> 
        = <strong>Ending MRR</strong> (${m_ending:,.2f})
    </div>
""", unsafe_allow_html=True)

# Row 3: MoM Trends (Dual Axis) and Segmentation Bar Chart
st.markdown('<div class="section-header">Business Trends & Segment Analysis</div>', unsafe_allow_html=True)
trend_col, segment_col = st.columns(2)

with trend_col:
    # Compile 18-month aggregate trend data from filtered dataset
    df_trends = df_filtered.groupby("month_date").agg(
        ending_mrr=("current_mrr", "sum"),
        active_customers=("current_mrr", lambda x: (x > 0).sum())
    ).reset_index().sort_values("month_date")
    
    # Render Dual-Axis Chart
    trend_fig = go.Figure()
    
    # 1. Ending MRR bar/line
    trend_fig.add_trace(go.Scatter(
        x=df_trends["month_date"],
        y=df_trends["ending_mrr"],
        name="Ending MRR (USD)",
        mode="lines+markers",
        line=dict(color="#3b82f6", width=3),
        yaxis="y1"
    ))
    
    # 2. Active Customers line
    trend_fig.add_trace(go.Scatter(
        x=df_trends["month_date"],
        y=df_trends["active_customers"],
        name="Active Customers",
        mode="lines+markers",
        line=dict(color="#10b981", width=2, dash="dash"),
        yaxis="y2"
    ))
    
    # Update axes layout configuration for dual-axis support
    trend_fig.update_layout(
        title="MRR & Active Customer Count Trends (Chronological Timeline)",
        xaxis=dict(title="Month Date", showgrid=False),
        yaxis=dict(title="Ending MRR (USD)", color="#3b82f6", showgrid=True, gridcolor="#f1f5f9"),
        yaxis2=dict(title="Active Customers Count", color="#10b981", overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)"
    )
    st.plotly_chart(trend_fig, use_container_width=True)

with segment_col:
    # Display segment composition using active customer company sizes
    df_segment = df_active[df_active["current_mrr"] > 0].groupby("company_size").agg(
        mrr_contribution=("current_mrr", "sum")
    ).reset_index()
    
    segment_fig = px.bar(
        df_segment,
        x="company_size",
        y="mrr_contribution",
        text="mrr_contribution",
        title="Active MRR Contribution by Customer Segment",
        color="company_size",
        color_discrete_map={"SMB": "#60a5fa", "Mid-Market": "#34d399", "Enterprise": "#f472b6"}
    )
    
    segment_fig.update_traces(
        texttemplate="$%{text:,.0f}",
        textposition="outside"
    )
    
    segment_fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(title="Company Size Segment", showgrid=False),
        yaxis=dict(title="Total MRR (USD)", showgrid=True, gridcolor="#f1f5f9"),
        showlegend=False
    )
    st.plotly_chart(segment_fig, use_container_width=True)

# Row 4: Detailed Transaction Logs Table
st.markdown('<div class="section-header">Customer Activity Ledger</div>', unsafe_allow_html=True)

# Filter out quiet months where no customer change occurred to display an active log
df_ledger = df_active[~df_active["mrr_category"].isin(["No Change", "Inactive"])].copy()

# Add a simple text search bar for table names
search_query = st.text_input("🔍 Search Customers by Name", "")
if search_query:
    df_ledger = df_ledger[df_ledger["customer_name"].str.contains(search_query, case=False, na=False)]

# Format data for clean reporting output
df_display = df_ledger[[
    "customer_name", "country", "industry", "company_size", 
    "prev_plan_name", "current_plan_name", "mrr_change", "mrr_category"
]].rename(columns={
    "customer_name": "Customer Name",
    "country": "Country",
    "industry": "Industry",
    "company_size": "Segment",
    "prev_plan_name": "Previous Plan",
    "current_plan_name": "New Plan",
    "mrr_change": "Monthly MRR Change",
    "mrr_category": "Action Category"
}).reset_index(drop=True)

# Render formatted dataframe
if df_display.empty:
    st.info("No transaction records found matching the active filters or search term.")
else:
    st.dataframe(
        df_display.style.format({
            "Monthly MRR Change": "${:+,.2f}"
        }),
        use_container_width=True,
        height=300
    )
    st.caption(f"Showing {len(df_display)} records")

# Row 5: Under the Hood SQL Explanation Expander
st.markdown("---")
with st.expander("🛠️ Under the Hood: Data Pipeline & SQL Transformations"):
    st.markdown("""
        ### Architectural Design & ETL Pipeline
        This project acts as a modern **ELT (Extract, Load, Transform)** database model:
        1. **Simulation**: Programmatic lifecycles are generated deterministically in Python (`src/generator.py`).
        2. **Ingestion**: Clean tables are created and loaded into DuckDB with primary/foreign keys and transaction commit safety (`src/pipeline.py`).
        3. **Transformation**: Heavy mathematical reconciliation is compiled inside the database using a **Date Spine** model (`sql/create_views.sql`).
        
        ### SQL Date Spine Model
        Because customer transaction events are sparse, we cross-join customers and months to fill reporting gaps. 
        Below is the raw SQL view structure compiled inside DuckDB to generate the active dataset:
    """)
    
    # Read the SQL query from create_views.sql to display directly in the dashboard
    try:
        with open(SQL_VIEWS_PATH, "r", encoding="utf-8") as f:
            raw_sql = f.read()
        st.code(raw_sql, language="sql")
    except Exception:
        st.warning("View schema SQL script not found on disk.")
