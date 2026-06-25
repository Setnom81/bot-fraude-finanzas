# bot-fraude-finanzas

# Bot Fraude Finanzas

Bot para leer automáticamente notificaciones de transacciones del BAC desde Gmail utilizando la Gmail API.

Actualmente el proyecto:

- Se autentica mediante OAuth 2.0.
- Lee correos del BAC.
- Extrae información de la transacción.
- Guarda las transacciones en formato JSON.
- Evita procesar correos duplicados.

---

# Requisitos

- Python 3.11+
- Cuenta de Gmail
- Proyecto en Google Cloud

---

# Instalación

Clonar el proyecto

```bash
git clone https://github.com/Setnom81/bot-fraude-finanzas.git

cd bot-fraude-finanzas
```

Instalar dependencias

```bash
pip install -r requirements.txt
```

---

# Configuración de Gmail API

## 1. Crear un proyecto

Ir a:

https://console.cloud.google.com/

Crear un nuevo proyecto.

---

## 2. Habilitar Gmail API

Entrar a:

APIs y Servicios

↓

Biblioteca

↓

Buscar

```
Gmail API
```

↓

Habilitar.

---

## 3. Configurar OAuth

Ir a

```
APIs y Servicios

↓

Pantalla de consentimiento OAuth
```

Seleccionar

```
Externo
```

Agregar:

- Nombre de la aplicación
- Correo de soporte
- Correo del desarrollador

Guardar.

---

## 4. Agregar usuario de prueba

Ir a

```
Pantalla de consentimiento OAuth

↓

Público

↓

Usuarios de prueba
```

Agregar el correo Gmail que utilizará el bot.

---

## 5. Crear credenciales

Ir a

```
APIs y Servicios

↓

Credenciales

↓

Crear credenciales

↓

ID de cliente OAuth
```

Seleccionar

```
Aplicación de escritorio
```

Descargar el archivo JSON.

Renombrarlo a

```
credentials.json
```

Moverlo a

```
data/
```

La estructura deberá quedar así

```
data/
├── credentials.json
```

---

# Generar token.json

La primera vez es necesario autenticarse con Gmail.

Ejecutar

```bash
python auth.py
```

Se abrirá el navegador.

Seleccionar la cuenta Gmail autorizada.

Aceptar los permisos.

Al finalizar se generará automáticamente

```
data/token.json
```

Este archivo contiene el token OAuth y **NO debe subirse al repositorio**.

---

# Ejecutar el proyecto

Una vez generado el token

```bash
python main.py
```

El programa:

- Busca correos del BAC.
- Procesa únicamente correos nuevos.
- Extrae la información de la transacción.
- Guarda los resultados en

```
data/transactions.json
```

---

# Archivos sensibles

Los siguientes archivos están ignorados por Git.

```
data/token.json
data/credentials.json
data/transactions.json
.env
```

Nunca deben subirse al repositorio.

---

# Arquitectura

```
gmail_client.py
parser.py
storage.py
models.py
config.py
main.py
```

---

# Próximas mejoras

- SQLite
- Dashboard
- Reportes
- Soporte para otros bancos
- Clasificación automática de gastos
- Detección de fraude