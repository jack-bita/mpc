"""apps/core/api/views.py — core's API views. Today only the health check: GET /api/health/ → {"status": "ok"}.

The outside uptime monitor calls it every minute, and the deploy smoke tests call it after each deploy
(03 §5.17, §12). An answer means the backend process is up and serving requests.
"""

from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

# REPO-6 probe, removed in the next commit: core must not import sales, so CI must turn red.
import apps.sales  # noqa: F401


class HealthView(APIView):
    # Public, with no login (03 §5.10): the monitor and the smoke tests have no account.
    # No authentication at all, not just AllowAny: DRF's session check would read the session from the
    # database, and this check must stay cheap and never touch the database.
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        return Response({"status": "ok"})
