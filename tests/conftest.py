import pytest
import duckdb
import contextlib
from src.pipeline import run_ddl_setup
from src.config import SQL_VIEWS_PATH
from src.utils import get_db_connection

@pytest.fixture
def db_conn():
    """Provides a read-only connection to the production DuckDB database."""
    with get_db_connection(read_only=True) as conn:
        yield conn

@pytest.fixture
def temp_db_conn():
    """Creates a clean in-memory DuckDB database with schema and transform views loaded."""
    conn = duckdb.connect(database=":memory:")
    # Initialize standard schemas
    run_ddl_setup(conn)
    
    # Compile the transform views
    with open(SQL_VIEWS_PATH, "r", encoding="utf-8") as f:
        sql_script = f.read()
    conn.execute(sql_script)
    
    yield conn
    conn.close()

@pytest.fixture
def mock_validator_db(temp_db_conn, monkeypatch):
    """Mocks get_db_connection in src.validator to use the in-memory temporary database."""
    @contextlib.contextmanager
    def mock_conn(read_only=False):
        yield temp_db_conn
    monkeypatch.setattr("src.validator.get_db_connection", mock_conn)
    return temp_db_conn
