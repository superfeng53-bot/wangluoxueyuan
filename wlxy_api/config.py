from pathlib import Path

SITE_URL = "https://www.wlxy.org.cn/"
BASE_URL = SITE_URL
API_BASE_URL = "https://api.cdwork.cn"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
DEFAULT_DEVICE = "2"
DEFAULT_HIERARCHY = "A1-1-1-1-"

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_ACCOUNT_FILE = DATA_DIR / "account.json"
DEFAULT_COOKIES_FILE = DATA_DIR / "cookies.json"
DEFAULT_USER_PROFILE_FILE = DATA_DIR / "user_profile.json"

TOKEN_COOKIE_KEY = "user_token"
