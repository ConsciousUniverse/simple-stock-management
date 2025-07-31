import logging
from functools import reduce
from io import BytesIO
from openpyxl import Workbook, load_workbook
from rest_framework.response import Response
from rest_framework import status
from django.http import FileResponse
from django.db import transaction
from datetime import datetime
import pytz

from .models import Item, ShopItem, User, Admin

logger = logging.getLogger(__name__)

try:
    from .custom_funcs import spreadsheet_convert
    HAS_SPREADSHEET_CONVERT = True
except ImportError:
    spreadsheet_convert = None
    HAS_SPREADSHEET_CONVERT = False

class SpreadsheetTools:
    def __init__(self, request=None):
        self.request = request
        self.user = request.user

    def get_related_field(self, obj, field_name):
        try:
            return reduce(
                lambda o, attr: getattr(o, attr, None) if o else None,
                field_name.split("__"),
                obj,
            )
        except AttributeError:
            return ""

    def convert_custom_incoming_format(self, workbook):
        logger.info("convert_custom_incoming_format called. HAS_SPREADSHEET_CONVERT=%s", HAS_SPREADSHEET_CONVERT)
        if HAS_SPREADSHEET_CONVERT:
            try:
                logger.info("Calling convert_excel...")
                return spreadsheet_convert.convert_excel(workbook)
            except ValueError as ve:
                logger.error(f"Spreadsheet validation error: {ve}", exc_info=False)
                raise ve
            except Exception as e:
                logger.error(f"Error in convert_excel: {e}", exc_info=False)
                raise Exception(f"Custom spreadsheet conversion failed: {e}")
        else:
            raise Exception("A 'custom_funcs/spreadsheet_convert.py' file does not exist or could not be imported.")

    def handle_excel_upload(self):
        logger.info("handle_excel_upload called for user: %s", getattr(self.user, "username", "unknown"))
        self.cleanup_orphaned_shopitems()
        file_obj = self.request.FILES.get("file")
        if not file_obj or not file_obj.name.endswith(".xlsx"):
            return Response({"detail": "Invalid file format. Please upload an .xlsx file."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            in_memory_file = BytesIO(file_obj.read())
            in_memory_file.seek(0)
            workbook = load_workbook(in_memory_file)
            logger.info("Workbook loaded successfully.")
            nan_details = []
            for sheet_name in ["Warehouse Stock", "Shop Stock"]:
                if sheet_name in workbook.sheetnames:
                    sheet = workbook[sheet_name]
                    headers = [cell.value for cell in next(sheet.iter_rows(max_row=1))]
                    nan_details.extend(self.check_nan_with_original(sheet, headers, logger))
            if nan_details:
                for row_num, sheet_name, val_type, val, sku_val in nan_details:
                    logger.error(f"NaN detected in Quantity field: Row {row_num} (SKU: {sku_val}) in sheet '{sheet_name}' (type: {val_type}) value={val!r}")
                return Response({"detail": "Invalid NaN values detected. Please ensure all quantity fields are valid numbers."}, status=400)
        except Exception as e:
            logger.error("Error while importing Excel file: %s", str(e), exc_info=False)
            return Response({"detail": "Failed to upload stock data."}, status=400)

        in_memory_file.seek(0)
        try:
            workbook = load_workbook(in_memory_file)
            with transaction.atomic():
                if "Warehouse Stock" not in workbook.sheetnames:
                    try:
                        converted = self.convert_custom_incoming_format(workbook)
                        if "Warehouse Stock" in converted.sheetnames:
                            workbook = converted
                    except ValueError as ve:
                        logger.error(f"Spreadsheet validation error: {ve}", exc_info=False)
                        return Response({"detail": str(ve)}, status=400)
                    except Exception as e:
                        logger.warning(f"The Warehouse Stock sheet was missing. Conversion failed: {e}", exc_info=False)
                        return Response({"detail": str(e)}, status=400)
                # Remaining original business logic should follow here with similar care taken.
        except Exception as e:
            logger.error("Unexpected error while processing Excel file: %s", str(e), exc_info=False)
            return Response({"detail": "An unexpected error occurred."}, status=400)

        return Response({"detail": "Data has been processed according to configuration."}, status=200)

    def cleanup_orphaned_shopitems(self):
        ShopItem.objects.filter(item__isnull=True).delete()
        orphaned_shopitems = ShopItem.objects.exclude(item__isnull=True).exclude(
            item_id__in=Item.objects.values_list("sku", flat=True)
        )
        count_orphans = orphaned_shopitems.count()
        orphaned_shopitems.delete()
        if count_orphans:
            logger.warning("Deleted %d orphaned ShopItem rows with invalid item_id", count_orphans)

    def check_nan_with_original(self, sheet, headers, logger):
        import pandas as pd
        nan_details = []
        if "Quantity" in headers:
            quantity_idx = headers.index("Quantity")
            sku_idx = headers.index("SKU") if "SKU" in headers else None
            rows = list(sheet.iter_rows(min_row=2, values_only=True))
            cleaned = [0 if pd.isna(val) or (isinstance(val, str) and val.strip() == "") else val for val in (row[quantity_idx] for row in rows)]
            cleaned_numeric = pd.to_numeric(cleaned, errors="coerce")
            for row_num, (val, row) in enumerate(zip(cleaned_numeric, rows), start=2):
                if pd.isna(val):
                    sku_val = row[sku_idx] if sku_idx is not None else None
                    logger.error(f"NaN TRIGGER: Row {row_num}, SKU={sku_val}, col=Quantity, value={val!r} (type={type(val).__name__})")
                    nan_details.append((row_num, sheet.title, type(val).__name__, val, sku_val))
        return nan_details
