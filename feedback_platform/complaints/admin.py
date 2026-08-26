from django.contrib import admin

from .models import Complaint, ComplaintNote

admin.site.register(Complaint)
admin.site.register(ComplaintNote)
