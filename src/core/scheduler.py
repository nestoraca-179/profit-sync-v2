"""Periodic scheduler for synchronization runs."""

from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

from src.config.config_loader import AppConfig
from src.core.engine import SynchronizationEngine

class SyncScheduler:
    """Wrap APScheduler for periodic sync execution."""

    def __init__(self, config: AppConfig, engine: SynchronizationEngine) -> None:
        self.config = config
        self.engine = engine
        self.scheduler = BackgroundScheduler(timezone=config.synchronizer.timezone)
        self.scheduler.add_job(
            self.engine.run_cycle,
            trigger="interval",
            minutes=config.synchronizer.run_interval_minutes,
            id="synchronization-cycle",
            replace_existing=True,
            max_instances=1,
        )

    def start(self) -> None:
        """Start the scheduler and trigger an immediate run."""
        self.scheduler.start()
        self.engine.run_cycle()

    def stop(self) -> None:
        """Stop the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)