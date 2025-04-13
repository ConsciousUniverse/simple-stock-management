import logging
from functools import reduce
from io import BytesIO
from openpyxl import Workbook
from rest_framework.response import Response
from rest_framework import status
from django.http import FileResponse
from .models import Item, ShopItem, User, Admin
from io import BytesIO
from openpyxl import Workbook, load_workbook
from functools import reduce
from django.db import transaction
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)


def get_related_field(obj, field_name):
    """
    Follow a chain of related fields (e.g. "shop_user__username") and return the resulting value.
    """
    try:
        return reduce(
            lambda o, attr: getattr(o, attr, None) if o else None,
            field_name.split("__"),
            obj,
        )
    except AttributeError:
        return ""


def create_excel_workbook(user):
    """
    Generate an Excel workbook containing two sheets.
      - 'Warehouse Stock' for Items.
      - 'Shop Stock' for ShopItems.
    The user must be in either the 'managers' or 'shop_users' group.
    """

    workbook = Workbook()

    # Create the 'Warehouse Stock' sheet
    item_sheet = workbook.active
    item_sheet.title = "Warehouse Stock"
    item_fields = ["sku", "description", "retail_price", "quantity"]
    item_header = ["SKU", "Description", "Retail Price", "Quantity"]
    item_sheet.append(item_header)
    for item in Item.objects.only(*item_fields):
        row_data = [getattr(item, field, "") for field in item_fields]
        item_sheet.append(row_data)

    # Create the 'Shop Stock' sheet
    shop_item_sheet = workbook.create_sheet(title="Shop Stock")
    shop_item_relation_fields = ["shop_user", "item"]
    shop_item_retrieved_fields = [
        "shop_user__username",
        "item__sku",
        "item__description",
        "item__retail_price",
        "quantity",
    ]
    shop_item_header = ["Shop User", "SKU", "Description", "Retail Price", "Quantity"]
    shop_item_sheet.append(shop_item_header)

    # If user is not a manager, limit the queryset
    is_manager = user.groups.filter(name="managers").exists()
    queryset = ShopItem.objects.select_related(*shop_item_relation_fields).only(
        *shop_item_retrieved_fields
    )
    if not is_manager:
        queryset = queryset.filter(shop_user__username=user.username)

    for shop_item in queryset:
        row_data = [
            get_related_field(shop_item, field) for field in shop_item_retrieved_fields
        ]
        shop_item_sheet.append(row_data)
    return workbook


