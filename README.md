# SaaS MRR Waterfall Pipeline

An end-to-end Analytics Engineering portfolio platform that simulates, loads, transforms, validates, and visualizes B2B customer subscription lifecycles to build a Month-over-Month (MoM) **Monthly Recurring Revenue (MRR) Waterfall**.

---

## 1. Project Overview

In SaaS businesses, customer activities (signups, upgrades, downgrades, cancellations) are captured as sparse transactional billing logs. To perform financial audits and analyze revenue growth, data teams must transform these sparse events into a continuous, month-by-month chronological ledger. 

This project simulates 1,000 customers over an 18-month period, ingests the data into a local **DuckDB** database, applies advanced **Date Spining** transformations to calculate recurring monthly recurring revenue, runs automated validations to reconcile accounting equations, and visualizes the results in an interactive **Streamlit** dashboard.

### The Business Value:
* **Cohorted MRR Breakdown**: Visualizes growth categorizations (New, Expansion, Reactivation, Contraction, Churn) so executives know *exactly* where revenue is expanding or leaking.
* **Accuracy Assurance**: Prevents accounting errors using automated data-integrity assertions, ensuring that starting balances, monthly shifts, and ending revenues reconcile to the single cent.

---

## 2. Technology Stack

| Technology | Purpose in Project |
| :--- | :--- |
| **Python** | Core language used for mock state-machine simulation and pipeline orchestration. |
| **DuckDB** | In-process OLAP database used for fast local storage, querying, and analytical view processing. |
| **SQL** | View transformation logic implementing date spining, CTE queries, lag window functions, and categorization. |
| **Streamlit** | Low-latency Python web framework used to build and serve the interactive metrics dashboard. |
| **Plotly** | Visualization library used to draw the dynamic MRR Waterfall steps and MoM dual-axis trend lines. |
| **Pandas** | In-memory data manipulation library used to parse, group, and display tabular ledger details. |
| **pytest** | Automated test runner verifying database constraints, transaction rollbacks, and schema integrity. |

---

## 3. Project Directory Layout

```text
SaaS-MRR-Waterfall-Pipeline/
│
├── app.py                              # Streamlit dashboard script
├── requirements.txt                    # Declared Python package dependencies
├── pytest.ini                          # pytest configuration file
├── .gitignore                          # Repository file exclusion rules
│
├── data/
│   └── mrr_waterfall.duckdb            # [Auto-generated] Embedded DuckDB database file
│
├── sql/
│   └── create_views.sql                # Analytical Date Spine transformations SQL script
│
├── src/
│   ├── config.py                       # Project paths, constants, and simulation limits
│   ├── generator.py                    # Mock subscriber lifecycle state-machine generator
│   ├── pipeline.py                     # Schema DDL setups, data loading, and ETL pipeline
│   ├── utils.py                        # Standardized dual logging and DuckDB connection managers
│   └── validator.py                    # Revenue reconciliation validation runner
│
└── tests/
    ├── __init__.py                     # Package marker for relative test module resolution
    ├── conftest.py                     # Reusable pytest fixtures (in-memory mock DBs)
    └── test_reconciliation.py          # Pytest suite running validations and negative tests
```

---

## 4. System Architecture & Data Flow

```text
  [Synthetic Generator] 
           │
           ▼ (Atomic Transaction Ingestion)
   [DuckDB Database] ──► DDL Tables (dim_plans, dim_customers, subscription_events)
           │
           ▼ (7-Step SQL View transform script)
   [View: v_mrr_movements]
           │
           ├──► [Pytest Validation Suite (pytest tests/)]
           │
           └──► [Streamlit Analytics Dashboard (app.py)]
```

### Flow Breakdown:
1. **Simulation**: A Python-based state machine simulator generates chronological subscription sequences (signups, plan changes, cancellations) for 1,000 customers.
2. **Ingestion (ETL)**: Python orchestrates DDL setups, clears previous states, inserts dataframes, and verifies database row counts matches inputs within a safe, commit-backed transaction block.
3. **Database Views (Transformations)**: DuckDB executes [sql/create_views.sql](sql/create_views.sql) to compile a 7-step analytical CTE view:
   * **Date Spine** generation using `generate_series()` cross-joined with customers to expand reporting periods.
   * **Forward-filling** active rates at month-ends using correlated subqueries.
   * **MoM Comparisons** utilizing `LAG()` window functions.
   * **Revenue Categorization** sorting shifts into New, Expansion, Reactivation, Contraction, Churn, or No Change.
