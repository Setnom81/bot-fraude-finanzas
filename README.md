# Bot Fraude Finanzas

Sistema automatizado de ingesta, procesamiento e identificación de transacciones bancarias (BAC Credomatic) a partir de notificaciones por correo electrónico, diseñado para la posterior detección de anomalías y fraude mediante Machine Learning.

Actualmente el proyecto:

- **Ingesta multicanal:** Lee correos de notificación del BAC desde **Gmail API** y **Microsoft Outlook (Microsoft Graph API)**.
- **Procesamiento inteligente:** Extrae datos estructurados (monto, comercio, fecha, tarjeta) evitando correos duplicados.
- **Persistencia en MySQL:** Guarda transacciones procesadas y metadatos de sincronización en base de datos relacional.
- **Entorno contenerizado:** Levanta la infraestructura de base de datos rápidamente con Docker Compose.
- **Arquitectura modular:** Código estructurado en capas dentro de `src/` para escalabilidad.

---

## Requisitos Previos

- **Python 3.11+**
- **Docker y Docker Compose** (para la base de datos MySQL)
- **Cuenta de Google** (si usas Gmail) con proyecto en Google Cloud
- **Cuenta de Microsoft** (si usas Outlook) con aplicación registrada en Azure Portal

---

## Instalación y Configuración

### 1. Clonar el repositorio e instalar dependencias

```bash
git clone [https://github.com/Setnom81/bot-fraude-finanzas.git](https://github.com/Setnom81/bot-fraude-finanzas.git)
cd bot-fraude-finanzas

# Crear y activar entorno virtual
python3 -m venv .venv
source .venv/bin/activate  # En Linux/macOS
# .venv\Scripts\activate   # En Windows

# Instalar librerías
pip install -r requirements.txt
```

---

### 2. Variables de Entorno (`.env`)

Crea un archivo `.env` en la raíz del proyecto tomando como plantilla `.env.example`:

```bash
cp .env.example .env
```

Configura tus credenciales de base de datos y de las APIs correspondientes en `.env`:

```env
# MySQL Database Config
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=tu_password
DB_NAME=bot_fraude_db

# Microsoft Outlook API Config
OUTLOOK_CLIENT_ID=tu_client_id_azure
OUTLOOK_CLIENT_SECRET=tu_client_secret_azure
```

---

### 3. Configuración de Proveedores de Correo

#### Opción A: Configurar Gmail API

1. Ve a [Google Cloud Console](https://console.cloud.google.com/) y crea un proyecto.
2. Habilita la **Gmail API** en *APIs y Servicios > Biblioteca*.
3. Configura la *Pantalla de consentimiento OAuth* (tipo Externo) y añade tu correo en *Usuarios de prueba*.
4. Crea credenciales de **ID de cliente OAuth (Aplicación de escritorio)**.
5. Descarga el JSON, renómbralo a `credentials.json` y colócalo en la carpeta `data/`:
   ```text
   data/
   └── credentials.json
   ```
6. Corre el script de autenticación inicial (se abrirá el navegador):
   ```bash
   python auth.py
   ```

#### Opción B: Configurar Outlook (Microsoft Graph API)

1. Registra una aplicación en [Azure Portal (App registrations)](https://portal.azure.com/).
2. Copia el **Application (client) ID** y crea un **Client Secret**.
3. Agrégalos en tu archivo `.env` (`OUTLOOK_CLIENT_ID` y `OUTLOOK_CLIENT_SECRET`).
4. Al ejecutar el programa por primera vez, el sistema solicitará autenticación vía URL para generar el token de sesión local `o365_token.txt`.

---

### 4. Levantar la Base de Datos (MySQL)

Asegúrate de tener Docker corriendo y ejecuta:

```bash
docker compose up -d
```

---

## Ejecución del Proyecto

Para correr el orquestador principal utilizando la nueva arquitectura de módulos:

```bash
python -m src.main
```

El programa ejecutará el siguiente flujo:
1. Inspecciona los clientes de correo configurados y disponibles (Gmail / Outlook).
2. Lee y filtra los correos de transacciones bancarias.
3. Descarta los mensajes previamente procesados analizando sus IDs en MySQL.
4. Parsea los datos de las nuevas transacciones y los inserta de forma estructurada en la base de datos.

---

## Arquitectura del Proyecto

```text
bot-fraude-finanzas/
├── docker-compose.yaml        # Servicios de infraestructura (MySQL)
├── requirements.txt
├── .env                       # Variables de entorno (Sensible)
│
├── notebooks/                 # Exploración de datos (EDA) y experimentos
│
└── src/                       # Código fuente modular
    ├── config.py              # Carga de variables de entorno y constantes
    ├── core/                  # Modelos de dominio y entidades
    │   └── models.py
    ├── ingestion/             # Clientes de API y Parsers de correo
    │   ├── gmail_client.py
    │   ├── outlook_client.py
    │   └── parsers/
    │       └── bac_parser.py
    ├── database/              # Capa de almacenamiento y consultas SQL
    │   └── storage.py
    ├── ml/                    # Feature engineering y modelos de detección
    ├── alerts/                # Módulo de notificaciones (Telegram, etc.)
    └── main.py                # Punto de entrada / Orquestador
```

---

## Archivos Sensibles y Seguridad

Los siguientes archivos contienen información privada o credenciales de acceso y **NUNCA** deben subirse a Git (ya se encuentran en `.gitignore`):

- `.env`
- `o365_token.txt`
- `data/credentials.json`
- `data/token.json`

---

## Próximas Mejoras

- [x] Soporte multi-proveedor (Gmail + Outlook)
- [x] Migración a base de datos relacional (MySQL)
- [ ] Módulo de **Feature Engineering** (patrones de consumo por horario, tarjeta y comercio)
- [ ] Entrenamiento e integración de **Modelo de Detección de Anomaly/Fraud** (Isolation Forest / Autoencoders)
- [ ] Bot de **Telegram** para alertas instantáneas y retroalimentación de usuario
- [ ] Dashboard de control financiero en **Metabase**