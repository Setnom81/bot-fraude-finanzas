from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

flow = InstalledAppFlow.from_client_secrets_file(
    "data/credentials.json",
    SCOPES
)

creds = flow.run_local_server(port=0)

with open("data/token.json", "w") as token:
    token.write(creds.to_json())

print("token.json creado correctamente")