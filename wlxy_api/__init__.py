"""wlxy_api — HTTP toolkit for WLXY."""
from .captcha_limiter import configure_state_file
from .config import DATA_DIR
from .session_manager import SessionManager, get_session_manager

configure_state_file(DATA_DIR / "captcha-state.json")

__all__ = ["SessionManager", "get_session_manager"]
