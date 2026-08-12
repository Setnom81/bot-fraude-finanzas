class AlertNotifier:
    """
    Handles immediate alerts for newly detected high-risk transactions.
    """

    def send_high_risk_alert(self, transaction: dict) -> None:
        """
        Trigger alert for transactions flagged as high risk.
        
        Args:
            transaction (dict): Evaluated transaction containing merchant, amount, score, etc.
        """
        merchant = transaction.get("merchant", "Unknown")
        amount = transaction.get("amount", 0.0)
        currency = transaction.get("currency", "CRC")
        score = transaction.get("final_risk_score", 0.0)

        print("\n" + "🚨" * 25)
        print(" ⚠️  ALERTA DE SEGURIDAD: TRANSACCIÓN SOSPECHOSA DETECTADA  ⚠️")
        print("🚨" * 25)
        print(f"  • Comercio: {merchant}")
        print(f"  • Monto: {currency} {amount:,.2f}")
        print(f"  • Risk Score: {score}/100 🔴")
        print("  • Acción recomendada: Verificar en banca en línea")
        print("🚨" * 25 + "\n")