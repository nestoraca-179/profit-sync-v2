# Instructivo de instalación y puesta en marcha

## 1. Verificar requisitos previos

Antes de instalar el sincronizador, confirmar:

- Python 3.11 o superior, si se ejecutará directamente en el servidor.
- SQL Server disponible en el servidor local y remoto.
- Acceso de red desde el servidor del sincronizador hacia ambas bases.
- Puertos SQL Server habilitados en firewall.
- Usuario SQL con permisos de lectura y escritura sobre las tablas sincronizadas.
- Permisos para crear y modificar `SyncControl` y `PendingOperations`.
- Driver `ODBC Driver 17 for SQL Server` instalado en el servidor de ejecución.

Las tablas configuradas actualmente se encuentran en `config/tables.yaml`.

## 2. Preparar el código del proyecto

Copiar el proyecto completo al servidor donde se ejecutará el sincronizador y abrir una consola en la raíz del proyecto:

```powershell
cd "C:\ruta\profit-sync-v2"
```

La raíz debe contener, entre otros archivos:

- `src/`
- `config/`
- `scripts/setup_db.sql`
- `requirements.txt`
- `Dockerfile`

## 3. Crear el entorno virtual

Para una instalación directa en Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Si PowerShell bloquea la activación para la sesión actual:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
```

Verificar la versión:

```powershell
python --version
```

Debe ser Python 3.11 o superior.

## 4. Instalar dependencias de Python y ODBC

Con el entorno virtual activo, instalar las dependencias:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

La instalación directa también requiere instalar previamente `ODBC Driver 17 for SQL Server` en Windows.

Para una ejecución con Docker, el `Dockerfile` utiliza `python:3.11-slim-bookworm` e instala `msodbcsql17` desde el repositorio oficial de Microsoft.

## 5. Configurar las variables de entorno

Crear el archivo `.env` en la raíz del proyecto. No usar credenciales reales en documentación ni subir este archivo al repositorio.

Ejemplo:

```env
LOCAL_DB_SERVER=servidor_local\INSTANCIA
LOCAL_DB_NAME=DEMOA
LOCAL_DB_USER=usuario_sync
LOCAL_DB_PASSWORD=contraseña_local

REMOTE_DB_SERVER=servidor_remoto\INSTANCIA
REMOTE_DB_NAME=DEMOA
REMOTE_DB_USER=usuario_sync
REMOTE_DB_PASSWORD=contraseña_remota

LOG_LEVEL=INFO
ENVIRONMENT=production
SYNC_INTERVAL_MINUTES=5
PROMETHEUS_PORT=8000
```

Los nombres deben coincidir exactamente con los usados en `config/config.yaml`.

## 6. Revisar la configuración YAML

Revisar `config/config.yaml` y confirmar:

- servidores, bases y credenciales mediante variables `${...}`;
- zona horaria;
- intervalo de sincronización;
- tamaño de lote;
- cantidad de reintentos;
- tiempos del circuit breaker;
- puerto de health check y métricas mediante `PROMETHEUS_PORT`.

Revisar `config/tables.yaml` y confirmar que:

- cada tabla exista en ambas bases;
- las PK sean correctas;
- las dependencias estén en el orden correcto;
- las tablas que no deban sincronizarse tengan `enabled: false`.

## 7. Preparar ambas bases de datos

Ejecutar `scripts/setup_db.sql` en la base local y en la base remota.

El script:

- habilita Change Tracking en la base;
- habilita Change Tracking en las tablas configuradas;
- crea `SyncControl`;
- crea `PendingOperations`;
- crea índices de soporte;
- inicializa el estado por dirección.

Ejecutarlo con SSMS, Azure Data Studio o `sqlcmd`, es decir, una herramienta que soporte `GO`.

Importante: el script contiene `ALTER DATABASE DEMOA`. Si la base tiene otro nombre, modificar ese valor antes de ejecutarlo.

Antes de ejecutarlo, verificar también que las tablas existan y que el usuario tenga permisos suficientes.

## 8. Ejecutar el sincronizador

Desde la raíz del proyecto y con el entorno virtual activo:

```powershell
python -m src.main
```

El proceso:

1. carga `.env` y los YAML;
2. conecta a ambas bases;
3. inicia el servidor de health check y métricas;
4. ejecuta un ciclo inicial inmediatamente;
5. continúa ejecutando ciclos según `SYNC_INTERVAL_MINUTES`.

Para detenerlo de forma controlada, presionar `Ctrl+C`.

### Alternativa con Docker

Construir la imagen:

```powershell
docker build -t profit-sync-v2 .
```

Ejecutar el contenedor pasando el archivo de entorno:

```powershell
docker run --rm --name profit-sync-v2 --env-file .env -p 8000:8000 profit-sync-v2
```

No incluir credenciales dentro de la imagen.

## 9. Validar el servicio y revisar logs

Health check:

```text
http://localhost:8000/health
```

Métricas Prometheus:

```text
http://localhost:8000/metrics
```

El health check debe mostrar, como mínimo:

- conexión local correcta;
- conexión remota correcta;
- último ciclo completado o su error;
- estado del circuit breaker.

Revisar el archivo:

```text
logs/synchronizer.log
```

Confirmar mensajes de inicio y ciclos completados. Ante un error, revisar también `SyncStatus`, `LastError` y `PendingOperations`.

## 10. Ejecutar pruebas y dejar el servicio operativo

Ejecutar las pruebas unitarias:

```powershell
python -m pytest tests/unit -q
```

Las pruebas de integración deben ejecutarse únicamente contra bases de prueba. Activarlas mediante:

```powershell
$env:RUN_INTEGRATION_TESTS = "1"
python -m pytest tests/integration -q
```

Antes de dejar el servicio en producción, comprobar:

- que un cambio controlado en una tabla se replique correctamente;
- que el cambio aparezca en la dirección esperada;
- que `SyncControl.LastSyncVersion` avance;
- que los errores se registren en `PendingOperations` sin perder el ciclo;
- que el servicio sobreviva a una interrupción temporal de red o SQL Server;
- que el puerto `8000` esté permitido si el health check se consultará remotamente.

El servicio actual procesa cambios en ambas direcciones: `LOCAL_TO_REMOTE` y `REMOTE_TO_LOCAL`. Si se requiere únicamente sincronización local hacia remota, debe ajustarse la lógica del motor antes de ponerlo en producción.

## Parámetros operativos actuales

- Intervalo: 5 minutos.
- Tamaño de lote: 500 registros.
- Intentos máximos por operación: 3.
- Espera mínima entre reintentos: 60 segundos.
- Multiplicador de backoff: 2.
- Apertura del circuit breaker: 5 ciclos fallidos consecutivos.
- Tiempo en estado `OPEN`: 300 segundos.
- Prueba en `HALF_OPEN`: una solicitud de recuperación.
- Timeout de conexión local: 30 segundos.
- Timeout de conexión remota: 60 segundos.
- Puerto predeterminado de health check y métricas: 8000.
