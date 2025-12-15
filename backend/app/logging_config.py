from __future__ import annotations

import logging
import logging.config
import sys

import structlog


def configure_logging(*, log_level: str = "INFO", json_logs: bool | None = None) -> None:
    """Configure structlog + stdlib logging for JSON (or console) output."""

    is_tty = sys.stdout.isatty()
    use_json = json_logs if json_logs is not None else not is_tty
    log_level = log_level.upper()

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        timestamper,
    ]
    renderer = (
        structlog.processors.JSONRenderer()
        if use_json
        else structlog.dev.ConsoleRenderer(colors=is_tty, exception_short=False)
    )

    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter_config = {
        "()": "structlog.stdlib.ProcessorFormatter",
        "processors": [
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            timestamper,
            renderer,
        ],
    }

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {"structlog": formatter_config},
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "formatter": "structlog",
                    "stream": "ext://sys.stdout",
                }
            },
            "loggers": {
                "": {"handlers": ["default"], "level": log_level, "propagate": False},
                "uvicorn": {"handlers": ["default"], "level": log_level, "propagate": False},
                "uvicorn.error": {"handlers": ["default"], "level": log_level, "propagate": False},
                "uvicorn.access": {"handlers": ["default"], "level": log_level, "propagate": False},
            },
        }
    )


__all__ = ["configure_logging"]
