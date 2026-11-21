from django.contrib import admin
from django.apps import AppConfig
from .models import Admin, GoodsReceipt, GoodsReceiptLine

admin.site.site_header = "SSM Administration "
admin.site.site_title = "Simpler Stock Management"
admin.site.index_title = "Administration Dashboard"

class AdminAdmin(admin.ModelAdmin):
    exclude = ("edit_lock",)


admin.site.register(Admin, AdminAdmin)


class GoodsReceiptLineInline(admin.TabularInline):
    model = GoodsReceiptLine
    extra = 0
    readonly_fields = ("item", "sku", "description", "quantity")


@admin.register(GoodsReceipt)
class GoodsReceiptAdmin(admin.ModelAdmin):
    list_display = ("po_number", "supplier", "received_at", "received_by")
    list_filter = ("supplier",)
    search_fields = ("po_number", "supplier", "lines__sku")
    inlines = [GoodsReceiptLineInline]
