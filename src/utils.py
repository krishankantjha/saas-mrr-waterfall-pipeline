import contextlib
from collections.abc import Generator
import logging
import sys
import duckdb
from src.config import DB_PATH, DATA_DIR, PROJECT_ROOT

def setup_logger(name: str = "mrr_pipeline") -> logging.Logger:
    """Configures dual logging to the console (stdout) and a log file."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        
        # Format pattern: [Timestamp] LEVEL [logger:file:line] - Message
        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s [%(name)s:%(filename)s:%(lineno)d] - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        # File handler (creates logs/ folder if missing)
        logs_dir = PROJECT_ROOT / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(str(logs_dir / "pipeline.log"), encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
    return logger

# Shared logger instance for all pipeline modules
logger = setup_logger()

@contextlib.contextmanager
def get_db_connection(read_only: bool = False) -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """Safe connection context manager that prevents DuckDB file locking issues."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = None
    try:
        conn = duckdb.connect(database=str(DB_PATH), read_only=read_only)
        yield conn
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        raise e
    finally:
        if conn:
            conn.close()