4. **Validation (Testing)**: Programs check for calculation balance, Month-over-Month continuity, customer count alignment, and join referential integrity.
5. **Dashboard (Visualization)**: Streamlit displays filtered visualizations, cards, and tables using cached database queries.

---

## 5. Dashboard Features & Layout

<!-- 
[PORTFOLIO NOTE] 
To add dashboard screenshots:
1. Take screenshots of your local Streamlit app.
2. Save them to a new folder: `docs/assets/`
3. Embed them here using markdown image syntax: `![Dashboard Overview](docs/assets/dashboard_overview.png)`
-->

* **Sidebar Segmentation Filters**: Dynamic dropdown filters for Country and Industry that rebuild and filter the entire dashboard dataset in real-time. Includes a chronological Month Selector.
* **KPI Metrics Row**: Metric cards displaying Ending MRR, Active Customers, ARPU, Net Revenue Retention (NRR), and Gross Churn, complete with prior-month delta trend indicators.
* **Plotly Waterfall Visualizer**: Step-chart showing Starting MRR, changes, and Ending MRR, backed by a clear mathematical formula block underneath.
* **Chronological Trend Tracker**: A dual-axis line chart plotting monthly Ending MRR (left) and Active Customers (right) across the full 18-month history.
* **Customer Activity Ledger**: A detailed transaction details table equipped with a live text name search box.
* **Under the Hood SQL Viewer**: An expander displaying the raw date-spine transform script so technical reviewers can inspect the SQL structure directly.

---

## 6. Business Metrics Definitions

For non-financial reviewers, here is how the metrics are calculated:
* **Monthly Recurring Revenue (MRR)**: The predictable total revenue generated by all active subscribers in a single month.
* **ARPU (Average Revenue Per User)**: The average amount of monthly revenue contributed per active customer. (Calculated as `Ending MRR / Active Customers`).
* **NRR (Net Revenue Retention)**: Measures the percentage of recurring revenue retained from existing customers over a given period, excluding new signups. (Calculated as `(Starting MRR + Expansion + Reactivation + Contraction + Churn) / Starting MRR * 100`).
* **Gross Churn Rate**: The percentage of revenue lost due to cancellations (Churn) and downgrades (Contraction) relative to Starting MRR. (Calculated as `(|Churn| + |Contraction|) / Starting MRR * 100`).

---

## 7. Getting Started & Setup

### Prerequisites
* Python 3.10+
* Virtual Environment manager (`venv`)

### Setup and Local Launch
1. **Clone the Repository** and navigate to the project folder:
   ```bash
   git clone <your-repository-url>
   cd "SaaS MRR Waterfall Pipeline"
   ```
2. **Setup Virtual Environment & Install Dependencies**:
   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. **Execute Ingestion & Transform Pipeline**:
   This recreates the DuckDB database file, ingests raw records, and compiles the analytical views:
   ```bash
   python -m src.pipeline
   ```
4. **Run Validation Script**:
   Verify database integrity checks exit with code `0`:
   ```bash
   python -m src.validator
   ```
5. **Run the Automated Tests**:
   Execute the full pytest suite (12 tests covering happy path, negative inputs, and check constraints):
   ```bash
   pytest
   ```
6. **Launch the Dashboard**:
   Run the interactive Streamlit dashboard locally:
   ```bash
   streamlit run app.py
   ```

---

## 8. Known Limitations
* **Scale Constraints**: Built and optimized for single-node portfolio datasets using DuckDB. Not designed for distributed big-data environments.
* **Local Processing**: Utilizes local file storage for database assets; does not include cloud data warehouse staging (e.g., Snowflake, BigQuery).
* **Security & Auth**: Running locally with no role-based access controls, authentication walls, or secure network proxies.
* **No Orchestration Engine**: Python script orchestration is synchronous; does not use containerized task schedulers like Airflow.

---

## 9. Future Improvements
* **Docker Containerization**: Wrap the pipeline and dashboard in a multi-container Docker setup for standard cloud deployments.
* **dbt Integration**: Migrate the SQL transformation views to a dedicated **dbt** project to show warehouse modularity.
* **Orchestration**: Implement a task-scheduling tool (Airflow or Prefect) to manage pipeline steps.
* **Cloud Warehouse Ingestion**: Add scripts to load simulation outputs to Snowflake or BigQuery.
* **Predictive Analytics**: Add a machine learning component (such as ARIMA or Prophet) to forecast customer churn and MRR trends.
