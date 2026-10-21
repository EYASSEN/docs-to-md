# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cleanup18: Microsoft Store (MSIX) package. Settings move to local application data when the app
runs as an installed package, because the install folder is read-only."""
import importlib.util, sys
import pytest
import xml.etree.ElementTree as ET
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from foldertomd import runtime
from scripts import make_msix as M

NS = {'m': 'http://schemas.microsoft.com/appx/manifest/foundation/windows10',
      'uap': 'http://schemas.microsoft.com/appx/manifest/uap/windows10',
      'rescap': 'http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities'}


def test_store_version_has_four_parts_ending_in_zero():
    assert M.store_version('1.1.0') == '1.1.0.0'
    assert M.store_version('2.0') == '2.0.0.0'


def test_manifest_is_a_full_trust_desktop_app_with_the_given_identity():
    root = ET.fromstring(M.manifest('123Yassin.DocsToMD', 'CN=ABC & Co', 'Yassin Abd El Aal', '1.1.0').encode())
    identity = root.find('m:Identity', NS)
    assert identity.get('Name') == '123Yassin.DocsToMD' and identity.get('Publisher') == 'CN=ABC & Co'
    assert identity.get('Version') == '1.1.0.0' and identity.get('ProcessorArchitecture') == 'x64'
    app = root.find('m:Applications/m:Application', NS)
    assert app.get('Executable') == 'DocsToMD.exe' and app.get('EntryPoint') == 'Windows.FullTrustApplication'
    assert root.find('m:Capabilities/rescap:Capability', NS).get('Name') == 'runFullTrust'


@pytest.mark.skipif(importlib.util.find_spec('tkinter') is None, reason='tile images use the app icon from the Tk window module')
def test_layout_copies_the_app_without_its_data_folder_and_adds_manifest_and_tiles(tmp_path):
    app = tmp_path / 'DocsToMD'
    (app / 'vendor' / 'ocr-onnx').mkdir(parents=True)
    (app / 'DocsToMD.exe').write_bytes(b'exe')
    (app / 'data').mkdir()
    (app / 'data' / 'settings.json').write_text('{}')
    out = M.layout(app, tmp_path / 'layout', M.TEST_NAME, M.TEST_PUBLISHER, 'Yassin Abd El Aal', '1.1.0')
    assert (out / 'DocsToMD.exe').is_file() and (out / 'vendor' / 'ocr-onnx').is_dir()
    assert not (out / 'data').exists() and (out / 'AppxManifest.xml').is_file()
    sizes = {p.stem: Image.open(p).size for p in (out / 'Assets').glob('*.png')}
    assert sizes == {'StoreLogo': (50, 50), 'Square44x44Logo': (44, 44), 'Square150x150Logo': (150, 150),
                     'Wide310x150Logo': (310, 150)}


def test_packaged_app_keeps_settings_in_local_app_data(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, 'packaged', lambda: True)
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    assert runtime.data_dir() == tmp_path / 'DocsToMD' / 'data' and runtime.data_dir().is_dir()


def test_portable_app_keeps_settings_beside_the_program(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, 'packaged', lambda: False)
    monkeypatch.setattr(runtime, 'app_root', lambda: tmp_path)
    assert runtime.data_dir() == tmp_path / 'data'


def test_this_test_process_is_not_packaged():
    assert runtime.packaged() is False
