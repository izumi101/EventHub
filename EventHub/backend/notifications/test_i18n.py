"""Notifications in the user's language (en / ru / kk): the catalogues are
complete and compiled, `notify()` writes each user's language, and the
preferences API stores the language and localises its labels."""

import ast
import gettext as gettext_module
import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import translation
from rest_framework.test import APITestCase

from events.models import Notification

from . import types
from .messages import build_message, format_datetime
from .models import NotificationPreference
from .service import notify
from .tests import WorldMixin, email_jobs

BACKEND = Path(settings.BASE_DIR)
LANGUAGES = ('ru', 'kk')
# Every file whose strings a notification shows.
PY_SOURCES = (
    BACKEND / 'notifications' / 'messages.py',
    BACKEND / 'notifications' / 'types.py',
    BACKEND / 'events' / 'services' / 'lifecycle.py',
)
TEMPLATES = tuple((BACKEND / 'notifications' / 'templates' / 'notifications' / 'email').glob('message.*'))
GETTEXT_FUNCTIONS = {'_', 'gettext', 'gettext_lazy', 'ngettext', 'ngettext_lazy', 'pgettext', 'pgettext_lazy'}
PLACEHOLDER = re.compile(r'%\((\w+)\)[sd]')


def source_msgids() -> set[tuple[str | None, str]]:
    """(context, msgid) of every translatable string in the sources."""
    found = set()
    for path in PY_SOURCES:
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if not (isinstance(node, ast.Call) and getattr(node.func, 'id', None) in GETTEXT_FUNCTIONS):
                continue
            args = [a.value for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
            if node.func.id.startswith('pgettext'):
                found.add((args[0], args[1]))
            elif args:
                found.add((None, args[0]))
    for path in TEMPLATES:
        text = path.read_text(encoding='utf-8')
        found |= {(None, m) for m in re.findall(r'{% translate "([^"]+)" %}', text)}
        found |= {(None, m) for m in re.findall(r"{% translate '([^']+)' %}", text)}
        for singular in re.findall(r'{% blocktranslate[^%]*%}(.*?){% (?:plural|endblocktranslate) %}', text):
            found.add((None, re.sub(r'{{ (\w+) }}', r'%(\1)s', singular)))
    return found


def parse_po(path: Path) -> dict[tuple[str | None, str], list[str]]:
    """{(context, msgid): [msgstr, …]} of a .po file (plural forms in order)."""
    entries = {}
    for block in path.read_text(encoding='utf-8').strip().split('\n\n'):
        fields, current = {}, None
        for line in block.splitlines():
            if line.startswith('#'):
                continue
            match = re.match(r'^(msgctxt|msgid_plural|msgid|msgstr(?:\[\d\])?) (".*")$', line)
            if match:
                current = match.group(1)
                fields[current] = ast.literal_eval(match.group(2))
            elif line.startswith('"') and current:
                fields[current] += ast.literal_eval(line)
        if fields.get('msgid'):
            forms = [v for k, v in sorted(fields.items()) if k.startswith('msgstr')]
            entries[(fields.get('msgctxt'), fields['msgid'])] = forms
    return entries


def po_path(lang: str, suffix: str = 'po') -> Path:
    return BACKEND / 'locale' / lang / 'LC_MESSAGES' / f'django.{suffix}'


class CatalogueTests(SimpleTestCase):
    def test_every_notification_string_is_translated_into_ru_and_kk(self):
        expected = source_msgids()
        self.assertGreater(len(expected), 150)
        for lang in LANGUAGES:
            catalogue = parse_po(po_path(lang))
            for key in sorted(expected, key=str):
                with self.subTest(lang=lang, msgid=key[1]):
                    self.assertIn(key, catalogue, f'{key} is missing from {lang}/django.po (makemessages)')
                    forms = catalogue[key]
                    self.assertTrue(forms and all(f.strip() for f in forms), f'{key} has no {lang} translation')

    def test_placeholders_match_the_source(self):
        for lang in LANGUAGES:
            for (_ctxt, msgid), forms in parse_po(po_path(lang)).items():
                for form in forms:
                    with self.subTest(lang=lang, msgid=msgid):
                        self.assertEqual(set(PLACEHOLDER.findall(form)), set(PLACEHOLDER.findall(msgid)))

    def test_compiled_mo_matches_the_po(self):
        """The committed .mo was compiled from the committed .po."""
        for lang in LANGUAGES:
            with po_path(lang, 'mo').open('rb') as fh:
                compiled = gettext_module.GNUTranslations(fh)
            for (ctxt, msgid), forms in parse_po(po_path(lang)).items():
                with self.subTest(lang=lang, msgid=msgid):
                    if len(forms) > 1:
                        self.assertEqual(compiled.ngettext(msgid, msgid + '-plural', 1), forms[0])
                    elif ctxt:
                        self.assertEqual(compiled.pgettext(ctxt, msgid), forms[0])
                    else:
                        self.assertEqual(compiled.gettext(msgid), forms[0])

    def test_kazakh_uses_cyrillic_kazakh_letters(self):
        text = ' '.join(f for forms in parse_po(po_path('kk')).values() for f in forms)
        self.assertTrue(set('әғқңөұүі') <= set(text))
        self.assertIn('EventHub', text)


@override_settings(NOTIFICATION_TIME_ZONE='Asia/Almaty')
class LanguageRenderingTests(WorldMixin, TestCase):
    def setUp(self):
        self.make_world()
        self.event.date = datetime(2026, 12, 5, 13, 0, tzinfo=UTC)
        self.event.save(update_fields=['date'])
        self.registration = self.confirmed(self.alice)

    def speak(self, user, language):
        NotificationPreference.objects.create(user=user, language=language)
        user.refresh_from_db()

    def notify_ticket(self, user):
        return notify(
            user,
            types.TICKET_PURCHASED,
            event=self.event,
            registration=self.registration,
            amount=Decimal('5000.00'),
            currency='kzt',
        )

    def test_dates_use_the_language_of_the_reader(self):
        cases = {
            'en': 'Sat, 5 Dec 2026, 18:00 (Asia/Almaty)',
            'ru': 'сб, 5 декабря 2026, 18:00 (Asia/Almaty)',
            'kk': '2026 ж. 5 желтоқсан, сб, 18:00 (Asia/Almaty)',
        }
        for lang, expected in cases.items():
            with self.subTest(lang=lang), translation.override(lang):
                self.assertEqual(format_datetime(self.event.date), expected)

    def test_a_russian_user_gets_a_russian_email_and_notification(self):
        self.speak(self.alice, 'ru')
        self.notify_ticket(self.alice)
        payload = email_jobs(self.alice).get().payload
        self.assertEqual(payload['subject'], 'Ваш билет на «Almaty Product Conference»')
        for part in (payload['body'], payload['html_body']):
            self.assertIn('Ваш билет подтверждён', part)
            self.assertIn('сб, 5 декабря 2026, 18:00', part)
            self.assertIn('Отписаться от этих писем', part)
            self.assertIn('Электронный билет', part)
        self.assertIn('<html lang="ru">', payload['html_body'])
        notification = Notification.objects.get(user=self.alice)
        self.assertEqual(notification.title, '🎫 Билет подтверждён: Almaty Product Conference')

    def test_a_kazakh_user_gets_a_kazakh_email_and_notification(self):
        self.speak(self.alice, 'kk')
        self.notify_ticket(self.alice)
        payload = email_jobs(self.alice).get().payload
        self.assertEqual(payload['subject'], '«Almaty Product Conference» іс-шарасына билетіңіз')
        for part in (payload['body'], payload['html_body']):
            self.assertIn('Билетіңіз расталды', part)
            self.assertIn('2026 ж. 5 желтоқсан, сб, 18:00', part)
            self.assertIn('Бұл хаттардан бас тарту', part)
        self.assertIn('<html lang="kk">', payload['html_body'])
        self.assertEqual(
            Notification.objects.get(user=self.alice).title, '🎫 Билет расталды: Almaty Product Conference'
        )

    def test_each_recipient_reads_their_own_language_and_the_server_stays_english(self):
        self.speak(self.alice, 'ru')
        self.confirmed(self.bob)
        notify(self.alice, types.EVENT_CANCELLED, event=self.event, refund='refunded')
        notify(self.bob, types.EVENT_CANCELLED, event=self.event, refund='refunded')
        self.assertEqual(email_jobs(self.alice).get().payload['subject'], 'Отменено: Almaty Product Conference')
        self.assertEqual(email_jobs(self.bob).get().payload['subject'], 'Cancelled: Almaty Product Conference')
        self.assertEqual(translation.get_language(), settings.LANGUAGE_CODE)

    def test_changes_are_shown_in_the_recipients_language(self):
        self.speak(self.alice, 'ru')
        old_date = self.event.date
        message_changes = [('Date', old_date, datetime(2026, 12, 6, 13, 0, tzinfo=UTC)), ('Online', False, True)]
        with translation.override('ru'):
            message = build_message(types.EVENT_UPDATED, self.alice, self.event, {'changes': message_changes})
        values = dict(message.details)
        self.assertEqual(
            values['Date'], 'вс, 6 декабря 2026, 18:00 (Asia/Almaty) (было: сб, 5 декабря 2026, 18:00 (Asia/Almaty))'
        )
        self.assertEqual(values['Online'], 'Да (было: Нет)')

    def test_an_event_update_reaches_a_kazakh_user_in_kazakh(self):
        from events.services import update_event

        self.speak(self.alice, 'kk')
        update_event(event=self.event, validated_data={'location': 'Almaty Arena'})
        notification = Notification.objects.get(user=self.alice, type=types.EVENT_UPDATED)
        self.assertEqual(notification.title, '📝 Іс-шара өзгертілді: Almaty Product Conference')
        self.assertIn('Өтетін орны', notification.body)


class LanguagePreferenceApiTests(WorldMixin, APITestCase):
    URL = '/api/v1/auth/profile/notifications/'

    def setUp(self):
        self.make_world()
        self.client.force_authenticate(self.alice)

    def test_the_language_is_saved_alone_or_with_email_changes(self):
        response = self.client.patch(self.URL, {'language': 'kk'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['language'], 'kk')
        self.assertEqual(NotificationPreference.objects.get(user=self.alice).language, 'kk')

        response = self.client.patch(
            self.URL, {'language': 'ru', 'email': {types.EVENT_REMINDER: False}}, format='json'
        )
        self.assertEqual(response.status_code, 200, response.data)
        preference = NotificationPreference.objects.get(user=self.alice)
        self.assertEqual((preference.language, preference.email_disabled), ('ru', [types.EVENT_REMINDER]))

        # Email changes alone keep the language.
        self.client.patch(self.URL, {'email': {types.EVENT_REMINDER: True}}, format='json')
        self.assertEqual(NotificationPreference.objects.get(user=self.alice).language, 'ru')
        # Empty: back to the default (English).
        self.client.patch(self.URL, {'language': ''}, format='json')
        self.assertEqual(NotificationPreference.objects.get(user=self.alice).language, '')

    def test_unknown_languages_are_rejected_with_an_english_error(self):
        for value in ('de', 'ru-RU', 'RU', None, 5):
            with self.subTest(value=value):
                response = self.client.patch(self.URL, {'language': value}, format='json', HTTP_ACCEPT_LANGUAGE='ru')
                self.assertEqual(response.status_code, 400)
                self.assertIn('language', response.data)
        self.assertIn('is not a valid choice', str(self.client.patch(self.URL, {'language': 'de'}, format='json').data))
        self.assertFalse(NotificationPreference.objects.exists())

    def test_labels_follow_accept_language(self):
        rows = {
            row['type']: row for row in self.client.get(self.URL, HTTP_ACCEPT_LANGUAGE='ru-RU,ru;q=0.9').data['types']
        }
        self.assertEqual(rows[types.EVENT_REMINDER]['label'], 'Напоминание о мероприятии')
        rows = {row['type']: row for row in self.client.get(self.URL, HTTP_ACCEPT_LANGUAGE='kk').data['types']}
        self.assertEqual(rows[types.EVENT_REMINDER]['label'], 'Іс-шара туралы еске салу')
        rows = {row['type']: row for row in self.client.get(self.URL, HTTP_ACCEPT_LANGUAGE='de').data['types']}
        self.assertEqual(rows[types.EVENT_REMINDER]['label'], 'Event reminder')
        # Only this response was localised.
        self.assertEqual(translation.get_language(), settings.LANGUAGE_CODE)
