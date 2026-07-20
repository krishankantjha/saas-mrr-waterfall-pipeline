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
    
    /* Section Headers */
    .section-header {
        font-size: 1.5rem;
        font-weight: 600;
        color: var(--text-color);
        margin-top: 1.5rem;
        margin-bottom: 0.5rem;
        border-bottom: 2px solid var(--border-color, #f1f5f9);
        padding-bottom: 8px;
    }
    
    /* Formula Box */
    .formula-container {
        background-color: var(--secondary-background-color);
        border: 1px solid var(--border-color, #e2e8f0);
        color: var(--text-color);
        border-radius: 8px;
        padding: 15px;
        text-align: center;
        margin-top: 10px;
        margin-bottom: 20px;
    }
    
    /* Custom KPI Cards Layout */
    .kpi-row {
        display: flex;
        flex-wrap: wrap;
        gap: 16px;
        margin-bottom: 20px;
        width: 100%;
    }
    .kpi-card {
        flex: 1;
        min-width: 180px;
        background-color: var(--secondary-background-color);
        border: 1px solid var(--border-color, #e2e8f0);
        color: var(--text-color);
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.02), 0 1px 3px rgba(0, 0, 0, 0.05);
        transition: transform 0.2s ease-in-out, box-shadow 0.2s ease-in-out;
    }
    .kpi-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 12px rgba(0, 0, 0, 0.04), 0 2px 4px rgba(0, 0, 0, 0.05);
    }
    .kpi-header {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 12px;
    }
    .kpi-icon {
        width: 32px;
        height: 32px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.1rem;
    }
    .icon-mrr { background-color: rgba(16, 185, 129, 0.15); color: #10b981; }
    .icon-cust { background-color: rgba(59, 130, 246, 0.15); color: #3b82f6; }
    .icon-arpu { background-color: rgba(139, 92, 246, 0.15); color: #8b5cf6; }
    .icon-nrr { background-color: rgba(249, 115, 22, 0.15); color: #f97316; }
    .icon-churn { background-color: rgba(239, 68, 68, 0.15); color: #ef4444; }
    
    .kpi-label {
        font-size: 0.85rem;
        font-weight: 600;
        color: var(--text-color);
        opacity: 0.8;
    }
    .kpi-value {
        font-size: 1.8rem;
        font-weight: 700;
        color: var(--text-color);
        margin-bottom: 6px;
    }
    .kpi-delta {
        font-size: 0.75rem;
        font-weight: 600;
        display: inline-flex;
        align-items: center;
        gap: 3px;
    }
    .delta-up { color: #10b981; }
    .delta-down { color: #ef4444; }
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

# Sidebar Title with Version Tag
st.sidebar.markdown("""
    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 5px;">
        <span style="width: 28px; height: 28px; display: inline-flex; align-items: center; justify-content: center; color: #3b82f6;">
            <svg width="28" height="28" viewBox="0 0 716 716" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M508.749 317.399C516.777 287.314 508.991 253.884 485.389 230.282C461.788 206.681 428.36 198.895 398.273 206.923C376.231 184.928 343.39 174.956 311.148 183.596C278.906 192.234 255.45 217.292 247.36 247.361C217.291 255.451 192.233 278.91 183.595 311.149C174.957 343.391 184.927 376.232 206.924 398.274C198.896 428.359 206.683 461.789 230.284 485.391C253.885 508.992 287.313 516.779 317.401 508.75C339.442 530.745 372.286 540.717 404.525 532.079C436.767 523.441 460.223 498.384 468.313 468.315C498.383 460.224 523.44 436.766 532.078 404.526C540.716 372.285 530.747 339.443 508.749 317.402V317.399ZM470.899 244.776C486.892 260.77 493.488 282.601 490.687 303.412L415.577 260.046C412.411 258.218 408.509 258.218 405.345 260.046L317.401 310.82V277.526C317.401 275.191 318.652 273.005 320.676 271.837L387.644 233.174C414.178 218.353 448.346 222.223 470.901 244.776H470.899ZM357.837 311.144L398.275 334.491V381.185L357.837 404.532L317.398 381.185V334.491L357.837 311.144ZM264.776 269.693C265.207 239.305 285.644 211.649 316.453 203.393C338.3 197.54 360.505 202.744 377.127 215.573L302.014 258.937C298.848 260.764 296.898 264.144 296.898 267.798V369.346L268.065 352.699C266.043 351.531 264.776 349.353 264.776 347.017V269.691V269.693ZM203.391 316.454C209.244 294.608 224.854 277.978 244.276 269.999V356.73C244.276 360.384 246.226 363.763 249.392 365.591L337.337 416.365L308.503 433.013C306.481 434.181 303.961 434.188 301.939 433.02L234.971 394.357C208.868 378.789 195.138 347.261 203.391 316.454ZM244.775 470.9C228.781 454.906 222.186 433.075 224.986 412.264L300.096 455.63C303.263 457.457 307.164 457.457 310.328 455.63L398.273 404.856V438.149C398.273 440.485 397.022 442.671 394.997 443.839L328.029 482.502C301.495 497.322 267.327 493.452 244.772 470.9H244.775ZM450.897 445.982C450.466 476.371 430.029 504.027 399.22 512.283C377.373 518.136 355.168 512.932 338.547 500.102L413.659 456.738C416.826 454.911 418.775 451.532 418.775 447.877V346.329L447.609 362.977C449.631 364.145 450.897 366.323 450.897 368.659V445.985V445.982ZM512.282 399.221C506.429 421.068 490.819 437.697 471.397 445.676V358.946C471.397 355.292 469.448 351.912 466.281 350.085L378.336 299.311L407.17 282.663C409.192 281.495 411.712 281.487 413.734 282.655L480.702 321.318C506.805 336.887 520.536 368.415 512.282 399.221Z" fill="currentColor"/>
            </svg>
        </span>
        <span style="font-weight: 700; font-size: 1.25rem; color: var(--text-color);">MRR Intelligence</span>
        <span style="background-color: #3b82f6; color: white; font-size: 0.7rem; font-weight: 700; padding: 2px 6px; border-radius: 4px;">v1.0</span>
    </div>
""", unsafe_allow_html=True)
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

# Pinned User Profile Footer in Sidebar
st.sidebar.markdown("""
    <div style="display: flex; align-items: center; gap: 12px; border-top: 1px solid var(--border-color, #e2e8f0); padding-top: 15px; margin-top: 30px;">
        <div style="background-color: #0f172a; color: white; font-weight: 700; width: 36px; height: 36px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 0.9rem;">
            KK
        </div>
        <div>
            <div style="font-weight: 600; font-size: 0.85rem; color: var(--text-color);">Krishan Kant Jha</div>
            <div style="font-size: 0.7rem; color: var(--text-color); opacity: 0.75;">Analytics Engineer</div>
        </div>
    </div>
""", unsafe_allow_html=True)

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
ending_val = f"${m_ending:,.2f}"
cust_val = f"{m_customers:,}"
arpu_val = f"${m_arpu:,.2f}"
nrr_val = f"{m_nrr:.2f}%"
churn_val = f"{m_churn:.2f}%"

if p_ending > 0:
    delta_mrr_str = f"▲ {delta_mrr_pct:+.1f}% vs last month" if delta_mrr_pct >= 0 else f"▼ {delta_mrr_pct:.1f}% vs last month"
    delta_cust_str = f"▲ {delta_cust:+} customers vs last month" if delta_cust >= 0 else f"▼ {delta_cust} customers vs last month"
    delta_arpu_str = f"▲ {delta_arpu_pct:+.1f}% vs last month" if delta_arpu_pct >= 0 else f"▼ {delta_arpu_pct:.1f}% vs last month"
    delta_nrr_str = f"▲ {delta_nrr:+.2f} pp vs last month" if delta_nrr >= 0 else f"▼ {delta_nrr:.2f} pp vs last month"
    delta_churn_str = f"▼ {delta_churn:+.2f} pp vs last month" if delta_churn <= 0 else f"▲ {delta_churn:+.2f} pp vs last month"
else:
    delta_mrr_str = "No prior month data"
    delta_cust_str = "No prior month data"
    delta_arpu_str = "No prior month data"
    delta_nrr_str = "No prior month data"
    delta_churn_str = "No prior month data"

delta_mrr_class = "delta-up" if delta_mrr_pct >= 0 else "delta-down"
delta_cust_class = "delta-up" if delta_cust >= 0 else "delta-down"
delta_arpu_class = "delta-up" if delta_arpu_pct >= 0 else "delta-down"
delta_nrr_class = "delta-up" if delta_nrr >= 0 else "delta-down"
delta_churn_class = "delta-up" if delta_churn <= 0 else "delta-down"

kpi_html = f"""
<div class="kpi-row">
    <!-- Ending MRR -->
    <div class="kpi-card">
        <div class="kpi-header">
            <div class="kpi-icon icon-mrr">💵</div>
            <div class="kpi-label">Ending MRR</div>
        </div>
        <div class="kpi-value">{ending_val}</div>
        <div class="kpi-delta {delta_mrr_class}">{delta_mrr_str}</div>
    </div>
    <!-- Active Customers -->
    <div class="kpi-card">
        <div class="kpi-header">
            <div class="kpi-icon icon-cust">👥</div>
            <div class="kpi-label">Active Customers</div>
        </div>
        <div class="kpi-value">{cust_val}</div>
        <div class="kpi-delta {delta_cust_class}">{delta_cust_str}</div>
    </div>
    <!-- ARPU -->
    <div class="kpi-card">
        <div class="kpi-header">
            <div class="kpi-icon icon-arpu">🪙</div>
            <div class="kpi-label">ARPU</div>
        </div>
        <div class="kpi-value">{arpu_val}</div>
        <div class="kpi-delta {delta_arpu_class}">{delta_arpu_str}</div>
    </div>
    <!-- NRR -->
    <div class="kpi-card">
        <div class="kpi-header">
            <div class="kpi-icon icon-nrr">📈</div>
            <div class="kpi-label">NRR (Net Retention)</div>
        </div>
        <div class="kpi-value">{nrr_val}</div>
        <div class="kpi-delta {delta_nrr_class}">{delta_nrr_str}</div>
    </div>
    <!-- Gross Churn Rate -->
    <div class="kpi-card">
        <div class="kpi-header">
            <div class="kpi-icon icon-churn">🚨</div>
            <div class="kpi-label">Gross Churn Rate</div>
        </div>
        <div class="kpi-value">{churn_val}</div>
        <div class="kpi-delta {delta_churn_class}">{delta_churn_str}</div>
    </div>
</div>
"""
st.markdown(kpi_html, unsafe_allow_html=True)

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
    
    # Compute CAGR and Growth metrics from the 18-month trends dataframe
    if not df_trends.empty and len(df_trends) > 1:
        first_row = df_trends.iloc[0]
        last_row = df_trends.iloc[-1]
        
        first_mrr = float(first_row["ending_mrr"])
        last_mrr = float(last_row["ending_mrr"])
        first_cust = int(first_row["active_customers"])
        last_cust = int(last_row["active_customers"])
        
        mrr_growth_pct = ((last_mrr - first_mrr) / first_mrr * 100) if first_mrr > 0 else 0.0
        cust_growth_pct = ((last_cust - first_cust) / first_cust * 100) if first_cust > 0 else 0.0
        
        years = (len(df_trends) - 1) / 12.0
        mrr_cagr = (((last_mrr / first_mrr) ** (1 / years) - 1) * 100) if first_mrr > 0 and last_mrr > 0 else 0.0
        cust_cagr = (((last_cust / first_cust) ** (1 / years) - 1) * 100) if first_cust > 0 and last_cust > 0 else 0.0
    else:
        mrr_growth_pct, cust_growth_pct, mrr_cagr, cust_cagr = 0.0, 0.0, 0.0, 0.0

    st.markdown("<br>", unsafe_allow_html=True)
    c_g1, c_g2, c_g3, c_g4 = st.columns(4)
    c_g1.markdown(f"""
    <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; padding: 10px; border-radius: 8px; text-align: center;">
        <div style="font-size: 0.72rem; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px;">MRR Growth (18M)</div>
        <div style="font-size: 1.1rem; font-weight: 700; color: #10b981; margin-top: 4px;">▲ {mrr_growth_pct:+.1f}%</div>
    </div>
    """, unsafe_allow_html=True)
    c_g2.markdown(f"""
    <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; padding: 10px; border-radius: 8px; text-align: center;">
        <div style="font-size: 0.72rem; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px;">Customer Growth (18M)</div>
        <div style="font-size: 1.1rem; font-weight: 700; color: #10b981; margin-top: 4px;">▲ {cust_growth_pct:+.1f}%</div>
    </div>
    """, unsafe_allow_html=True)
    c_g3.markdown(f"""
    <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; padding: 10px; border-radius: 8px; text-align: center;">
        <div style="font-size: 0.72rem; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px;">MRR CAGR</div>
        <div style="font-size: 1.1rem; font-weight: 700; color: #3b82f6; margin-top: 4px;">{mrr_cagr:.1f}%</div>
    </div>
    """, unsafe_allow_html=True)
    c_g4.markdown(f"""
    <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; padding: 10px; border-radius: 8px; text-align: center;">
        <div style="font-size: 0.72rem; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px;">Customer CAGR</div>
        <div style="font-size: 1.1rem; font-weight: 700; color: #3b82f6; margin-top: 4px;">{cust_cagr:.1f}%</div>
    </div>
    """, unsafe_allow_html=True)

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
    def style_categories(val):
        if val in ["Upgrade", "New", "Reactivation"]:
            return "background-color: rgba(16, 185, 129, 0.2); color: #10b981; font-weight: bold;"
        elif val in ["Downgrade", "Contraction", "Churn"]:
            return "background-color: rgba(239, 68, 68, 0.2); color: #ef4444; font-weight: bold;"
        return ""

    st.dataframe(
        df_display.style.format({
            "Monthly MRR Change": "${:+,.2f}"
        }).map(style_categories, subset=["Action Category"]),
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

# Main Canvas Page Footer
st.markdown("""
    <div style="text-align: center; color: #64748b; font-size: 0.8rem; margin-top: 60px; padding-bottom: 20px; border-top: 1px solid #f1f5f9; padding-top: 20px;">
        © 2026 MRR Intelligence Platform • Developed by Krishan Kant Jha
    </div>
""", unsafe_allow_html=True)
