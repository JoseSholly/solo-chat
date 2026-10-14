import statistics
import time

from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = (
        "Measure the round trip from this server to the database. Run it where "
        "the app runs (a shell in the deployed service), not on your laptop."
    )

    def add_arguments(self, parser):
        parser.add_argument("-n", type=int, default=10, help="queries to time")

    def handle(self, *args, n, **options):
        settings = connection.settings_dict
        self.stdout.write(f"Database host: {settings.get('HOST') or 'local'}")

        start = time.perf_counter()
        connection.ensure_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        first = (time.perf_counter() - start) * 1000

        times = []
        with connection.cursor() as cursor:
            for _ in range(n):
                start = time.perf_counter()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                times.append((time.perf_counter() - start) * 1000)

        rtt = statistics.median(times)
        self.stdout.write(f"First query (incl. connecting): {first:.0f} ms")
        self.stdout.write(
            f"Round trip per query: median {rtt:.1f} ms, best {min(times):.1f} ms "
            f"({n} queries)"
        )
        if rtt < 20:
            verdict = "Close: the database is in or next to this server's region."
        elif rtt < 60:
            verdict = "Medium: a neighbouring region. Fine, but each query adds up."
        else:
            verdict = (
                "Far: likely another continent. Every query costs this much; "
                "moving the database next to the server is the biggest win."
            )
        self.stdout.write(verdict)
