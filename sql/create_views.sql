CREATE OR REPLACE VIEW v_mrr_movements AS
WITH 
-- 1. Generate a continuous sequence of monthly dates (the spine timeline)
months AS (
    SELECT CAST(generate_series AS DATE) AS month_date
    FROM generate_series(
        (SELECT DATE_TRUNC('month', MIN(event_date))::DATE FROM subscription_events),
        (SELECT DATE_TRUNC('month', MAX(event_date))::DATE FROM subscription_events),
        INTERVAL '1 month'
    )
),

-- 2. Find the absolute first event month for each customer
customer_range AS (
    SELECT 
        customer_id, 
        DATE_TRUNC('month', MIN(event_date))::DATE AS first_month
    FROM subscription_events
    GROUP BY customer_id
),

-- 3. Multiply customers by months to generate a dense grid (the Date Spine)
customer_months AS (
    SELECT 
        cr.customer_id,
        cr.first_month,
        m.month_date
    FROM customer_range cr
    CROSS JOIN months m
    WHERE m.month_date >= cr.first_month
),

-- 4. Retrieve the active spend and plan for each customer-month combination
customer_monthly_spend AS (
    SELECT 
        cm.customer_id,
        cm.first_month,
        cm.month_date,
        COALESCE(
            (
                SELECT se.monthly_amount
                FROM subscription_events se
                WHERE se.customer_id = cm.customer_id
                  -- Find the last event occurring before the next month starts
                  AND se.event_date < cm.month_date + INTERVAL '1 month'
                ORDER BY se.event_date DESC, se.event_id DESC
                LIMIT 1
            ), 
            0.0
        ) AS current_mrr,
        (
            SELECT se.plan_id
            FROM subscription_events se
            WHERE se.customer_id = cm.customer_id
              AND se.event_date < cm.month_date + INTERVAL '1 month'
            ORDER BY se.event_date DESC, se.event_id DESC
            LIMIT 1
        ) AS current_plan_id
    FROM customer_months cm
),

-- 5. Retrieve the prior month's MRR and plan ID for comparison
customer_mom AS (
    SELECT 
        cms.customer_id,
        cms.first_month,
        cms.month_date,
        cms.current_mrr,
        cms.current_plan_id,
        COALESCE(
            LAG(cms.current_mrr, 1) OVER (PARTITION BY cms.customer_id ORDER BY cms.month_date),
            0.0
        ) AS prev_mrr,
        LAG(cms.current_plan_id, 1) OVER (PARTITION BY cms.customer_id ORDER BY cms.month_date) AS prev_plan_id
    FROM customer_monthly_spend cms
),

-- 6. Apply conditional CASE WHEN logic to categorize transitions
classified_movements AS (
    SELECT 
        cmom.customer_id,
        cmom.month_date,
        cmom.current_mrr,
        cmom.prev_mrr,
        cmom.current_plan_id,
        cmom.prev_plan_id,
        (cmom.current_mrr - cmom.prev_mrr) AS mrr_change,
        CASE
            -- No change in recurring spend
            WHEN cmom.current_mrr = cmom.prev_mrr THEN 'No Change'
            
            -- Spend increased from $0.00
            WHEN cmom.prev_mrr = 0.0 AND cmom.current_mrr > 0.0 THEN
                CASE 
                    -- If this is their absolute first month active, it is "New"
                    WHEN cmom.month_date = cmom.first_month THEN 'New'
                    -- If they signed up previously but were cancelled, it is "Reactivation"
                    ELSE 'Reactivation'
                END
            
            -- Active customer increases spend
            WHEN cmom.prev_mrr > 0.0 AND cmom.current_mrr > cmom.prev_mrr THEN 'Expansion'
            
            -- Active customer decreases spend but remains active
            WHEN cmom.prev_mrr > 0.0 AND cmom.current_mrr < cmom.prev_mrr AND cmom.current_mrr > 0.0 THEN 'Contraction'
            
            -- Active customer cancels entirely (spend drops to $0.00)
            WHEN cmom.prev_mrr > 0.0 AND cmom.current_mrr = 0.0 THEN 'Churn'
            
            -- Catch-all for inactive months
            ELSE 'Inactive'
        END AS mrr_category
    FROM customer_mom cmom
)

-- 7. Join the transformed model with customer and plan metadata
SELECT 
    cm.customer_id,
    c.customer_name,
    c.country,
    c.industry,
    c.company_size,
    c.signup_date,
    cm.month_date,
    cm.prev_mrr,
    cm.current_mrr,
    cm.mrr_change,
    cm.mrr_category,
    cm.prev_plan_id,
    p_prev.plan_name AS prev_plan_name,
    cm.current_plan_id,
    p_curr.plan_name AS current_plan_name
FROM classified_movements cm
JOIN dim_customers c ON cm.customer_id = c.customer_id
LEFT JOIN dim_plans p_prev ON cm.prev_plan_id = p_prev.plan_id
LEFT JOIN dim_plans p_curr ON cm.current_plan_id = p_curr.plan_id;
