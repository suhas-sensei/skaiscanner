import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="FlightSearch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("origin", models.CharField(db_index=True, max_length=8)),
                ("destination", models.CharField(db_index=True, max_length=8)),
                ("departure_date", models.DateField(db_index=True)),
                ("source", models.CharField(default="yatra", max_length=32)),
                (
                    "status",
                    models.CharField(
                        choices=[("success", "Success"), ("no_results", "No results"), ("failed", "Failed")],
                        max_length=16,
                    ),
                ),
                ("offers_found", models.PositiveIntegerField(default=0)),
                ("error_message", models.TextField(blank=True)),
                ("search_url", models.URLField(blank=True, max_length=1000)),
                ("scraped_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                "ordering": ["-scraped_at"],
            },
        ),
        migrations.CreateModel(
            name="FlightOffer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source", models.CharField(db_index=True, default="yatra", max_length=32)),
                ("origin", models.CharField(db_index=True, max_length=8)),
                ("destination", models.CharField(db_index=True, max_length=8)),
                ("departure_date", models.DateField(db_index=True)),
                ("airline", models.CharField(blank=True, db_index=True, max_length=120)),
                ("flight_number", models.CharField(blank=True, max_length=40)),
                ("departure_time", models.CharField(blank=True, max_length=20)),
                ("arrival_time", models.CharField(blank=True, max_length=20)),
                ("duration", models.CharField(blank=True, max_length=80)),
                ("stops", models.CharField(blank=True, max_length=80)),
                ("price_amount", models.DecimalField(blank=True, db_index=True, decimal_places=2, max_digits=12, null=True)),
                ("currency", models.CharField(default="INR", max_length=8)),
                ("raw_text", models.TextField(blank=True)),
                ("raw_payload", models.JSONField(blank=True, default=dict)),
                ("scraped_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "search",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="offers",
                        to="flights.flightsearch",
                    ),
                ),
            ],
            options={
                "ordering": ["price_amount", "departure_time", "airline"],
            },
        ),
        migrations.AddIndex(
            model_name="flightsearch",
            index=models.Index(fields=["origin", "destination", "departure_date"], name="flights_fli_origin_4fb505_idx"),
        ),
        migrations.AddIndex(
            model_name="flightoffer",
            index=models.Index(
                fields=["origin", "destination", "departure_date", "price_amount"],
                name="flights_fli_origin_8d165a_idx",
            ),
        ),
    ]
