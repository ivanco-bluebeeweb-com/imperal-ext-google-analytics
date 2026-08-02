"""Extension entrypoint: importing registers app panels and health checks."""

from app import ext
import handlers  # noqa: F401  Registers chat functions.
import panels  # noqa: F401  Registers panel routes.

app = ext
