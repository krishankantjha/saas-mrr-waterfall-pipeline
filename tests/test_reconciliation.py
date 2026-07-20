import pytest
import duckdb
from src.validator import (
    validate_mrr_reconciliation,
    validate_mrr_continuity,
    validate_customer_counts,
    validate_referential_integrity
)

# ==============================================================================
# HAPPY PATH TESTS (Against Production DB, read-only)
# ==============================================================================

def test_mrr_reconciliation_math(db_conn):
    """Asserts that starting/ending/change MRR values balance out exactly for all months."""
    assert validate_mrr_reconciliation() is True, "Accounting equation validation failed."

def test_mrr_continuity(db_conn):
    """Asserts that Starting MRR of any month matches the Ending MRR of the previous month."""
    assert validate_mrr_continuity() is True, "Month-over-month continuity check failed."

def test_customer_counts(db_conn):
    """Asserts that unique customer counts are consistent between dimensions and transform views."""
    assert validate_customer_counts() is True, "Distinct customer count mismatch."

def test_foreign_key_referential_integrity(db_conn):
    """Asserts that there are no orphan customer or plan records inside analytical views."""
    assert validate_referential_integrity() is True, "Referential integrity lookup failed."

def test_database_schema_constraints(db_conn):
    """Asserts that database contains expected constraints (no negative pricing, valid domains)."""
    # 1. Assert that dim_plans contains the correct 3 plans
    plans_count = db_conn.execute("SELECT COUNT(*) FROM dim_plans;").fetchone()[0]
    assert plans_count == 3, f"Expected 3 plans, found {plans_count}."
    
    # 2. Assert that no negative monthly amounts exist in events table
    negative_events = db_conn.execute("SELECT COUNT(*) FROM subscription_events WHERE monthly_amount < 0;").fetchone()[0]
    assert negative_events == 0, f"Found {negative_events} transaction records with negative pricing."
    
    # 3. Assert that only valid company sizes exist in dim_customers
    invalid_sizes = db_conn.execute(
        "SELECT COUNT(*) FROM dim_customers WHERE company_size NOT IN ('SMB', 'Mid-Market', 'Enterprise');"
    ).fetchone()[0]
    assert invalid_sizes == 0, f"Found {invalid_sizes} customer profiles with invalid segment sizes."
    
    # 4. Assert that all event types fall within valid categories
    invalid_events = db_conn.execute(
        "SELECT COUNT(*) FROM subscription_events WHERE event_type NOT IN ('signup', 'upgrade', 'downgrade', 'cancel', 'reactivate');"
    ).fetchone()[0]
    assert invalid_events == 0, f"Found {invalid_events} event records with invalid categories."

# ==============================================================================
# NEGATIVE TESTS (Against Mock in-memory DB to verify failure detection)
# ==============================================================================

def test_validate_mrr_reconciliation_failure(mock_validator_db):
    """Asserts that validate_mrr_reconciliation returns False when the accounting equation does not balance."""
    # We replace the v_mrr_movements view with a physical table containing corrupted data
    mock_validator_db.execute("DROP VIEW v_mrr_movements;")
    mock_validator_db.execute("""
        CREATE TABLE v_mrr_movements (
            customer_id VARCHAR,
            customer_name VARCHAR,
            country VARCHAR,
            industry VARCHAR,
            company_size VARCHAR,
            signup_date DATE,
            month_date DATE,
            prev_mrr DECIMAL(10, 2),
            current_mrr DECIMAL(10, 2),
            mrr_change DECIMAL(10, 2),
            mrr_category VARCHAR,
            prev_plan_id VARCHAR,
            prev_plan_name VARCHAR,
            current_plan_id VARCHAR,
            current_plan_name VARCHAR
        );
    """)
    # Insert corrupted row: starting=10.0, ending=20.0, change=0.0 (imbalance of $10)
    mock_validator_db.execute("""
        INSERT INTO v_mrr_movements VALUES (
            'cust_001', 'Test Co', 'US', 'Tech', 'SMB', '2025-01-01', '2025-01-01',
            10.00, 20.00, 0.00, 'No Change', 'plan_basic', 'Basic', 'plan_basic', 'Basic'
        );
    """)
    
    assert validate_mrr_reconciliation() is False, "Validator failed to detect an unbalanced accounting equation!"

def test_validate_mrr_continuity_failure(mock_validator_db):
    """Asserts that validate_mrr_continuity returns False when a month-over-month continuity gap is found."""
    mock_validator_db.execute("DROP VIEW v_mrr_movements;")
    mock_validator_db.execute("""
        CREATE TABLE v_mrr_movements (
            month_date DATE,
            prev_mrr DECIMAL(10, 2),
            current_mrr DECIMAL(10, 2)
        );
    """)
    # Insert Month 1: ending MRR is $19
    mock_validator_db.execute("INSERT INTO v_mrr_movements VALUES ('2025-01-01', 0.00, 19.00);")
    # Insert Month 2: starting MRR is $50 (continuity gap of $31)
    mock_validator_db.execute("INSERT INTO v_mrr_movements VALUES ('2025-02-01', 50.00, 50.00);")
    
    assert validate_mrr_continuity() is False, "Validator failed to detect a Month-over-Month continuity gap!"

