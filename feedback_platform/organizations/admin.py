from django.contrib import admin

from .models import Branch, Organization, UserBranch

admin.site.register(Organization)
admin.site.register(Branch)
admin.site.register(UserBranch)
