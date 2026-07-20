import random
from datetime import datetime, timedelta
import pandas as pd
from src.config import SIM_START_DATE, SIM_END_DATE, NUM_CUSTOMERS

# Set seed for reproducibility across all runs
random.seed(42)

INDUSTRIES = ["Tech", "Finance", "Healthcare", "Retail", "Education"]
COUNTRIES = ["US", "UK", "Canada", "Germany", "Australia", "India"]
COMPANY_SIZES = ["SMB", "Mid-Market", "Enterprise"]


COMPANY_PREFIXES = [
    "Acme", "Apex", "Nova", "Vortex", "Sentry", "Quantum", "Nexus", "Zenith", "Beacon", "Cloud",
    "Alpha", "Beta", "Gamma", "Delta", "Omega", "Helix", "Vector", "Summit", "Prime", "Vertex",
    "Stellar", "Orion", "Synergy", "Matrix", "Krypton", "Hyperion", "Titan", "Atlas", "Crest", "Vanguard",
    "Pinnacle", "Stratis", "Intellect", "Catalyst", "Optima", "Infinity", "Horizon", "Core", "Aura", "Pulse"
]
COMPANY_SUFFIXES = [
    "Corp", "Inc", "Co", "Solutions", "Technologies", "Systems", "Labs", "Hub", "Group", "Enterprises",
    "Networks", "Ventures", "Consulting", "Software", "Digital", "Data", "Global", "Dynamics", "Logic", "Media"
]

PLANS = [
    {"plan_id": "plan_basic", "plan_name": "Basic", "monthly_price": 19.00, "billing_cycle": "monthly"},
    {"plan_id": "plan_pro", "plan_name": "Professional", "monthly_price": 49.00, "billing_cycle": "monthly"},
    {"plan_id": "plan_enterprise", "plan_name": "Enterprise", "monthly_price": 199.00, "billing_cycle": "monthly"}
]

def generate_company_name() -> str:
    """Generates a randomized, realistic company name."""
    return f"{random.choice(COMPANY_PREFIXES)} {random.choice(COMPANY_SUFFIXES)}"

def generate_plans_df() -> pd.DataFrame:
    """Generates the dimensions dataframe for subscription plans."""
    return pd.DataFrame(PLANS)

def generate_customers_df() -> pd.DataFrame:
    """Generates synthetic B2B customers with industry, region, and segment size."""
    customers = []
    start_dt = datetime.strptime(SIM_START_DATE, "%Y-%m-%d")
    # Ensure most signups happen in the first 12 months to allow dynamic lifecycles
    end_signup_dt = start_dt + timedelta(days=365)
    
    for i in range(1, NUM_CUSTOMERS + 1):
        cust_id = f"cust_{i:03d}"
        cust_name = generate_company_name()
        
        # Random signup date in the signup window
        delta_days = random.randint(0, (end_signup_dt - start_dt).days)
        signup_dt = start_dt + timedelta(days=delta_days)
        
        # Weighted selection: 50% SMB, 35% Mid-Market, 15% Enterprise
        size = random.choices(COMPANY_SIZES, weights=[0.50, 0.35, 0.15], k=1)[0]
        
        customers.append({
            "customer_id": cust_id,
            "customer_name": cust_name,
            "signup_date": signup_dt.strftime("%Y-%m-%d"),
            "country": random.choice(COUNTRIES),
            "industry": random.choice(INDUSTRIES),
            "company_size": size
        })
    return pd.DataFrame(customers)

def generate_events_df(df_customers: pd.DataFrame) -> pd.DataFrame:
    """Simulates chronological subscription lifecycle events for customers."""
    events = []
    event_idx = 1
    end_dt = datetime.strptime(SIM_END_DATE, "%Y-%m-%d")
    
    # Plan price lookup for event generation
    plan_prices = {p["plan_id"]: p["monthly_price"] for p in PLANS}
    plan_ids = [p["plan_id"] for p in PLANS]
    
    for _, cust in df_customers.iterrows():
        cust_id = cust["customer_id"]
        signup_date_str = cust["signup_date"]
        current_date = datetime.strptime(signup_date_str, "%Y-%m-%d")
        
        # 1. Signup event
        current_plan = random.choice(plan_ids)
        current_amount = plan_prices[current_plan]
        status = "active"
        
        events.append({
            "event_id": f"evt_{event_idx:04d}",
            "customer_id": cust_id,
            "plan_id": current_plan,
            "event_type": "signup",
            "event_date": current_date.strftime("%Y-%m-%d"),
            "monthly_amount": float(current_amount)
        })
        event_idx += 1
        
        # 2. Subsequent lifecycle events
        while current_date < end_dt:
            # Advance time randomly (15 to 45 days) to model mid-month actions
            current_date += timedelta(days=random.randint(15, 45))
            if current_date > end_dt:
                break
                
            # 15% probability of an event triggering in any step
            if random.random() > 0.15:
                continue
                
            # Initialize event_type before conditional assignment
            event_type = None
            
            if status == "active":
                action = random.choice(["upgrade", "downgrade", "cancel"])
                
                if action == "upgrade":
                    if current_plan == "plan_basic":
                        current_plan = "plan_pro"
                        event_type = "upgrade"
                    elif current_plan == "plan_pro":
                        current_plan = "plan_enterprise"
                        event_type = "upgrade"
                    else:
                        # Enterprise cannot upgrade, downgrade instead
                        current_plan = "plan_pro"
                        event_type = "downgrade"
                    current_amount = plan_prices[current_plan]
                        
                elif action == "downgrade":
                    if current_plan == "plan_enterprise":
                        current_plan = "plan_pro"
                        event_type = "downgrade"
                    elif current_plan == "plan_pro":
                        current_plan = "plan_basic"
                        event_type = "downgrade"
                    else:
                        # Basic cannot downgrade, cancel instead
                        current_plan = "plan_basic"
                        event_type = "cancel"
                        current_amount = 0.0
                        status = "inactive"
                        
                    if status == "active":
                        current_amount = plan_prices[current_plan]
                        
                elif action == "cancel":
                    event_type = "cancel"
                    current_amount = 0.0
                    status = "inactive"
                    current_plan = None
                    
                events.append({
                    "event_id": f"evt_{event_idx:04d}",
                    "customer_id": cust_id,
                    "plan_id": current_plan,
                    "event_type": event_type,
                    "event_date": current_date.strftime("%Y-%m-%d"),
                    "monthly_amount": float(current_amount)
                })
                event_idx += 1
                
            elif status == "inactive":
                # Reactivation (30% weight when inactive)
                if random.random() < 0.3:
                    current_plan = random.choice(plan_ids)
                    current_amount = plan_prices[current_plan]
                    status = "active"
                    
                    events.append({
                        "event_id": f"evt_{event_idx:04d}",
                        "customer_id": cust_id,
                        "plan_id": current_plan,
                        "event_type": "reactivate",
                        "event_date": current_date.strftime("%Y-%m-%d"),
                        "monthly_amount": float(current_amount)
                    })
                    event_idx += 1
                    
    return pd.DataFrame(events)

def get_synthetic_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Compiles and returns synthetic plans, customers, and events dataframes."""
    df_plans = generate_plans_df()
    df_customers = generate_customers_df()
    df_events = generate_events_df(df_customers)
    return df_plans, df_customers, df_events
