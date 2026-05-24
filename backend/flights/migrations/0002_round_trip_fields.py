from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("flights", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="flightsearch",
            name="return_date",
            field=models.DateField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="flightsearch",
            name="trip_type",
            field=models.CharField(db_index=True, default="one_way", max_length=16),
        ),
        migrations.AddField(
            model_name="flightoffer",
            name="return_date",
            field=models.DateField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="flightoffer",
            name="trip_type",
            field=models.CharField(db_index=True, default="one_way", max_length=16),
        ),
        migrations.RemoveIndex(
            model_name="flightsearch",
            name="flights_fli_origin_4fb505_idx",
        ),
        migrations.RemoveIndex(
            model_name="flightoffer",
            name="flights_fli_origin_8d165a_idx",
        ),
        migrations.AddIndex(
            model_name="flightsearch",
            index=models.Index(
                fields=["origin", "destination", "departure_date", "trip_type"],
                name="flights_fli_origin_d402f6_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="flightoffer",
            index=models.Index(
                fields=["origin", "destination", "departure_date", "trip_type", "price_amount"],
                name="flights_fli_origin_92dac1_idx",
            ),
        ),
    ]
