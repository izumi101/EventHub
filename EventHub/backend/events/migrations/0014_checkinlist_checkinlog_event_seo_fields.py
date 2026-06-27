from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0013_event_refundable_refundrequest'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # SEO override fields on Event
        migrations.AddField(
            model_name='event',
            name='seo_title',
            field=models.CharField(blank=True, max_length=200, help_text='Custom <title> / og:title (falls back to event title)'),
        ),
        migrations.AddField(
            model_name='event',
            name='seo_description',
            field=models.CharField(blank=True, max_length=500, help_text='Custom meta description / og:description'),
        ),

        # CheckInList model
        migrations.CreateModel(
            name='CheckInList',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120)),
                ('description', models.CharField(blank=True, max_length=300)),
                ('color', models.CharField(default='#4f46e5', help_text='Hex color for UI badge', max_length=7)),
                ('is_default', models.BooleanField(default=False, help_text='The list used by the QR scanner when no list is selected')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='checkin_lists', to='events.event')),
            ],
            options={
                'verbose_name': 'check-in list',
                'verbose_name_plural': 'check-in lists',
                'ordering': ['created_at'],
            },
        ),

        # CheckInLog model
        migrations.CreateModel(
            name='CheckInLog',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(
                    choices=[('check_in', 'Checked in'), ('undo', 'Undo check-in')],
                    default='check_in',
                    max_length=10,
                )),
                ('note', models.CharField(blank=True, max_length=200)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('checkin_list', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='logs', to='events.checkinlist')),
                ('registration', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='checkin_logs', to='events.registration')),
                ('scanned_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='checkin_actions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'check-in log entry',
                'verbose_name_plural': 'check-in log entries',
                'ordering': ['-created_at'],
            },
        ),
    ]
