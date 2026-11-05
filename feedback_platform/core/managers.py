from django.db import models


class TenantQuerySet(models.QuerySet):
    """QuerySet providing tenant-scoped helper methods."""

    def for_organization(self, organization):
        """
        Filters records to a specific organization.
        Accepts either an Organization instance or a UUID/string organization ID.
        Returns empty queryset if organization is falsy or None.
        """
        if not organization:
            return self.none()
        org_id = getattr(organization, "id", organization)
        return self.filter(organization_id=org_id)


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):
    """
    Custom manager wired to TenantQuerySet, allowing both Model.objects.for_organization(...)
    and Model.objects.filter(...).for_organization(...) query patterns.
    """
    pass
