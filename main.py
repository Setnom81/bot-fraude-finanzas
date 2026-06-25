from datetime import datetime

from config import DEFAULT_START_DATE, QUERY_TEMPLATE
from gmail_client import GmailClient
from parser import BacParser
from storage import TransactionStorage


def iso_to_gmail_date(value):
    if not value:
        return DEFAULT_START_DATE

    dt = datetime.fromisoformat(value)
    return dt.strftime("%Y/%m/%d")


def main():
    storage = TransactionStorage()
    data = storage.load()

    start_date = iso_to_gmail_date(data.get("last_sync"))
    query = QUERY_TEMPLATE.format(start_date=start_date)

    print(f"Buscando correos con query:")
    print(query)

    gmail = GmailClient()
    parser = BacParser()

    processed_ids = storage.get_processed_ids(data)
    messages = gmail.search_messages(query)

    print(f"Correos encontrados: {len(messages)}")

    new_transactions = []

    for item in messages:
        message_id = item["id"]

        if message_id in processed_ids:
            print(f"Saltando duplicado: {message_id}")
            continue

        message = gmail.get_message(message_id)
        payload = message.get("payload", {})
        headers = payload.get("headers", [])
        body = gmail.get_body(payload)

        transaction = parser.parse(
            message_id=message_id,
            headers=headers,
            body=body,
            gmail_client=gmail
        )

        new_transactions.append(transaction)
        print(f"Transacción detectada: {transaction.amount} - {transaction.merchant}")

    storage.add_transactions(data, new_transactions)
    storage.save(data)

    print(f"Nuevas transacciones: {len(new_transactions)}")
    print(f"Total guardadas: {len(data['transactions'])}")


if __name__ == "__main__":
    main()