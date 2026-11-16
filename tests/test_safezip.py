"""Unit tests for subsync/assets/safezip.py: asset archives can't write
outside the asset folder.

    python -m unittest discover -s tests -v
"""

import importlib.util
import io
import os
import tempfile
import unittest
import zipfile

_path = os.path.join(os.path.dirname(__file__), '..', 'subsync', 'assets', 'safezip.py')
_spec = importlib.util.spec_from_file_location('safezip', _path)
safezip = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(safezip)


def archive(*names):
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as z:
        for name in names:
            z.writestr(zipfile.ZipInfo(name), b'x')
    data.seek(0)
    return zipfile.ZipFile(data)


class SafeZipTest(unittest.TestCase):
    def test_normal_archive_extracted(self):
        with tempfile.TemporaryDirectory() as tmp:
            safezip.extractAll(archive('eng.dict', 'models/jpn/model.bin'), tmp)
            self.assertTrue(os.path.isfile(os.path.join(tmp, 'models', 'jpn', 'model.bin')))

    def test_outside_paths_refused(self):
        for name in ('../evil.txt', 'models/../../evil.txt', '/etc/evil', '\\evil.txt',
                'C:/evil.txt', 'C:evil.txt', 'models\\..\\..\\evil.txt'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                dst = os.path.join(tmp, 'assets')
                os.makedirs(dst)
                with self.assertRaises(ValueError):
                    safezip.extractAll(archive('good.txt', name), dst)
                self.assertEqual(os.listdir(dst), [], 'nothing written')
                self.assertEqual(os.listdir(tmp), [ 'assets' ])

    def test_dots_inside_names_allowed(self):
        z = archive('model..v2.bin', 'a/..b/c')
        self.assertEqual(safezip.unsafeMembers(z, tempfile.gettempdir()), [])


if __name__ == '__main__':
    unittest.main()
