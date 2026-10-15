"""Run inside backend image with: python manage.py test recorder"""
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from .profileImport import allowedPath
from .utils import normalizeUsername, validateInterval


class ValidationTests(SimpleTestCase):
    def testUsernameNormalization(self):
        self.assertEqual(normalizeUsername(' @Te.St '), 'te.st')
        with self.assertRaises(ValidationError):
            normalizeUsername('../../etc/passwd')

    def testIntervalBounds(self):
        self.assertEqual(validateInterval('5'), 5)
        for value in (0, -1, 1441, 'x', True):
            with self.assertRaises(ValidationError):
                validateInterval(value)

    def testAllowedArchiveEntries(self):
        self.assertEqual(str(allowedPath('data/profile/storage/key')), 'storage/key')
        self.assertEqual(str(allowedPath('profile/cookies.sqlite')), 'cookies.sqlite')
        self.assertEqual(str(allowedPath('storage.sqlite')), 'storage.sqlite')
        for value in ('../etc/passwd', 'profile/storage/../../bad',
                      '/etc/passwd', 'profile/other.txt', 'profile/storage/evil\\x'):
            with self.assertRaises(ValidationError):
                allowedPath(value)
