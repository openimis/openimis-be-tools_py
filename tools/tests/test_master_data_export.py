import json
import os
import zipfile
from unittest.mock import patch

import pyzipper
from django.test import TestCase

from tools.apps import ToolsConfig
from tools.services import create_master_data_export

# WinZip AES marks an AES encrypted entry with this extra field (APPNOTE 7.2).
WZ_AES_EXTRA_ID = 0x9901


def extra_field_ids(info):
    ids, extra = [], info.extra
    while len(extra) >= 4:
        field_id, size = int.from_bytes(extra[0:2], "little"), int.from_bytes(extra[2:4], "little")
        ids.append(field_id)
        extra = extra[4 + size:]
    return ids


class MasterDataExportTest(TestCase):
    """The master data archive the policies app downloads (MasterData.txt, JSON)."""

    def _export(self, password):
        with patch.object(ToolsConfig, "master_data_password", password):
            archive = create_master_data_export(user=None)
        self.addCleanup(os.remove, archive.name)
        return archive.name

    def test_without_password_any_zip_reader_opens_it(self):
        # The app's online fetch reads the archive with java.util.zip, which cannot decrypt.
        path = self._export(None)

        with zipfile.ZipFile(path) as zf:
            self.assertEqual(zf.namelist(), ["MasterData.txt"])
            self.assertFalse(zf.getinfo("MasterData.txt").flag_bits & 0x1, "entry is encrypted")
            data = json.loads(zf.read("MasterData.txt"))
        self.assertIn("products", data)
        self.assertIn("ModuleConfiguration", data)

    def test_with_password_the_entry_is_aes_encrypted(self):
        # The app opens a password protected archive with zip4j, which reads WinZip AES,
        # the method it uses for its own uploads; legacy ZipCrypto is broken by design.
        path = self._export("s3cret-master-data")

        with pyzipper.AESZipFile(path) as zf:
            info = zf.getinfo("MasterData.txt")
            self.assertTrue(info.flag_bits & 0x1, "entry is not encrypted")
            self.assertIn(WZ_AES_EXTRA_ID, extra_field_ids(info), "entry is not WinZip AES")
            with self.assertRaises(RuntimeError):
                zf.read("MasterData.txt")
            zf.setpassword(b"s3cret-master-data")
            data = json.loads(zf.read("MasterData.txt"))
        self.assertIn("products", data)
