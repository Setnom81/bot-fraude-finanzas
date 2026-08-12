import os
from dotenv import load_dotenv

load_dotenv()
# Defines the Gmail API permissions required by the application.
# The "gmail.modify" scope allows the app to read, modify, and label
# Gmail messages without permanently deleting them.
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

# Base directory where the application's configuration and data files
# are stored.
DATA_DIR = "data"

# Path to the OAuth token file.
# This file stores the user's access and refresh tokens after
# successful authentication.
TOKEN_FILE = f"{DATA_DIR}/token.json"

# Path to the Google OAuth client credentials file.
# This file is downloaded from the Google Cloud Console and contains
# the application's Client ID and Client Secret.
CREDENTIALS_FILE = f"{DATA_DIR}/credentials.json"

# Path to the JSON file used to store processed transaction data.
# This allows the application to persist transaction history between runs.
TRANSACTIONS_FILE = f"{DATA_DIR}/transactions.json"

# Default starting date used when searching Gmail for transaction emails.
# The format follows Gmail's search query syntax: YYYY/MM/DD.
DEFAULT_START_DATE = "2026/01/01"

# Gmail search query template.
#
# The query searches for emails that:
# - Have the subject "Notificación de transacción".
# - Contain the keyword "bac".
# - Were received after the specified start date.
#
# The {start_date} placeholder is replaced at runtime with the desired date.
QUERY_TEMPLATE = (
    'subject:"Notificación de transacción" '
    'bac '
)

# Load Outlook Credentials from .env
OUTLOOK_CLIENT_ID = os.getenv('OUTLOOK_CLIENT_ID') 
OUTLOOK_CLIENT_SECRET = os.getenv('OUTLOOK_CLIENT_SECRET')
OUTLOOK_SUBJECT = os.getenv('OUTLOOK_SUBJECT')

# Outlook Scopes
outlook_scopes = ['https://graph.microsoft.com/Mail.ReadWrite', 'https://graph.microsoft.com/Mail.Send']

# Database Configuration
DB_HOST = "localhost"
DB_PORT = 3306
DB_USER = "app_user"
DB_PASSWORD = "user_password_here"  # La contraseña definida en docker-compose.yml
DB_NAME = "finance_db"