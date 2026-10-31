"""Request ids and logging: every log line and every response can be tied back to one request.

* ``X-Request-ID`` is accepted from a trusted proxy (if well-formed) or generated, stored in a context
  variable, stamped on each log record and returned on the response, including the 500 page.
* ``LOG_FORMAT=json`` switches to one JSON object per line for log collectors. The redaction filter always
  runs first, so neither format can carry a phone number, key or card number.
"""

import contextvars
import json
import logging
import re
import uuid

from app.security import RedactingFilter

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
_VALID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


def new_request_id(incoming: str | None = None) -> str:
    """Reuse a well-formed inbound id (so ids survive a proxy hop); never trust arbitrary text in logs."""
    return incoming if incoming and _VALID.match(incoming) else uuid.uuid4().hex


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {"ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"), "level": record.levelname, "logger": record.name,
                 "request_id": getattr(record, "request_id", "-"), "message": record.getMessage()}
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def configure_logging(fmt: str = "text") -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s [%(request_id)s]: %(message)s", force=True)
    for handler in logging.getLogger().handlers:
        handler.filters.clear()
        handler.addFilter(RedactingFilter())     # first: scrub the message …
        handler.addFilter(RequestIdFilter())     # … then attach the request id
        if fmt == "json":
            handler.setFormatter(JsonFormatter())
