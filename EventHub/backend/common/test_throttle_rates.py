from django.test import SimpleTestCase

from .throttle_rates import parse_overrides

KNOWN = {'login', 'register', 'mfa_ip'}


class ThrottleRateOverrideTests(SimpleTestCase):
    def test_empty_means_no_change(self):
        self.assertEqual(parse_overrides('', KNOWN), {})
        self.assertEqual(parse_overrides(' , ', KNOWN), {})

    def test_pairs_are_parsed_and_trimmed(self):
        self.assertEqual(
            parse_overrides(' login = 60/min , mfa_ip=2/s,register=100/day', KNOWN),
            {'login': '60/min', 'mfa_ip': '2/s', 'register': '100/day'},
        )

    def test_every_problem_is_reported(self):
        with self.assertRaises(ValueError) as ctx:
            parse_overrides('logn=5/min,login=fast,register,login=1/min,mfa_ip=0/min', KNOWN)
        message = str(ctx.exception)
        self.assertIn('unknown scope "logn"', message)
        self.assertIn('"fast" for login', message)
        self.assertIn('"register" is not scope=rate', message)
        self.assertIn('"0/min" for mfa_ip', message)

    def test_duplicate_scope_is_refused(self):
        with self.assertRaisesMessage(ValueError, 'login is listed twice'):
            parse_overrides('login=5/min,login=6/min', KNOWN)
