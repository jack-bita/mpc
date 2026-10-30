"""backend/tests/concurrency.py — helpers for tests in which two transactions meet at the same moment.

Two managers press "confirm" on the same code; two pairings take the shop's first device number at once. To test
what the locks promise, a test runs the second one in a thread, and lets the first commit only once the second is
truly waiting for it: committing earlier would let the second run after, and the test would pass with no lock at
all. Django gives each thread its own database connection, so the thread is a second transaction, as a second
phone would be. Such tests need `@pytest.mark.django_db(transaction=True)`: each transaction must really commit,
or the other could never see it.
"""

import threading
import time
from collections.abc import Callable

from django.db import connection


def in_another_transaction(work: Callable[[], object]) -> tuple[threading.Thread, list[object]]:
    """Start `work` in a thread of its own, on its own database connection. The list gets what `work` returned, or
    the error it raised, once it ends; join the thread first. A new thread starts with no shop open (a context
    variable starts empty there), so `work` opens its own."""
    ended: list[object] = []

    def run() -> None:
        try:
            ended.append(work())
        except BaseException as error:  # handed back to the test, which checks it
            ended.append(error)
        finally:
            connection.close()  # this thread's connection, which nothing else will close

    thread = threading.Thread(target=run)
    thread.start()
    return thread, ended


def wait_until_someone_waits_for_me(seconds: float = 5) -> None:
    """Return once another connection waits for this one, the test's own: for a row it locked, or a row it inserted
    and hasn't committed. PostgreSQL's live list of locks (pg_locks) holds each lock a connection is still waiting
    for (`granted` false), and pg_blocking_pids says whom it waits for. pg_locks, not pg_stat_activity: inside one
    transaction, PostgreSQL shows pg_stat_activity as it was at the first look, like a photo, so a connection that
    started waiting after that first look would never show, and this would wait in vain."""
    deadline = time.monotonic() + seconds
    while True:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pg_locks WHERE NOT granted AND pg_backend_pid() = ANY(pg_blocking_pids(pid))"
            )
            (waiting,) = cursor.fetchone() or (0,)
        if waiting:
            return
        assert time.monotonic() < deadline, "the other transaction never waited for this one"
        time.sleep(0.02)
