"""apps/core/api/views.py — core's API views. Today only the health check:
GET /api/health/ → {"status": "ok", "version": "<the deployed git commit, or "dev">"}.

The outside uptime monitor calls it every minute, and the deploy smoke tests call it after each deploy
(03 §5.17, §12). An answer means the backend process is up and serving requests.
"""

from django.conf import settings
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    # Public, with no login (03 §5.10): the monitor and the smoke tests have no account.
    # No authentication at all, not just AllowAny: DRF's session check would read the session from the
    # database, and this check must stay cheap and never touch the database.
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        # During a deploy the old version keeps answering "ok" until the new one takes over, so "ok"
        # alone can't prove a deploy worked. The demo's smoke test waits until this version equals the
        # commit it just deployed (OPS-2). A commit id is no secret: the repo is public.
        return Response({"status": "ok", "version": settings.APP_VERSION})