def generate_excel_response(user):
    """
    Convert an Excel workbook into a Django FileResponse that triggers a download.
    """
    formatted_datetime = datetime.now(pytz.timezone("EUROPE/LONDON")).strftime(
        "%d%b%Y_%H%M%S%Z"
    )
    filename = f"SSM_DATA_{formatted_datetime}.xlsx"
    workbook = create_excel_workbook(user)
    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return FileResponse(
        output,
        as_attachment=True,
        filename=filename,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def field_changed(instance, field_name, new_value):
    """
    Check whether a field on an instance would change if updated with new_value.
    Uses the model field's to_python() to convert the new value.
    """
    try:
        field_obj = instance._meta.get_field(field_name)
        norm_new_value = field_obj.to_python(new_value)
    except Exception:
        norm_new_value = new_value  # fallback if field not found or conversion fails

    # Handle None vs. empty string
    old_value = getattr(instance, field_name)
    if old_value is None and norm_new_value in [None, ""]:
        return False
    return old_value != norm_new_value


def handle_excel_upload(request):
    """
    Process the uploaded Excel workbook(s) and return the response
    """
    # Check that a file is provided and that it's an .xlsx file.
    file_obj = request.FILES.get("file")
    if not file_obj or not file_obj.name.endswith(".xlsx"):
        return Response(
            {"detail": "Invalid file format. Please upload an .xlsx file."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    # Define field mappings for Item and ShopItem models.
    item_field_mapping = {
        "SKU": "sku",
        "Description": "description",
        "Retail Price": "retail_price",
        "Quantity": "quantity",
    }
    shop_item_field_mapping = {
        "Shop User": "shop_user__username",
        "SKU": "item__sku",
        "Description": "item__description",
        "Retail Price": "item__retail_price",
        "Quantity": "quantity",
    }

    # We'll track which records are present in the Excel data.
    excel_item_skus = set()  # For Item (sku is the primary key)
    excel_shopitem_keys = (
        set()
    )  # For ShopItem (tuple of (shop_user.username, item.sku))

    try:
        workbook = load_workbook(file_obj)
        with transaction.atomic():
            # Process "Warehouse Stock" sheet for Item model
            if "Warehouse Stock" in workbook.sheetnames:
                item_sheet = workbook["Warehouse Stock"]
                headers = [cell.value for cell in next(item_sheet.iter_rows(max_row=1))]
                for row in item_sheet.iter_rows(min_row=2, values_only=True):
                    # Build a data dictionary using the mapping
                    data = {
                        item_field_mapping[headers[i]]: value
                        for i, value in enumerate(row)
                        if headers[i] in item_field_mapping
                    }
                    sku = data.get("sku")
                    if not sku:
                        continue  # skip rows without an SKU
                    excel_item_skus.add(sku)
                    obj, created = Item.objects.get_or_create(sku=sku, defaults=data)
                    if not created:
                        updated = False
                        for key, value in data.items():
                            if field_changed(obj, key, value):
                                setattr(obj, key, value)
                                updated = True
                        if updated:
                            obj.save()

            # Process "Shop Stock" sheet for ShopItem model
            if "Shop Stock" in workbook.sheetnames:
                shop_item_sheet = workbook["Shop Stock"]
                headers = [
                    cell.value for cell in next(shop_item_sheet.iter_rows(max_row=1))
                ]
                for row in shop_item_sheet.iter_rows(min_row=2, values_only=True):
                    raw_data = {
                        shop_item_field_mapping[headers[i]]: value
                        for i, value in enumerate(row)
                        if headers[i] in shop_item_field_mapping
                    }
                    # Resolve related fields: fetch shop_user and item.
                    shop_username = raw_data.pop("shop_user__username", None)
                    item_sku = raw_data.pop("item__sku", None)
                    if not shop_username or not item_sku:
                        continue  # skip row if key data is missing

                    # Track the combination key
                    excel_shopitem_keys.add((shop_username, item_sku))

                    shop_user = User.objects.get(username=shop_username)
                    item = Item.objects.get(sku=item_sku)
                    obj, created = ShopItem.objects.get_or_create(
                        shop_user=shop_user, item=item
                    )

                    item_updated = False
                    shop_item_updated = False

                    for key, value in raw_data.items():
                        if key.startswith("item__"):
                            field = key.split("__", 1)[1]
                            if field_changed(item, field, value):
                                setattr(item, field, value)
                                item_updated = True
                        else:
                            if field_changed(obj, key, value):
                                setattr(obj, key, value)
                                shop_item_updated = True

                    if item_updated:
                        item.save()
                    if shop_item_updated:
                        obj.save()
            if Admin.is_allow_upload_deletions():
                # Delete Items that are in the DB but not in the Excel file.
                # (Excel file is considered the source of truth.)
                if "Warehouse Stock" in workbook.sheetnames:
                    deleted_items_count, _ = Item.objects.exclude(
                        sku__in=excel_item_skus
                    ).delete()
                    logger.debug(
                        "Deleted %s Item records not present in Excel",
                        deleted_items_count,
                    )

                # Delete ShopItem records that are in the DB but not in the Excel file.
                # Iterate over all ShopItem records and delete those that do not match any Excel key.
                if "Shop Stock" in workbook.sheetnames:
                    for shop_item in ShopItem.objects.select_related(
                        "shop_user", "item"
                    ):
                        key = (shop_item.shop_user.username, shop_item.item.sku)
                        if key not in excel_shopitem_keys:
                            shop_item.delete()

    except Exception as e:
        logger.debug("Error while importing Excel file: %s", str(e))
        return Response({"detail": str(e)}, status=400)

    return Response({"detail": "Data successfully imported."}, status=200)
