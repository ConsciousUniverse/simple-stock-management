"""The audit action for a phone freed from its account.

Unbinding a device is a decision about who may sign stock movements in a
person's name, so it belongs in the audit trail with the rest of them. Only the
choices list changes; the column and its length stay as they are.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("stock_manager", "0010_mobile_device_binding")]

    operations = [
        migrations.AlterField(
            model_name='auditevent',
            name='action',
            field=models.CharField(choices=[('login', 'Signed in'), ('login_failed', 'Sign-in refused'), ('logout', 'Signed out'), ('password_changed', 'Password changed'), ('document_created', 'Document created'), ('document_approved', 'Document approved'), ('document_rejected', 'Document rejected'), ('document_permit', 'Company voucher recorded'), ('item_created', 'Item created'), ('item_updated', 'Item changed'), ('item_deleted', 'Item deleted'), ('transfer_sent', 'Transfer requested'), ('transfer_completed', 'Transfer dispatched'), ('data_imported', 'Spreadsheet imported'), ('data_exported', 'Spreadsheet exported'), ('user_created', 'User created'), ('user_updated', 'User changed'), ('user_deactivated', 'User deactivated'), ('settings_changed', 'Settings changed'), ('release_published', 'App release published'), ('user_unlocked', 'Lockout cleared'), ('user_reset', 'Password reset on deploy'), ('phone_changed', 'Sign-in phone changed'), ('phone_requested', 'Phone change requested'), ('phone_request_decided', 'Phone change decided'), ('mobile_device_cleared', 'Phone unbound from the app')], max_length=32),
        ),
    ]