def test_validate_customer_counts_failure(mock_validator_db):
    """Asserts that validate_customer_counts returns False when customer totals are inconsistent."""
    mock_validator_db.execute("INSERT INTO dim_customers VALUES ('cust_1', 'C1', '2025-01-01', 'US', 'Tech', 'SMB');")
    mock_validator_db.execute("INSERT INTO dim_customers VALUES ('cust_2', 'C2', '2025-01-01', 'US', 'Tech', 'SMB');")
    
    mock_validator_db.execute("DROP VIEW v_mrr_movements;")
    mock_validator_db.execute("CREATE TABLE v_mrr_movements (customer_id VARCHAR);")
    mock_validator_db.execute("INSERT INTO v_mrr_movements VALUES ('cust_1');")
    
    assert validate_customer_counts() is False, "Validator failed to detect customer count mismatch!"

def test_validate_referential_integrity_failure(mock_validator_db):
    """Asserts that validate_referential_integrity returns False when orphan references exist."""
    mock_validator_db.execute("DROP VIEW v_mrr_movements;")
    mock_validator_db.execute("""
        CREATE TABLE v_mrr_movements (
            customer_id VARCHAR,
            current_plan_id VARCHAR
        );
    """)
    # Insert an orphan customer (does not exist in dim_customers)
    mock_validator_db.execute("INSERT INTO v_mrr_movements VALUES ('cust_orphan', 'plan_basic');")
    
    assert validate_referential_integrity() is False, "Validator failed to detect orphan customer reference!"

# ==============================================================================
# EDGE CASE & DDL CONSTRAINT TESTS
# ==============================================================================

def test_single_customer_lifecycle(mock_validator_db):
    """Asserts that a customer with a single signup event is correctly processed and validates."""
    mock_validator_db.execute("INSERT INTO dim_plans VALUES ('plan_basic', 'Basic', 19.00, 'monthly');")
    mock_validator_db.execute("INSERT INTO dim_customers VALUES ('cust_1', 'C1', '2025-01-01', 'US', 'Tech', 'SMB');")
    mock_validator_db.execute("INSERT INTO subscription_events VALUES ('evt_1', 'cust_1', 'plan_basic', 'signup', '2025-01-15', 19.00);")
    
    # Verify that the view compiles and all checks pass
    assert validate_mrr_reconciliation() is True
    assert validate_customer_counts() is True
    assert validate_referential_integrity() is True

def test_customer_signup_and_churn(mock_validator_db):
    """Asserts that a customer who signs up and cancels in consecutive months computes correctly."""
    mock_validator_db.execute("INSERT INTO dim_plans VALUES ('plan_basic', 'Basic', 19.00, 'monthly');")
    mock_validator_db.execute("INSERT INTO dim_customers VALUES ('cust_1', 'C1', '2025-01-01', 'US', 'Tech', 'SMB');")
    # Signup in January, cancel in February
    mock_validator_db.execute("INSERT INTO subscription_events VALUES ('evt_1', 'cust_1', 'plan_basic', 'signup', '2025-01-10', 19.00);")
    mock_validator_db.execute("INSERT INTO subscription_events VALUES ('evt_2', 'cust_1', NULL, 'cancel', '2025-02-10', 0.00);")
    
    # Assert end of month 1 spend is 19.0 (New)
    m1_mrr = mock_validator_db.execute("SELECT current_mrr FROM v_mrr_movements WHERE month_date = '2025-01-01'").fetchone()[0]
    assert float(m1_mrr) == 19.0, f"Expected January ending MRR to be 19.0, got {m1_mrr}"
    
    # Assert end of month 2 spend is 0.0 after cancellation (Churn)
    m2_mrr = mock_validator_db.execute("SELECT current_mrr FROM v_mrr_movements WHERE month_date = '2025-02-01'").fetchone()[0]
    assert float(m2_mrr) == 0.0, f"Expected February ending MRR to be 0.0 after cancellation, got {m2_mrr}"
    
    m2_category = mock_validator_db.execute("SELECT mrr_category FROM v_mrr_movements WHERE month_date = '2025-02-01'").fetchone()[0]
    assert m2_category == 'Churn', f"Expected category 'Churn' in February, got {m2_category}"

def test_duplicate_primary_keys_rejected(temp_db_conn):
    """Asserts that duplicate plan and customer keys violate PRIMARY KEY constraints."""
    # 1. Duplicate plan key
    temp_db_conn.execute("INSERT INTO dim_plans VALUES ('plan_dup', 'P1', 10.0, 'monthly');")
    with pytest.raises(duckdb.ConstraintException):
        temp_db_conn.execute("INSERT INTO dim_plans VALUES ('plan_dup', 'P2', 20.0, 'monthly');")
        
    # 2. Duplicate customer key
    temp_db_conn.execute("INSERT INTO dim_customers VALUES ('cust_dup', 'C1', '2025-01-01', 'US', 'Tech', 'SMB');")
    with pytest.raises(duckdb.ConstraintException):
        temp_db_conn.execute("INSERT INTO dim_customers VALUES ('cust_dup', 'C2', '2025-01-01', 'US', 'Tech', 'SMB');")
