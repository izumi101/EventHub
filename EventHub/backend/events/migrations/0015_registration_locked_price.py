from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0014_checkinlist_checkinlog_event_seo_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='registration',
            name='locked_price',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
    ]
