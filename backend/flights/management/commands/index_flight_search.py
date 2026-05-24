from django.core.management.base import BaseCommand, CommandError

from flights.models import FlightOffer
from flights.search import index_meilisearch_offers, index_opensearch_offers


class Command(BaseCommand):
    help = "Index flight offers into Meilisearch or OpenSearch."

    def add_arguments(self, parser):
        parser.add_argument(
            "--backend",
            choices=["meilisearch", "opensearch"],
            default="meilisearch",
        )
        parser.add_argument("--batch-size", type=int, default=1000)

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        if batch_size < 1:
            raise CommandError("--batch-size must be at least 1")

        backend = options["backend"]
        indexed = 0
        queryset = FlightOffer.objects.order_by("id")
        total = queryset.count()

        for start in range(0, total, batch_size):
            batch = list(queryset[start : start + batch_size])
            if backend == "opensearch":
                result = index_opensearch_offers(batch)
            else:
                result = index_meilisearch_offers(batch)
            indexed += result["indexed"]
            self.stdout.write(f"Indexed {indexed}/{total} offers into {backend}")

        self.stdout.write(self.style.SUCCESS(f"Indexed {indexed} offers into {backend}"))
