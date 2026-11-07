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


@pytest.fixture(autouse=True)
def never_call_the_real_llm(monkeypatch):
    """The developer's .env may hold a real Gemini key. Tests must never use it: they either run
    rules-only or inject a fake client explicitly (`client=` / the fakes in test_advisor_llm.py)."""
    import config
    monkeypatch.setattr(config, "USE_LLM", False)
    monkeypatch.setattr(config, "LLM_API_KEY", "")
    try:
        from advisor import llm

        def blocked():
            raise AssertionError("a test tried to create a real LLM client")
        monkeypatch.setattr(llm, "make_client", blocked)
    except ImportError:
        pass
