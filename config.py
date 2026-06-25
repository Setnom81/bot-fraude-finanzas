SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

DATA_DIR = "data"

TOKEN_FILE = f"{DATA_DIR}/token.json"
CREDENTIALS_FILE = f"{DATA_DIR}/credentials.json"
TRANSACTIONS_FILE = f"{DATA_DIR}/transactions.json"

DEFAULT_START_DATE = "2026/01/01"

QUERY_TEMPLATE = (
    'subject:"Notificación de transacción" '
    'bac '
    'after:{start_date}'
)