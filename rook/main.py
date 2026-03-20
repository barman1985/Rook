"""
rook.main — Entry point
========================
    python -m rook.main

Or:
    python main.py
"""

import logging
import sys

from rook.core.config import cfg
from rook.core.db import init_db
from rook.skills.loader import load_skills
from rook.transport.telegram import create_app

logger = logging.getLogger(__name__)


def setup_logging():
    """Configure logging."""
    level = getattr(logging, cfg.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main():
    """Start Rook."""
    setup_logging()

    # Validate config
    errors = cfg.validate()
    if errors:
        logger.error(f"Missing required config: {', '.join(errors)}")
        logger.error("Copy .env.example to .env and fill in your values.")
        sys.exit(1)

    logger.info("\u265C Rook starting...")
    logger.info(f"\n{cfg.summary()}")

    # Initialize database
    init_db()

    # Load skills
    skills = load_skills()
    logger.info(f"Skills: {', '.join(skills.keys())}")

    # Register notification handler (event bus listener)
    import rook.services.notifications  # noqa: F401 — registers @bus.on handlers

    # Start Telegram bot (scheduler starts inside its async context via post_init)
    app = create_app()

    async def _on_startup(application):
        from rook.services.scheduler import start_scheduler
        start_scheduler()

    app.post_init = _on_startup
    logger.info("Telegram bot ready — polling for messages")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
