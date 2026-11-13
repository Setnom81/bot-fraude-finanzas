import os
from pathlib import Path

from dotenv import load_dotenv

# Repository root and the .env that lives next to this file. Loading it by
# explicit path means the service works no matter what the working directory is.
SRC_DIR = Path(__file__).resolve().parent
ROOT_DIR = SRC_DIR.parent
load_dotenv(SRC_DIR / ".env")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Gmail (legacy historical import, see src/main.py)
# ---------------------------------------------------------------------------
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
DATA_DIR = "data"
TOKEN_FILE = f"{DATA_DIR}/token.json"
CREDENTIALS_FILE = f"{DATA_DIR}/credentials.json"
TRANSACTIONS_FILE = f"{DATA_DIR}/transactions.json"
DEFAULT_START_DATE = "2026/01/01"
QUERY_TEMPLATE = (
    'subject:"Notificación de transacción" '
    'bac '
)

# ---------------------------------------------------------------------------
# Outlook
# ---------------------------------------------------------------------------
OUTLOOK_CLIENT_ID = os.getenv("OUTLOOK_CLIENT_ID")
OUTLOOK_CLIENT_SECRET = os.getenv("OUTLOOK_CLIENT_SECRET")
OUTLOOK_SUBJECT = os.getenv("OUTLOOK_SUBJECT")

# The bot only reads mail. This is what the login script requests; a token
# obtained earlier keeps its old (broader) scopes until you log in again.
outlook_scopes = ["https://graph.microsoft.com/Mail.Read"]

# Where the O365 token cache is stored.
OUTLOOK_TOKEN_DIR = ROOT_DIR
OUTLOOK_TOKEN_FILENAME = "o365_token.txt"

# Only emails from these senders are treated as bank notifications.
_DEFAULT_SENDERS = (
    "notificacion@notificacionesbaccr.com,"
    "notificacion@baccredomatic.cr,"
    "notificacionbac@baccredomatic.cr"
)
ALLOWED_SENDERS = {
    s.strip().lower()
    for s in os.getenv("ALLOWED_SENDERS", _DEFAULT_SENDERS).split(",")
    if s.strip()
}

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = _env_int("DB_PORT", 3306)
DB_USER = os.getenv("DB_USER", "app_user")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME", "finance_db")

# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
# Timezone the card is used in. Hours ("night") are evaluated in this zone.
LOCAL_TZ = os.getenv("LOCAL_TZ", "America/Costa_Rica")

# Approximate exchange rate used to put USD and CRC amounts on one scale.
# It only needs to be roughly right; adjust it in .env if it drifts a lot.
USD_TO_CRC_RATE = _env_float("USD_TO_CRC_RATE", 500.0)

# The amount z-score is ignored until this many earlier transactions exist.
MIN_HISTORY_FOR_ZSCORE = _env_int("MIN_HISTORY_FOR_ZSCORE", 30)

MODEL_PATH = ROOT_DIR / "models" / "fraud_model.joblib"

# ---------------------------------------------------------------------------
# Listener
# ---------------------------------------------------------------------------
POLL_INTERVAL_SECONDS = _env_int("POLL_INTERVAL_SECONDS", 120)

# A high-risk transaction older than this is not alerted one by one; it is
# included in a single "late" summary instead (e.g. after the PC was off).
ALERT_MAX_AGE_HOURS = _env_int("ALERT_MAX_AGE_HOURS", 72)

# How far back to look on the very first run, when the database is empty.
INITIAL_LOOKBACK_DAYS = _env_int("INITIAL_LOOKBACK_DAYS", 3)

# Send a "bot is failing" Telegram message after this many failed cycles in a
# row, and repeat it every FAILURE_REMINDER_HOURS while it keeps failing.
FAILURE_ALERT_AFTER = _env_int("FAILURE_ALERT_AFTER", 3)
FAILURE_REMINDER_HOURS = _env_int("FAILURE_REMINDER_HOURS", 6)

# Local hour of the daily "still alive" message. Set to -1 to disable.
HEARTBEAT_HOUR = _env_int("HEARTBEAT_HOUR", 8)
