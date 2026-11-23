"""backend/tests/unread.py — a request's body that must never be read.

Both photo uploads refuse a file from its length alone (apps/control/api/uploads.py), so that a 50 MB one never fills
the server's memory. A test that only looks at the answer, or at the service, can't tell a route that refuses unread
from one that reads the whole body and then refuses. With this as the body, a route that reads a byte of it fails the
test:

    client.put(address, data=b"…", content_type="image/jpeg", **{"wsgi.input": NeverRead()})
"""


class NeverRead:
    # What Django reads a request's body through (django/core/handlers/wsgi.py, LimitedStream).
    def read(self, size: int = -1) -> bytes:
        raise AssertionError("The body was read.")

    def readline(self, size: int = -1) -> bytes:
        raise AssertionError("The body was read.")
