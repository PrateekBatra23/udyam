import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("TESSDATA_PREFIX", "C:/Users/prate/miniconda3/share/tessdata")


@pytest.fixture(scope="session")
def store():
    from data_store import get_store
    return get_store()


def db_available() -> bool:
    try:
        import db
        db.init_db()
        return True
    except Exception:
        return False


needs_db = pytest.mark.skipif(not db_available(), reason="PostgreSQL not running")
