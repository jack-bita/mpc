"""apps/control/api/pagination.py — how the list of flags comes in pages (CTRL-4): as every long list does (CursorPage,
newest first), and with how many flags wait, which the page's tab counts: *Zinasubiri (5)*.
"""

from typing import Any

from rest_framework.response import Response

from apps.core.api.pagination import CursorPage


class FlagPage(CursorPage):
    # How many flags wait, under the same filters as the list. The view sets it before it answers a page: a page holds
    # at most 50 lines, so counting them would say 50 for 60.
    waiting = 0

    def get_paginated_response(self, data: Any) -> Response:
        answer = super().get_paginated_response(data)
        answer.data["waiting"] = self.waiting
        return answer

    def get_paginated_response_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        # The same in the API's description, so the app's types know it (ADR-0025).
        page = super().get_paginated_response_schema(schema)
        page["properties"]["waiting"] = {
            "type": "integer",
            "description": "How many flags wait, under the filters asked.",
        }
        page["required"] = [*page["required"], "waiting"]
        return page
