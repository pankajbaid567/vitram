"""Dedicated background worker: `python -m app.worker`.

Runs the reminder dispatcher outside the web process, so the API can scale (or restart) independently.
Start the API with ``RUN_SCHEDULER=false`` when a worker is deployed. Running several workers is safe: reminders
are claimed atomically (see ``services/channels/scheduler.claim_due``).
"""

import asyncio
import logging
import signal

from app.config import get_settings
from app.db import init_db
from app.observability import configure_logging
from app.services.catalogue import load_catalogues
from app.services.channels.scheduler import reminder_loop
from app.services.jobs import job_loop

log = logging.getLogger("vitram.worker")


async def run(interval: int = 60) -> None:
    settings = get_settings()
    settings.assert_production_ready()
    init_db()
    load_catalogues()
    tasks = [asyncio.create_task(reminder_loop(interval)), asyncio.create_task(job_loop())]
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    log.info("worker started (reminder loop every %ss, job loop)", interval)
    await stop.wait()
    log.info("worker stopping")
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


def main() -> None:
    configure_logging(get_settings().log_format)
    asyncio.run(run())


if __name__ == "__main__":
    main()
