from django.contrib import admin

from .models import PlatformAdmin, User

admin.site.register(PlatformAdmin)
admin.site.register(User)
