"""apps/shops/api/fields.py — form fields that name a shop's rows by their id, for any office route that takes one
(03 §5.10). Today SideField: the side a new row goes on, such as a device's home side (AUTH-5).
"""

from django.db.models import QuerySet
from rest_framework import serializers

from apps.shops.models import Side


class SideField(serializers.PrimaryKeyRelatedField[Side]):
    """A side, sent by its id: one of the visit's shop, and one the person acting sees. Any other id is "not found"
    (does_not_exist), another shop's side and a side hidden from the person alike, so the answer never tells that such
    a side exists (03 §5.4, PPL-5). Whether the person may act on the side is the route's own check, after this one."""

    def get_queryset(self) -> QuerySet[Side]:
        # Read on each visit, inside the visit's open shop, through the guard: named in the field's arguments
        # (`queryset=Side.objects.all()`), the sides would be asked for while the module loads, with no shop open,
        # and the guard would raise (CORE-2). Then kept to the sides the person sees, as the route's own reads are
        # (ShopViewSet.visible_sides, apps/core/api/base.py): None when a key of theirs covers every side.
        sides = Side.objects.all()
        view = self.context["view"]
        seen = view.visible_sides(view.request)
        return sides if seen is None else sides.filter(pk__in=seen)
