"""Interactive Outlook sign-in.

Run it by hand from the project folder whenever the bot reports that the
Outlook login is missing or expired:

    .venv/bin/python -m src.outlook_login

It prints a Microsoft URL; open it, approve, and paste back the address you
are redirected to. The token is saved where the service reads it.
"""

from src.config import outlook_scopes
from src.ingestion.outlook_client import build_account


def main() -> None:
    account = build_account()
    if account.authenticate(requested_scopes=outlook_scopes):
        print("Outlook login saved. Restart the service: sudo systemctl restart bot-fraude")
    else:
        raise SystemExit("Outlook login failed.")


if __name__ == "__main__":
    main()
