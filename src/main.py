"""Entry point for the synchronizer service."""

from __future__ import annotations

import signal
import sys
import threading
from typing import Optional

from src.config.config_loader import ConfigLoader
from src.core.engine import SynchronizationEngine
from src.core.scheduler import SyncScheduler
from src.logging.logger_setup import configure_logging, get_logger

logger = get_logger(__name__)

class Application:
    """Service wrapper that coordinates lifecycle management."""

    def __init__(self) -> None:
        self._scheduler: Optional[SyncScheduler] = None
        self._engine: Optional[SynchronizationEngine] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        """Start the synchronizer service."""
        config = ConfigLoader().load()
        configure_logging(config.logging)
        self._stop_event.clear()
        self._engine = SynchronizationEngine.from_config(config)
        self._scheduler = SyncScheduler(config=config, engine=self._engine)
        self._scheduler.start()
        logger.info("Servicio de sincronizacion iniciado", operation="service_start")

    def stop(self) -> None:
        """Stop the synchronizer service."""
        self._stop_event.set()
        if self._scheduler is not None:
            self._scheduler.stop()
        if self._engine is not None:
            self._engine.shutdown()
        logger.info("Servicio de sincronizacion detenido", operation="service_stop")

    def wait_forever(self) -> None:
        """Block until the application receives a stop signal."""
        while not self._stop_event.wait(timeout=1):
            continue

def _build_signal_handler(app: Application):
    def _handler(signum: int, _frame: object) -> None:
        logger.info(
            "Senal del sistema recibida",
            operation="signal_received",
            signal=signum,
        )
        app.stop()
        raise SystemExit(0)

    return _handler

def main() -> int:
    """Run the synchronizer service as a foreground daemon."""
    app = Application()
    signal_handler = _build_signal_handler(app)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    try:
        app.start()
        app.wait_forever()
        return 0
    except KeyboardInterrupt:
        app.stop()
        return 0
    except SystemExit:
        return 0
    except Exception:
        logger.exception("Fallo fatal al iniciar el servicio", operation="startup")
        app.stop()
        return 1

if __name__ == "__main__":
    sys.exit(main())