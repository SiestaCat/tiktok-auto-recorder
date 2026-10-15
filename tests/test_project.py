import importlib.util
import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'backend'))

from tiktokRecorder.profile import PROFILE_FILES, cloneProfile, createBrowserFactory
from tiktokRecorder.config import getProfileSeed
from tiktokRecorder.streams import addStream


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.profile = self.root / 'profile'
        self.profile.mkdir()
        for item in ('cookies.sqlite', 'cookies.sqlite-wal', 'storage.sqlite'):
            (self.profile / item).write_text(item)
        (self.profile / 'storage').mkdir()
        (self.profile / 'storage' / 'a').write_text('original')
        self.seed = getProfileSeed(self.profile)

    def tearDown(self):
        self.tmp.cleanup()

    def test_copies_only_four_items(self):
        (self.profile / 'irrelevant.secret').write_text('ignore')
        clone = cloneProfile(self.profile, 'Alice')
        self.assertTrue(clone.name.startswith('profile_alice_'))
        self.assertEqual(set(p.name for p in clone.iterdir()), set(PROFILE_FILES))
        self.assertEqual((clone / 'storage' / 'a').read_text(), 'original')

    def test_clones_are_independent(self):
        first = cloneProfile(self.profile, 'Alice')
        second = cloneProfile(self.profile, 'Alice')
        self.assertNotEqual(first, second)
        (first / 'cookies.sqlite').write_text('changed')
        self.assertEqual((second / 'cookies.sqlite').read_text(), 'cookies.sqlite')
        self.assertEqual((self.profile / 'cookies.sqlite').read_text(), 'cookies.sqlite')

    def test_missing_optional_file(self):
        (self.profile / 'cookies.sqlite-wal').unlink()
        clone = cloneProfile(self.profile, 'Bob')
        self.assertFalse((clone / 'cookies.sqlite-wal').exists())

    def test_fails_without_cookies(self):
        (self.profile / 'cookies.sqlite').unlink()
        with self.assertRaises(FileNotFoundError):
            cloneProfile(self.profile, 'Bob')

    def test_factory_is_headless_and_fresh(self):
        created = []
        cls = MagicMock()
        fac = createBrowserFactory(self.profile, 'Alice', createdCopies=created, playwrightClass=cls)
        fac()
        fac()
        self.assertEqual(len(created), 2)
        self.assertNotEqual(created[0], created[1])
        self.assertEqual(cls.call_count, 2)
        self.assertTrue(cls.call_args.kwargs['headless'])
        self.assertEqual(cls.call_args.kwargs['seed'], self.seed)


class StreamTests(unittest.TestCase):
    def test_favors_h264(self):
        streams = {}
        addStream({'VCodec': 'h265', 'url': 'https://video.example/a.flv'}, streams)
        addStream({'VCodec': 'h264', 'url': 'https://video.example/b.flv'}, streams)
        self.assertGreater(streams['https://video.example/b.flv'], streams['https://video.example/a.flv'])


class HostZipTests(unittest.TestCase):
    def test_exports_only_expected(self):
        spec = importlib.util.spec_from_file_location('hostLogin', ROOT / 'scripts' / 'hostLogin.py')
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'invisible_playwright': MagicMock()}):
            spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp) / 'profile'
            profile.mkdir()
            (profile / 'cookies.sqlite').write_text('cookies')
            (profile / 'junk.txt').write_text('junk')
            (profile / 'storage').mkdir()
            (profile / 'storage' / 'abc').write_text('session')
            getProfileSeed(profile)
            outfile = Path(tmp) / 'profile.zip'
            module.archiveProfile(profile, outfile)
            with zipfile.ZipFile(outfile) as archive:
                self.assertIn('profile/cookies.sqlite', archive.namelist())
                self.assertIn('profile/storage/abc', archive.namelist())
                self.assertIn('profile/.invisible-playwright-seed', archive.namelist())
                self.assertNotIn('profile/junk.txt', archive.namelist())


if __name__ == '__main__':
    unittest.main()
