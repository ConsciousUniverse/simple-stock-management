"""Review, then apply, the internal codes the migration gives the catalogue.

The deploy's migration already assigns one internal code to every existing item
(1:1). This command exists so the result can be read *before* it is committed:
without ``--apply`` it prints the plan and changes nothing. It is also the
repair path if a row ever arrives without a code (a bulk load, for example).
"""

from django.core.management.base import BaseCommand
from django.db.models import Sum

from ...models import Item, ItemGroup


class Command(BaseCommand):
    help = "Show (or apply) the internal code for every Oracle item code."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Assign the codes. Without it the command only prints the plan.",
        )
        parser.add_argument(
            "--show-groups",
            action="store_true",
            help="Print every internal code with its Oracle codes and total.",
        )

    def handle(self, *args, **options):
        pending = Item.objects.filter(internal_group__isnull=True).order_by("sku")
        existing = [
            int(code)
            for code in ItemGroup.objects.values_list("code", flat=True)
            if str(code).isdigit()
        ]
        number = max(existing, default=0)

        self.stdout.write(
            f"items: {Item.objects.count()} · without an internal code: {pending.count()}"
        )
        for offset, item in enumerate(pending, start=1):
            self.stdout.write(f"  {number + offset:05d} ← {item.sku}  {item.description}")

        if pending and not options["apply"]:
            self.stdout.write(
                self.style.WARNING(
                    "Dry run: nothing was written. Run again with --apply to assign these codes."
                )
            )
        elif pending:
            assigned = 0
            for item in pending:
                group = ItemGroup.create_next()
                Item.objects.filter(pk=item.pk).update(internal_group=group)
                assigned += 1
            self.stdout.write(self.style.SUCCESS(f"Assigned {assigned} internal code(s)."))

        if options["show_groups"]:
            self.stdout.write("")
            self.stdout.write("Internal codes:")
            for group in ItemGroup.objects.prefetch_related("items").order_by("code"):
                members = sorted(group.items.all(), key=lambda item: item.sku)
                total = sum(item.quantity for item in members)
                self.stdout.write(
                    f"  {group.code}  total={total}  "
                    + "، ".join(item.sku for item in members)
                )
