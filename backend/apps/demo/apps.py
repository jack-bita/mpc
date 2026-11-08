"""apps/demo/apps.py — registers the demo app with Django, so `manage.py seed_demo` is found."""

from django.apps import AppConfig


class DemoConfig(AppConfig):
    name = "apps.demo"
