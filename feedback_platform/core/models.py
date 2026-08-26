import uuid

from django.db import models


class BaseModel(models.Model):
    """
    Abstract base for every model in the platform.

    Gives every table a UUID primary key (per Phase 2 correction: UUID PKs
    used consistently platform-wide) and a created_at timestamp, so
    individual model definitions don't repeat this boilerplate.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
