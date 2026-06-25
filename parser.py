"""
BAC Parser

Se encarga de convertir el contenido de un correo del BAC
en un objeto Transaction.

Si en el futuro agregas otros bancos, cada uno debería tener
su propio parser (por ejemplo PromericaParser, BNParser, etc.).
"""

import re
from datetime import datetime

from models import Transaction


class BacParser:

    # ==========================================================
    # API PÚBLICA
    # ==========================================================

    def parse(self, message_id, headers, body, gmail_client):
        """
        Convierte un correo de Gmail en una Transaction.
        """

        amount_raw = self.extract_amount_raw(body)

        return Transaction(
            message_id=message_id,

            bank="BAC",

            amount=amount_raw,

            amount_value=self.extract_amount_value(amount_raw),

            currency=self.extract_currency(amount_raw),

            merchant=self.extract_merchant(body),

            card_last4=self.extract_card_last4(body),

            transaction_date=self.extract_transaction_date(body),

            authorization=self.extract_authorization(body),

            email_from=gmail_client.get_header(headers, "From"),

            email_to=gmail_client.get_header(headers, "To"),

            email_subject=gmail_client.get_header(headers, "Subject"),

            email_date=gmail_client.get_header(headers, "Date"),

            processed_at=datetime.now().isoformat(),

            body=body
        )

    # ==========================================================
    # UTILIDADES
    # ==========================================================

    @staticmethod
    def clean_text(text):
        """
        Elimina espacios repetidos y saltos de línea.
        """

        return " ".join(text.split())

    # ==========================================================
    # MONTO
    # ==========================================================

    def extract_amount_raw(self, body):
        """
        Devuelve el monto exactamente como aparece
        en el correo.

        Ejemplos:

        ₡12,500.00

        USD 25.75

        $50.00
        """

        match = re.search(

            r"(₡|CRC|USD|\$)\s?[\d.,]+",

            self.clean_text(body),

            re.IGNORECASE

        )

        return match.group(0) if match else None

    def extract_currency(self, amount):
        """
        Determina la moneda.
        """

        if not amount:
            return None

        amount = amount.upper()

        if "₡" in amount or "CRC" in amount:
            return "CRC"

        if "$" in amount or "USD" in amount:
            return "USD"

        return None

    def extract_amount_value(self, amount):
        """
        Convierte el monto en float.

        Ejemplo:

        ₡12,500.75

        →

        12500.75
        """

        if not amount:
            return None

        value = (

            amount.upper()

            .replace("CRC", "")

            .replace("USD", "")

            .replace("₡", "")

            .replace("$", "")

            .strip()

        )

        # BAC normalmente usa:
        #
        # 12,500.75
        #
        # quitamos separador de miles

        value = value.replace(",", "")

        try:
            return float(value)

        except ValueError:
            return None

    # ==========================================================
    # COMERCIO
    # ==========================================================

    def extract_merchant(self, body):
        """
        Intenta encontrar el comercio.
        """

        match = re.search(

            r"(?:comercio|establecimiento|afiliado|local|empresa)\s*[:\-]?\s*(.+?)(?:fecha|monto|tarjeta|autorizaci[oó]n|referencia|$)",

            self.clean_text(body),

            re.IGNORECASE

        )

        return match.group(1).strip() if match else None

    # ==========================================================
    # TARJETA
    # ==========================================================

    def extract_card_last4(self, body):
        """
        Obtiene los últimos cuatro dígitos
        de la tarjeta.
        """

        match = re.search(

            r"(?:tarjeta|terminada en|finalizada en|últimos|ultimos|x{2,}|\*{2,})\s*(\d{4})",

            self.clean_text(body),

            re.IGNORECASE

        )

        return match.group(1) if match else None

    # ==========================================================
    # FECHA
    # ==========================================================

    def extract_transaction_date(self, body):
        """
        Busca una fecha dentro del correo.
        """

        match = re.search(

            r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",

            self.clean_text(body)

        )

        return match.group(0) if match else None

    # ==========================================================
    # AUTORIZACIÓN
    # ==========================================================

    def extract_authorization(self, body):
        """
        Obtiene el código de autorización
        o referencia.
        """

        match = re.search(

            r"(?:autorizaci[oó]n|autorizacion|aprobaci[oó]n|referencia)\s*[:#-]?\s*([A-Z0-9-]+)",

            self.clean_text(body),

            re.IGNORECASE

        )

        return match.group(1) if match else None