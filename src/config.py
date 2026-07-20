import pathlib

# Centralized directory paths
SRC_DIR: pathlib.Path = pathlib.Path(__file__).parent.resolve()
PROJECT_ROOT: pathlib.Path = SRC_DIR.parent
DATA_DIR: pathlib.Path = PROJECT_ROOT / "data"
SQL_DIR: pathlib.Path = PROJECT_ROOT / "sql"
DOCS_DIR: pathlib.Path = PROJECT_ROOT / "docs"

# Database path
DB_PATH: pathlib.Path = DATA_DIR / "mrr_waterfall.duckdb"

# Ingestion paths
SQL_VIEWS_PATH: pathlib.Path = SQL_DIR / "create_views.sql"

# Simulation configuration
SIM_START_DATE: str = "2025-01-01"
SIM_END_DATE: str = "2026-06-30"
NUM_CUSTOMERS: int = 1000
