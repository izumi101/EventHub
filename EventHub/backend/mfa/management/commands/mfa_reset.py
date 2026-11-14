"""Remove every second factor of a locked-out user (docs/SECURITY_2FA.md).

    python manage.py mfa_reset <username> --yes-i-verified-the-user [--operator NAME] [--reason TEXT]

Only after the user's identity was verified out of band. The reset is logged
(logger `mfa`, level WARNING), the user is signed out everywhere and gets an
in-app notification and an email.
"""

import getpass

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from mfa.services import admin_reset

CONFIRM_FLAG = '--yes-i-verified-the-user'


class Command(BaseCommand):
    help = 'Reset two-factor authentication of one user (after verifying their identity).'

    def add_arguments(self, parser):
        parser.add_argument('username')
        parser.add_argument(
            CONFIRM_FLAG,
            dest='confirmed',
            action='store_true',
            help="Required: you verified the person's identity out of band.",
        )
        parser.add_argument('--operator', default='', help='Who performs the reset (for the audit log).')
        parser.add_argument('--reason', default='', help='Ticket number or reason (for the audit log).')

    def handle(self, *args, username, confirmed, operator, reason, **options):
        if not confirmed:
            raise CommandError(
                f"Refusing to reset 2FA without {CONFIRM_FLAG}. Verify the user's identity first "
                '(docs/SECURITY_2FA.md, "Resetting a locked-out user").'
            )
        user = User.objects.filter(username=username).first()
        if user is None:
            raise CommandError(f'No user named "{username}".')
        try:
            who = operator or getpass.getuser()
        except Exception:
            who = operator or 'unknown'
        label = f'{who} ({reason})' if reason else who
        removed = admin_reset(user, operator=label)
        self.stdout.write(
            self.style.SUCCESS(
                f'2FA reset for {user.username}: removed {removed["totp"]} authenticator app(s), '
                f'{removed["passkeys"]} passkey(s), {removed["email"]} email factor(s), '
                f'{removed["recovery_codes"]} recovery code(s); '
                'all sessions signed out.'
            )
        )
