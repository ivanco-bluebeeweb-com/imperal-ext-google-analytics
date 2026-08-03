"""Extension entrypoint: importing registers app panels and health checks."""

from app import ext
import handlers  # noqa: F401  Registers chat functions.
import handlers_accounts  # noqa: F401  Registers account management chat functions.
import handlers_alerts  # noqa: F401  Registers alert rule chat functions + scheduled evaluator.
import panels  # noqa: F401  Registers panel routes.

app = ext
