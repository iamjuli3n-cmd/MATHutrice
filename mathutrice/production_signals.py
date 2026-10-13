"""Production signals: the service's errors and logs, sent to PostHog.

Three settings, read from each deployed environment:

- `POSTHOG_PROJECT_TOKEN`: the PostHog project's token (`phc_...`);
- `POSTHOG_HOST`: the ingestion host, `https://eu.i.posthog.com`;
- `POSTHOG_ENVIRONMENT`: `staging` or `production`.

All three, or none. With none (a laptop, a fresh clone), nothing is wired: the
service starts and answers exactly as before. With only some, the service
refuses to start and names the missing one (`ValueError: POSTHOG_ENVIRONMENT
missing`): otherwise one environment's errors could mix silently with
another's, or vanish. No value is ever committed.

`start()` is called from the app's lifespan, never at import: uvicorn applies
its own logging configuration after the import, and would remove the handler
set here. `shutdown()` flushes what is queued when the service stops, so that a
redeploy does not lose the last signals.
"""

from contextlib import contextmanager, nullcontext
import logging
import os

import posthog
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource

SETTINGS = ("POSTHOG_PROJECT_TOKEN", "POSTHOG_HOST", "POSTHOG_ENVIRONMENT")

# PostHog Logs' OTLP path, appended to POSTHOG_HOST.
LOGS_PATH = "/i/v1/logs"


class ProductionSignals:
    """What `start()` wired, and how to unwire it.

    Off (`client` is None) when the settings are unset: the request context,
    `report()` and `shutdown()` then do nothing.
    """

    def __init__(self, client=None, logger_provider=None, handler=None, loggers=()):
        self.client = client
        self._logger_provider = logger_provider
        self._handler = handler
        self._loggers = loggers

    def request_context(self, request):
        """PostHog context of one request, identified by the signed-in user.

        An exception leaving it is captured with that identity, then re-raised
        as it was: the answer does not change. To be opened inside
        `SessionMiddleware`, which loads the session.
        """
        if self.client is None:
            return nullcontext()
        return self._identified_context(request)

    @contextmanager
    def _identified_context(self, request):
        # Without client=, the context would capture through PostHog's global
        # client, never set up: no exception would arrive.
        with posthog.new_context(client=self.client):
            # No signed-in user, no identity: none is invented.
            email = (request.session.get("user") or {}).get("email")
            if email:
                posthog.identify_context(email)
            yield

    def report(self, exception):
        """Send to Error tracking an exception the code caught and answered for.

        Caught, it leaves no context, so nothing would capture it. It goes with
        the identity of the request's context, when there is one.
        """
        if self.client is None:
            return
        self.client.capture_exception(exception)

    def shutdown(self):
        """Flush what is queued, and unwire the log handler."""
        if self.client is None:
            return
        for logger in self._loggers:
            logger.removeHandler(self._handler)
        self._logger_provider.shutdown()
        self.client.shutdown()


# Set by start(), in the app's lifespan. Off until then, and off for good
# without the settings.
_signals = ProductionSignals()


def read_settings():
    """The three settings `(token, host, environment)`, or None with none set.

    Raises `ValueError`, naming the first missing setting, when only some are
    set.
    """
    values = {name: os.environ.get(name, "").strip() for name in SETTINGS}
    if not any(values.values()):
        return None
    for name in SETTINGS:
        if not values[name]:
            raise ValueError(f"{name} missing")
    return (
        values["POSTHOG_PROJECT_TOKEN"],
        values["POSTHOG_HOST"].rstrip("/"),
        values["POSTHOG_ENVIRONMENT"],
    )


def start(service_name):
    """Wire errors and logs to PostHog, when the three settings are set."""
    global _signals
    settings = read_settings()
    if settings is None:
        _signals = ProductionSignals()
        return _signals
    token, host, environment = settings

    client = posthog.Posthog(
        token,
        host=host,
        enable_exception_autocapture=True,
        super_properties={"environment": environment},
    )

    logger_provider = LoggerProvider(
        resource=Resource.create(
            {"service.name": service_name, "deployment.environment": environment}
        )
    )
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(
            OTLPLogExporter(
                endpoint=host + LOGS_PATH,
                headers={"Authorization": f"Bearer {token}"},
            )
        )
    )
    handler = LoggingHandler(logger_provider=logger_provider)

    # The root, at INFO, plus each logger the code uses that does not
    # propagate. Never one that propagates: its line would be sent twice.
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    loggers = [root] + [
        logger
        for name, logger in logging.root.manager.loggerDict.items()
        if name.startswith(service_name)
        and isinstance(logger, logging.Logger)
        and not logger.propagate
    ]
    for logger in loggers:
        logger.addHandler(handler)

    _signals = ProductionSignals(client, logger_provider, handler, loggers)
    return _signals


def request_context(request):
    """The current request's PostHog context; see ProductionSignals."""
    return _signals.request_context(request)


def report(exception):
    """Report a caught exception; see ProductionSignals.report."""
    _signals.report(exception)


def shutdown():
    """Flush and unwire; see ProductionSignals.shutdown."""
    _signals.shutdown()
