"""Extension entrypoint: importing registers app panels and health checks."""

from app import ext
import handlers  # noqa: F401  Registers chat functions.
import handlers_accounts  # noqa: F401  Registers account management chat functions.
import handlers_admin  # noqa: F401  Registers Admin API structure chat functions (Part B).
import handlers_admin_write  # noqa: F401  Registers Admin API write/edit chat functions (Part D).
import handlers_alerts  # noqa: F401  Registers alert rule chat functions + scheduled evaluator.
import handlers_reports  # noqa: F401  Registers custom/canned report chat functions (Part A).
import panels  # noqa: F401  Registers panel routes.

app = ext
