# 🛡️ Bot de Detección de Fraude Financiero (`bot-fraude-finanzas`)

Sistema daemonizado y automatizado en Python para el monitoreo en tiempo real de notificaciones bancarias (BAC Credomatic) mediante **Microsoft Graph API (Outlook)** y **Gmail API**, evaluación de riesgo híbrida (Machine Learning + Motor de Reglas) y alertas instantáneas a dispositivos móviles mediante **Telegram Bot API**.

---

## 📐 Arquitectura del Sistema

```text
[ Email Inbox (Outlook / Gmail) ]
       │
       ▼ (Polling cada 2 min / Ventana 5 min)
[ outlook_listener.py ] ──► Deduplicación ──► [ Database (Storage) ]
       │
       ▼
[ Data Preprocessor ] (Normalización UTC & Feature Engineering)
       │
       ▼
[ Hybrid Evaluator ] (Modelo ML + Motor de Reglas)
       │
       ├──► Si es de Alto Riesgo ──► [ Telegram Bot API ]
       └──► Si es Transacción Normal ──► Persistencia en BD
```

---

## Tecnologías Utilizadas

* **Lenguaje:** Python 3.12
* **Integración API Email:** `O365` (Microsoft Graph API para Outlook), Gmail API
* **Contenerización y Base de Datos:** Docker Compose, MySQL 8.0, Adminer
* **Machine Learning & Datos:** `pandas`, `scikit-learn`, `joblib`
* **Notificaciones:** Telegram Bot API
* **Orquestación en Servidor:** Linux `systemd`, Scripting en Bash

---

## Estructura del Proyecto

```text
bot-fraude-finanzas/
├── data/                        # Dataset local y almacenamiento de transacciones
├── models/                      # Artefactos y modelos entrenados de ML (.joblib)
├── notebooks/                   # Notebooks de Jupyter para EDA y experimentación
├── src/
│   ├── alerts/
│   │   ├── notifier.py          # Orquestador central de notificaciones
│   │   └── telegram.py          # Cliente de envío de alertas a Telegram API
│   ├── core/
│   │   └── models.py            # Modelos de datos y esquemas de dominio
│   ├── dashboard/
│   │   └── app.py               # Panel/Interfaz de visualización de métricas
│   ├── database/
│   │   └── storage.py           # Capa de persistencia y conexión a base de datos
│   ├── ingestion/
│   │   ├── parsers/
│   │   │   └── bac_parser.py    # Extracción y limpieza de correos BAC Credomatic
│   │   ├── gmail_client.py      # Cliente de ingesta vía Gmail API
│   │   └── outlook_client.py    # Cliente de ingesta vía Microsoft Graph API (O365)
│   ├── ml/
│   │   ├── data_preprocessing.py# Preprocesamiento, fechas UTC y feature engineering
│   │   ├── evaluator.py         # Evaluador híbrido de score de riesgo
│   │   ├── inference.py         # Inferencia del modelo y disparo de alertas
│   │   ├── model.py             # Clase de envoltura del modelo de ML
│   │   └── train.py             # Script de entrenamiento y reentrenamiento del modelo
│   ├── services/
│   │   └── outlook_listener.py  # Daemon de monitoreo continuo en segundo plano
│   ├── .env                     # Variables de entorno y llaves secretas (local)
│   ├── .env.example             # Plantilla de variables de entorno
│   ├── auth.py                  # Script de autenticación inicial OAuth
│   ├── config.py                # Carga de configuración global y constantes
│   └── main.py                  # Ingesta masiva inicial / Ejecución principal
├── .gitignore
├── docker-compose.yaml          # Infraestructura Docker (MySQL, Adminer)
├── get-docker.sh                # Script auxiliar de instalación de Docker
├── o365_token.txt               # Token de autenticación guardado por O365
├── README.md                    # Documentación del proyecto
├── requirements.txt             # Dependencias del proyecto
└── startup.sh                   # Script Bash de orquestación para systemd
```

---

## Configuración del Entorno

Crea un archivo `.env` dentro de la carpeta `src/` basándote en `src/.env.example`:

```env
# Configuración de Base de Datos MySQL (Docker)
DB_HOST=localhost
DB_PORT=3306
DB_NAME=finance_db
DB_USER=root
DB_PASSWORD=tu_password_mysql

# Credenciales de Microsoft Graph API (Outlook)
OUTLOOK_CLIENT_ID="tu_outlook_client_id"
OUTLOOK_CLIENT_SECRET="tu_outlook_client_secret"
OUTLOOK_SUBJECT="Notificacion de transaccion"

# Configuración del Bot de Telegram
TELEGRAM_BOT_TOKEN="tu_telegram_bot_token"
TELEGRAM_CHAT_ID="tu_telegram_chat_id"
```

---

## Instalación y Despliegue

### 1. Configurar entorno virtual Python

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Iniciar contenedores con Docker

```bash
docker compose up -d
```

### 3. Ejecución Manual (Pruebas)

* **Ejecutar proceso principal (Backfill/Ingesta inicial):**
  ```bash
  python src/main.py
  ```

* **Iniciar el Daemon Listener manualmente:**
  ```bash
  python -m src.services.outlook_listener
  ```

---

## Despliegue Automatizado en Servidor (`systemd`)

El proyecto se ejecuta en segundo plano mediante `systemd` usando el orquestador `startup.sh`.

### Configuración del servicio en Linux:

1. Asignar permisos de ejecución al script:
   ```bash
   chmod +x startup.sh
   ```

2. Crear el archivo de servicio `systemd`:
   ```bash
   sudo nano /etc/systemd/system/bot-fraude.service
   ```

3. Contenido del servicio:
   ```ini
   [Unit]
   Description=Bot Fraude Finanzas - Startup Service
   After=network-online.target docker.service
   Wants=network-online.target docker.service

   [Service]
   Type=simple
   User=user
   WorkingDirectory=
   Environment="PYTHONPATH="
   ExecStart=path/startup.sh
   Restart=always
   RestartSec=10
   StandardOutput=append:path/bot-fraude-finanzas/service_output.log
   StandardError=append:path/service_error.log

   [Install]
   WantedBy=multi-user.target
   ```

4. Habilitar y reiniciar el servicio:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable bot-fraude.service
   sudo systemctl restart bot-fraude.service
   ```

---

## Alertas de Telegram

Cuando el evaluador identifica una transacción que supera el umbral de riesgo (`is_high_risk = True`), notifica instantáneamente vía Telegram:

* **Monto:** CRC 150,000.00  
* **Comercio:** TIENDA DESCONOCIDA ONLINE  
* **Fecha:** 2026-08-12 22:00:00 UTC  
* **Score de Riesgo:** 92.50%