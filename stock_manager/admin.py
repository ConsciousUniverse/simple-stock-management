from django.contrib import admin
from django.apps import AppConfig
from .models import Admin

admin.site.site_header = "SSM Administration "
admin.site.site_title = "Simpler Stock Management"
admin.site.index_title = "Administration Dashboard"

class AdminAdmin(admin.ModelAdmin):
    exclude = ("edit_lock",)


admin.site.register(Admin, AdminAdmin)
