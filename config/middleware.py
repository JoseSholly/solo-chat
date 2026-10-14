import logging
import time

from django.db import connection

logger = logging.getLogger(__name__)

SLOW_REQUEST_MS = 500


class ServerTimingMiddleware:
    """Adds a Server-Timing header to every response:

        Server-Timing: app;dur=12.3, db;dur=8.1;desc="3 queries"

    Browsers show it in DevTools → Network → (request) → Timing, so you can see
    how long the server spent and how much of that was the database. Requests
    slower than SLOW_REQUEST_MS are also logged.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        db = {"ms": 0.0, "queries": 0}

        def timed(execute, sql, params, many, context):
            start = time.perf_counter()
            try:
                return execute(sql, params, many, context)
            finally:
                db["ms"] += (time.perf_counter() - start) * 1000
                db["queries"] += 1

        start = time.perf_counter()
        with connection.execute_wrapper(timed):
            response = self.get_response(request)
        total = (time.perf_counter() - start) * 1000

        response["Server-Timing"] = (
            f'app;dur={total:.1f}, db;dur={db["ms"]:.1f};desc="{db["queries"]} queries"'
        )
        if total > SLOW_REQUEST_MS:
            logger.warning(
                "Slow request: %s %s took %.0f ms (db %.0f ms, %d queries)",
                request.method,
                request.path,
                total,
                db["ms"],
                db["queries"],
            )
        return response
