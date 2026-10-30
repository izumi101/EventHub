from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0006_unique_user_email'),
    ]

    operations = [
        # NOT NULL can only be set once no row holds NULL.
        migrations.RunSQL(
            "UPDATE accounts_passwordresetcode SET reset_token = '' WHERE reset_token IS NULL",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AlterField(
            model_name='passwordresetcode',
            name='reset_token',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
    ]
