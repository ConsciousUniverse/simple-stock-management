from django.contrib import admin
from django.apps import AppConfig
from .models import Admin, GoodsReceipt, GoodsReceiptLine, Item

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


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    """Only the item card fields are editable here.

    Price, quantity and description move through the stock flow and the item
    manager, which keep the audit trail; this page shows them read-only so a
    save here can never blank a required field or change a balance.
    """

    list_display = ("sku", "description", "arabic_name", "sub_inventory", "unit", "internal_group")
    list_editable = ("arabic_name", "sub_inventory", "unit")
    search_fields = ("sku", "description", "arabic_name", "internal_group__code")
    list_filter = ("sub_inventory", "is_active")
    list_per_page = 100
    readonly_fields = ("sku", "description", "retail_price", "quantity", "internal_group", "is_active")
    fields = (
        "sku",
        "description",
        "arabic_name",
        "sub_inventory",
        "unit",
        "retail_price",
        "quantity",
        "internal_group",
        "is_active",
    )

    def has_add_permission(self, request):
        return False
