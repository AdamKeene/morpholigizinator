# Make Celery app available so @shared_task picks it up on worker start.
from .celery import app as celery_app

__all__ = ("celery_app",)
