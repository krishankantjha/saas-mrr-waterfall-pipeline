import duckdb
from src.config import SQL_VIEWS_PATH
from src.utils import get_db_connection, logger
from src.generator import get_synthetic_data

def run_ddl_setup(conn: duckdb.DuckDBPyConnection) -> None:
    """Executes the DDL statements to create database tables with constraints and checks."""
    logger.info("Initializing database tables...")
    
    # 1. Plans dimension table with check constraints
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dim_plans (
            plan_id VARCHAR PRIMARY KEY,
            plan_name VARCHAR NOT NULL,
            monthly_price DECIMAL(10, 2) NOT NULL,
            billing_cycle VARCHAR NOT NULL CHECK (billing_cycle IN ('monthly'))
        );
    """)
    
    # 2. Customers dimension table with check constraints
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dim_customers (
            customer_id VARCHAR PRIMARY KEY,
            customer_name VARCHAR NOT NULL,
            signup_date DATE NOT NULL,
            country VARCHAR NOT NULL,
            industry VARCHAR NOT NULL,
            company_size VARCHAR NOT NULL CHECK (company_size IN ('SMB', 'Mid-Market', 'Enterprise'))
        );
    """)
    
    # 3. Subscription transaction events fact table with check constraints
    conn.execute("""
        CREATE TABLE IF NOT EXISTS subscription_events (
            event_id VARCHAR PRIMARY KEY,
            customer_id VARCHAR NOT NULL REFERENCES dim_customers(customer_id),
            plan_id VARCHAR REFERENCES dim_plans(plan_id),
            event_type VARCHAR NOT NULL CHECK (event_type IN ('signup', 'upgrade', 'downgrade', 'cancel', 'reactivate')),
            event_date DATE NOT NULL,
            monthly_amount DECIMAL(10, 2) NOT NULL CHECK (monthly_amount >= 0)
        );
    """)
    logger.info("Database tables initialized successfully.")

def load_data(conn: duckdb.DuckDBPyConnection) -> None:
    """Ingests synthetic customer and plan dataframes into the DuckDB tables atomically."""
    logger.info("Generating and ingesting synthetic customer datasets...")
    
    df_plans, df_customers, df_events = get_synthetic_data()
    
    try:
        # Start transaction to ensure atomicity
        conn.execute("BEGIN;")
        
        # Clear existing data in reverse relational order to prevent key constraint violations
        conn.execute("DELETE FROM subscription_events;")
        conn.execute("DELETE FROM dim_customers;")
        conn.execute("DELETE FROM dim_plans;")
        
        # Ingest dataframes directly (DuckDB automatically queries local variables by name)
        conn.execute("INSERT INTO dim_plans SELECT * FROM df_plans;")
        conn.execute("INSERT INTO dim_customers SELECT * FROM df_customers;")
        conn.execute("INSERT INTO subscription_events SELECT * FROM df_events;")
        
        plans_count = conn.execute("SELECT COUNT(*) FROM dim_plans;").fetchone()[0]
        customers_count = conn.execute("SELECT COUNT(*) FROM dim_customers;").fetchone()[0]
        events_count = conn.execute("SELECT COUNT(*) FROM subscription_events;").fetchone()[0]
        
        if plans_count != len(df_plans):
            raise ValueError(f"Data loading validation failed: dim_plans row count mismatch (DB: {plans_count}, Expected: {len(df_plans)})")
        if customers_count != len(df_customers):
            raise ValueError(f"Data loading validation failed: dim_customers row count mismatch (DB: {customers_count}, Expected: {len(df_customers)})")
        if events_count != len(df_events):
            raise ValueError(f"Data loading validation failed: subscription_events row count mismatch (DB: {events_count}, Expected: {len(df_events)})")
            
        logger.info("Data loading validation passed: database counts match dataframes.")
        
        conn.execute("COMMIT;")
        logger.info(f"Ingested {len(df_plans)} plans, {len(df_customers)} customers, and {len(df_events)} transaction events.")
        
    except Exception as e:
        conn.execute("ROLLBACK;")
        logger.error(f"Data loading failed. Transaction rolled back: {e}")
        raise e

def build_analytical_views(conn: duckdb.DuckDBPyConnection) -> None:
    """Reads and executes the SQL view file to build the transformation models."""
    logger.info("Compiling analytical transformations and SQL views...")
    
    if not SQL_VIEWS_PATH.exists():
        raise FileNotFoundError(f"SQL view script not found at path: {SQL_VIEWS_PATH}")
        
    with open(SQL_VIEWS_PATH, "r", encoding="utf-8") as f:
        sql_script = f.read()
        
    # Execute the view creation script
    conn.execute(sql_script)
    logger.info("SQL views compiled successfully.")

def run_pipeline() -> None:
    """Orchestrates the complete database DDL creation, load, and transform pipeline."""
    logger.info("=== Starting SaaS MRR Pipeline Ingestion ===")
    
    try:
        with get_db_connection() as conn:
            run_ddl_setup(conn)
            load_data(conn)
            build_analytical_views(conn)
        logger.info("=== SaaS MRR Pipeline Executed Successfully ===")
    except Exception as e:
        logger.error(f"Pipeline execution encountered an error: {e}")
        raise e

if __name__ == "__main__":
    run_pipeline()
