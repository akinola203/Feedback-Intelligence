from django.core.management.base import BaseCommand

from feedback.models import DEFAULT_CATEGORIES, Category


class Command(BaseCommand):
    help = (
        "Seed the platform-defined default feedback categories "
        "(organization=None). Safe to run multiple times — existing "
        "categories are left untouched."
    )

    def handle(self, *args, **options):
        created = 0
        for name in DEFAULT_CATEGORIES:
            _, was_created = Category.objects.get_or_create(
                organization=None, name=name
            )
            if was_created:
                created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. {created} category(ies) created, "
                f"{len(DEFAULT_CATEGORIES) - created} already existed."
            )
        )
