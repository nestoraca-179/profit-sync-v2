# SQL Server Synchronizer

Servicio de sincronizacion bidireccional entre una base local y una base remota de SQL Server utilizando Change Tracking.

## Requisitos

- Python 3.11+
- SQL Server con Change Tracking habilitado en ambas bases
- Driver ODBC 17 para SQL Server

## Instalacion

1. Crear un entorno virtual.
2. Instalar dependencias con `pip install -r requirements.txt`.
3. Copiar `.env.example` a `.env` y completar credenciales.
4. Ejecutar `scripts/setup_db.sql` en ambas bases.

## Ejecucion

- Desarrollo: `python -m src.main`
- Pruebas: `pytest`
- Health check: `http://localhost:8000/health`
- Metricas: `http://localhost:8000/metrics`

## Flujo de sincronizacion

1. Carga configuracion YAML y variables de entorno.
2. Valida conectividad local, remota y estado del circuit breaker.
3. Lee cambios con Change Tracking desde ambos servidores.
4. Resuelve conflictos por prioridad temporal.
5. Replica operaciones en lotes transaccionales.
6. Actualiza SyncControl por direccion.
7. Publica logs JSON y metricas Prometheus.

## Estructura de logs

Todos los logs se emiten en JSON con campos canonicos como `timestamp`, `level`, `logger`, `module`, `function`, `line`, `sync_id` y `error_category`.

## Troubleshooting

- Verificar que `SyncControl` y `PendingOperations` existan en ambas bases.
- Confirmar que el usuario SQL tenga permisos de lectura y escritura.
- Revisar el estado del circuit breaker en `/health`.
- Confirmar que el puerto 8000 este disponible para health y metricas.
