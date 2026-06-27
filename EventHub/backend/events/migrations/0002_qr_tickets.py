import uuid
from django.db import migrations, models

def gen_uuid(apps, schema_editor):
    Registration = apps.get_model('events', 'Registration')
    for row in Registration.objects.all():
        row.ticket_uuid = uuid.uuid4()
        row.save(update_fields=['ticket_uuid'])

class Migration(migrations.Migration):

    dependencies = [
        ('events', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='registration',
            name='is_checked_in',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='registration',
            name='ticket_uuid',
            field=models.UUIDField(default=uuid.uuid4, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='registration',
            name='checked_in_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(gen_uuid, reverse_code=migrations.RunPython.noop),
        migrations.AlterField(
            model_name='registration',
            name='ticket_uuid',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
