# Imports the class that handles the OAuth 2.0 authentication flow
# for installed applications (desktop apps or local scripts).
from google_auth_oauthlib.flow import InstalledAppFlow

# Defines the permissions (scopes) the application is requesting.
# In this case:
# - gmail.modify: allows the application to read, modify, and label
#   Gmail messages, but not permanently delete them.
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

# Creates the OAuth authentication flow using the client credentials
# downloaded from the Google Cloud Console.
#
# The "credentials.json" file contains the application's
# Client ID and Client Secret.
flow = InstalledAppFlow.from_client_secrets_file(
    "data/credentials.json",
    SCOPES
)

# Starts the OAuth authentication process.
#
# A browser window will automatically open so the user can:
#   1. Sign in to their Google account.
#   2. Grant the requested permissions.
#
# Setting port=0 allows the operating system to automatically
# choose an available local port for the callback.
creds = flow.run_local_server(port=0)

# Saves the access token and refresh token to a JSON file.
#
# This allows future executions of the application to reuse the
# existing authorization without requiring the user to log in again,
# as long as the refresh token remains valid.
with open("data/token.json", "w") as token:
    token.write(creds.to_json())

# Prints a confirmation message indicating that the authentication
# completed successfully and the token was saved.
print("token.json created successfully")