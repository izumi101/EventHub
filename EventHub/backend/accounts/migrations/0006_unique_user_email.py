"""Case-insensitive unique email for auth.User.

auth.User is Django's stock model, so the constraint is a partial unique
index on lower(email) (empty emails are allowed and not compared). Login and
password reset by email rely on one address mapping to one account; the
sign-up check alone can't stop two simultaneous registrations.
"""
from django.db import migrations

INDEX = 'auth_user_email_lower_uniq'


def refuse_duplicates(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "SELECT lower(email), count(*) FROM auth_user WHERE email <> '' "
            "GROUP BY lower(email) HAVING count(*) > 1 ORDER BY 2 DESC LIMIT 10"
        )
        duplicates = cursor.fetchall()
    if duplicates:
        listing = ', '.join(f'{email} ({count} accounts)' for email, count in duplicates)
        raise RuntimeError(
            'Cannot add the unique email index — these addresses belong to several accounts: '
            f'{listing}. Give each account its own email (e.g. in the Django admin), '
            'then run `manage.py migrate` again.'
        )


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_code_attempts'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(refuse_duplicates, migrations.RunPython.noop),
        migrations.RunSQL(
            f"CREATE UNIQUE INDEX {INDEX} ON auth_user (lower(email)) WHERE email <> ''",
            reverse_sql=f'DROP INDEX IF EXISTS {INDEX}',
        ),
    ]
