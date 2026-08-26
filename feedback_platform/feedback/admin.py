from django.contrib import admin

from .models import Category, Feedback, QRCode

admin.site.register(Category)
admin.site.register(QRCode)
admin.site.register(Feedback)
