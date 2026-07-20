from src.utils import get_db_connection, logger

def validate_mrr_reconciliation() -> bool:
    """Verifies that the financial MRR Waterfall logic reconciles to the exact cent for all months."""
    logger.info("Running validation check: MRR Waterfall Accounting Equation...")
    
    with get_db_connection(read_only=True) as conn:
        query = """
            SELECT 
                month_date,
                ROUND(SUM(prev_mrr), 2) AS starting_mrr,
                ROUND(SUM(current_mrr), 2) AS ending_mrr,
                ROUND(SUM(CASE WHEN mrr_category = 'New' THEN mrr_change ELSE 0.0 END), 2) AS new_mrr,
                ROUND(SUM(CASE WHEN mrr_category = 'Expansion' THEN mrr_change ELSE 0.0 END), 2) AS expansion_mrr,
                ROUND(SUM(CASE WHEN mrr_category = 'Reactivation' THEN mrr_change ELSE 0.0 END), 2) AS reactivation_mrr,
                ROUND(SUM(CASE WHEN mrr_category = 'Contraction' THEN mrr_change ELSE 0.0 END), 2) AS contraction_mrr,
                ROUND(SUM(CASE WHEN mrr_category = 'Churn' THEN mrr_change ELSE 0.0 END), 2) AS churn_mrr
            FROM v_mrr_movements
            GROUP BY month_date
            ORDER BY month_date;
        """
        df = conn.execute(query).df()
        
        passed = True
        for _, row in df.iterrows():
            month = str(row["month_date"])
            starting = float(row["starting_mrr"])
            ending = float(row["ending_mrr"])
            new_mrr = float(row["new_mrr"])
            expansion = float(row["expansion_mrr"])
            reactivation = float(row["reactivation_mrr"])
            contraction = float(row["contraction_mrr"])
            churn = float(row["churn_mrr"])
            
            # Note: contraction_mrr and churn_mrr are negative because they represent spend reductions.
            # Thus, we add them to Starting MRR instead of subtracting them.
            expected_ending = round(starting + new_mrr + expansion + reactivation + contraction + churn, 2)
            difference = round(abs(expected_ending - ending), 2)
            
            if difference != 0.0:
                logger.error(
                    f"MRR Reconciliation FAILED for month {month}: "
                    f"Expected Ending: ${expected_ending}, Actual Ending: ${ending} (Diff: ${difference})"
                )
                passed = False
            else:
                logger.debug(f"Month {month} reconciled successfully: ${ending}")
                
        if passed:
            logger.info("PASS: MRR Waterfall Accounting Equation balances to the exact cent for all months.")
        return passed
 
def validate_mrr_continuity() -> bool:
    """Verifies that Starting MRR of Month M matches Ending MRR of Month M-1 exactly."""
    logger.info("Running validation check: Month-over-Month MRR Continuity...")
    
    with get_db_connection(read_only=True) as conn:
        query = """
            SELECT 
                month_date,
                ROUND(SUM(prev_mrr), 2) AS starting_mrr,
                ROUND(SUM(current_mrr), 2) AS ending_mrr
            FROM v_mrr_movements
            GROUP BY month_date
            ORDER BY month_date;
        """
        df = conn.execute(query).df()
        
        passed = True
        # Skip the first month (index 0) because it has no prior month to compare against.
        for i in range(1, len(df)):
            current_month = str(df.loc[i, "month_date"])
            starting_mrr = float(df.loc[i, "starting_mrr"])
            prev_ending_mrr = float(df.loc[i-1, "ending_mrr"])
            
            difference = round(abs(starting_mrr - prev_ending_mrr), 2)
            if difference != 0.0:
                logger.error(
                    f"MRR Continuity FAILED for {current_month}: "
                    f"Starting MRR (${starting_mrr}) does not match previous month's Ending MRR (${prev_ending_mrr}). Diff: ${difference}"
                )
                passed = False
                
        if passed:
            logger.info("PASS: Month-over-Month MRR Continuity matches exactly across the entire timeline.")
        return passed

def validate_customer_counts() -> bool:
    """Verifies that the distinct customer count in v_mrr_movements aligns with dim_customers."""
    logger.info("Running validation check: Customer Count Consistency...")
    
    with get_db_connection(read_only=True) as conn:
        dim_cust_count = conn.execute("SELECT COUNT(DISTINCT customer_id) FROM dim_customers;").fetchone()[0]
        view_cust_count = conn.execute("SELECT COUNT(DISTINCT customer_id) FROM v_mrr_movements;").fetchone()[0]
        
        if dim_cust_count != view_cust_count:
            logger.error(
                f"Customer count mismatch: dim_customers has {dim_cust_count} rows, "
                f"but view v_mrr_movements has {view_cust_count} distinct customers."
            )
            return False
            
        logger.info(f"PASS: Customer count is consistent across tables ({view_cust_count} customers).")
        return True

def validate_referential_integrity() -> bool:
    """Verifies that there are no orphan customer or plan references in v_mrr_movements."""
    logger.info("Running validation check: Database Referential Integrity...")
    
    with get_db_connection(read_only=True) as conn:
        # 1. Check for orphaned customers in view
        orphan_customers = conn.execute("""
            SELECT COUNT(*) 
            FROM v_mrr_movements v
            LEFT JOIN dim_customers c ON v.customer_id = c.customer_id
            WHERE c.customer_id IS NULL;
        """).fetchone()[0]
        
        # 2. Check for orphaned current plans in view (ignoring NULL plans which are cancellations)
        orphan_plans = conn.execute("""
            SELECT COUNT(*) 
            FROM v_mrr_movements v
            LEFT JOIN dim_plans p ON v.current_plan_id = p.plan_id
            WHERE v.current_plan_id IS NOT NULL AND p.plan_id IS NULL;
        """).fetchone()[0]
        
        if orphan_customers > 0:
            logger.error(f"Referential integrity failure: Found {orphan_customers} orphan customer rows in views.")
            return False
        if orphan_plans > 0:
            logger.error(f"Referential integrity failure: Found {orphan_plans} orphan plan references in views.")
            return False
            
        logger.info("PASS: Referential integrity holds. No orphan references detected.")
        return True

def run_all_validations() -> bool:
    """Orchestrates and executes all database validation rules."""
    logger.info("=== Starting Pipeline Data Validations ===")
    
    reconciliation = validate_mrr_reconciliation()
    continuity = validate_mrr_continuity()
    customer_counts = validate_customer_counts()
    integrity = validate_referential_integrity()
    
    success = reconciliation and continuity and customer_counts and integrity
    if success:
        logger.info("=== All Database Validations Passed! ===")
    else:
        logger.error("=== Database Validation FAIL ===")
        
    return success

if __name__ == "__main__":
    import sys
    success = run_all_validations()
    sys.exit(0 if success else 1)
