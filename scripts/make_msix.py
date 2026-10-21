# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build an MSIX package of the portable app for the Microsoft Store (Cleanup18).

Run after `scripts/package.py --revision N`, which completes dist/DocsToMD. The Store re-signs the
package after certification, so no certificate is needed for the Store upload.

    python scripts/make_msix.py                       # local test identity
    python scripts/make_msix.py --name 12345Yassin.DocsToMD --publisher "CN=XXXXXXXX-..." \
        --publisher-name "Yassin Abd El Aal"           # values from Partner Center > Product identity

Local test without a certificate (Windows Settings > System > For developers > Developer Mode on):
    Add-AppxPackage -Register build\\msix\\YassinAbdElAal.DocsToMD.Test\\AppxManifest.xml

makeappx.exe comes from an installed Windows SDK, or else from the Microsoft.Windows.SDK.BuildTools
NuGet package, downloaded once into build-cache; its SHA-256 is recorded in dependencies.lock.json on
first download and checked on every later build (same rule as scripts/acquire.py).
"""
from pathlib import Path
import argparse, glob, hashlib, json, os, shutil, subprocess, sys, urllib.request, zipfile
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SDK_TOOLS = '10.0.26100.1742'
TEST_NAME = 'YassinAbdElAal.DocsToMD.Test'
TEST_PUBLISHER = 'CN=DocsToMD Test'
EXCLUDE = {'data'}


def digest(path):
    with open(path, 'rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def store_version(version):
    """MSIX versions have four parts and the Store needs the last one to be 0: 1.1.0 -> 1.1.0.0."""
    parts = [int(p) for p in version.split('.')][:3]
    return '.'.join(str(p) for p in parts + [0] * (4 - len(parts)))


def manifest(name, publisher, publisher_name, version):
    return f'''<?xml version="1.0" encoding="utf-8"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
         xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
         xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
         IgnorableNamespaces="uap rescap">
  <Identity Name="{escape(name)}" Publisher="{escape(publisher)}" Version="{store_version(version)}" ProcessorArchitecture="x64"/>
  <Properties>
    <DisplayName>Docs to MD</DisplayName>
    <PublisherDisplayName>{escape(publisher_name)}</PublisherDisplayName>
    <Logo>Assets\\StoreLogo.png</Logo>
    <Description>Offline converter of document folders to Markdown, with Arabic and English OCR.</Description>
  </Properties>
  <Dependencies>
    <TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.19041.0" MaxVersionTested="10.0.26100.0"/>
  </Dependencies>
  <Resources>
    <Resource Language="en-us"/>
  </Resources>
  <Applications>
    <Application Id="DocsToMD" Executable="DocsToMD.exe" EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements DisplayName="Docs to MD" Description="Offline document folder to Markdown converter"
                          BackgroundColor="transparent" Square150x150Logo="Assets\\Square150x150Logo.png"
                          Square44x44Logo="Assets\\Square44x44Logo.png">
        <uap:DefaultTile Wide310x150Logo="Assets\\Wide310x150Logo.png"/>
      </uap:VisualElements>
    </Application>
  </Applications>
  <Capabilities>
    <rescap:Capability Name="runFullTrust"/>
  </Capabilities>
</Package>
'''


def assets(folder):
    """Tile and Store images drawn with the app's own icon (light theme accent)."""
    from PIL import Image
    from foldertomd.gui import _icon, THEMES
    accent = THEMES['light']['ACCENT']
    folder.mkdir(parents=True, exist_ok=True)
    for name, size in (('StoreLogo', 50), ('Square44x44Logo', 44), ('Square150x150Logo', 150)):
        _icon(size, accent).save(folder / f'{name}.png')
    wide = Image.new('RGBA', (310, 150), (0, 0, 0, 0))
    wide.paste(_icon(110, accent), (100, 20))
    wide.save(folder / 'Wide310x150Logo.png')


def layout(app, target, name, publisher, publisher_name, version):
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(app, target, ignore=lambda d, names: [n for n in names if Path(d) == app and n in EXCLUDE])
    (target / 'AppxManifest.xml').write_text(manifest(name, publisher, publisher_name, version), encoding='utf-8')
    assets(target / 'Assets')
    return target


def installed_makeappx():
    kits = os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)') + r'\Windows Kits\10\bin'
    found = sorted(glob.glob(kits + r'\10.*\x64\makeappx.exe'))
    return Path(found[-1]) if found else None


def nuget_makeappx(version=SDK_TOOLS):
    cache = ROOT / 'build-cache' / 'msix-tools'
    cache.mkdir(parents=True, exist_ok=True)
    package = cache / f'Microsoft.Windows.SDK.BuildTools.{version}.nupkg'
    if not package.exists():
        url = f'https://www.nuget.org/api/v2/package/Microsoft.Windows.SDK.BuildTools/{version}'
        print('Downloading', package.name, flush=True)
        part = package.with_suffix('.part')
        with urllib.request.urlopen(url, timeout=180) as r, part.open('wb') as w:
            shutil.copyfileobj(r, w)
        part.replace(package)
    lockpath = ROOT / 'dependencies.lock.json'
    lock = json.loads(lockpath.read_text(encoding='utf-8')) if lockpath.exists() else {}
    sha = digest(package)
    if package.name in lock and lock[package.name]['sha256'] != sha:
        raise RuntimeError('Checksum mismatch: ' + package.name)
    if package.name not in lock:
        lock[package.name] = {'url': f'https://www.nuget.org/api/v2/package/Microsoft.Windows.SDK.BuildTools/{version}',
                              'sha256': sha, 'bytes': package.stat().st_size}
        lockpath.write_text(json.dumps(lock, indent=2), encoding='utf-8')
    tools = cache / version
    if not tools.exists():
        with zipfile.ZipFile(package) as z:
            z.extractall(tools)
    found = sorted(tools.glob('bin/*/x64/makeappx.exe'))
    if not found:
        raise RuntimeError('makeappx.exe not found in ' + package.name)
    return found[-1]


def main():
    from foldertomd import __version__
    ap = argparse.ArgumentParser()
    ap.add_argument('--app', type=Path, default=ROOT / 'dist' / 'DocsToMD')
    ap.add_argument('--name', default=TEST_NAME)
    ap.add_argument('--publisher', default=TEST_PUBLISHER)
    ap.add_argument('--publisher-name', default='Yassin Abd El Aal')
    ap.add_argument('--out', type=Path, default=ROOT / 'release')
    args = ap.parse_args()
    app = args.app.resolve()
    if not (app / 'DocsToMD.exe').is_file() or not (app / 'vendor' / 'ocr-onnx').is_dir():
        raise SystemExit('Run scripts/package.py --revision N first: dist/DocsToMD is not complete.')
    # One layout folder per identity: a test package registered from its folder keeps that folder in use (Cleanup19).
    target = layout(app, ROOT / 'build' / 'msix' / args.name, args.name, args.publisher, args.publisher_name, __version__)
    tool = installed_makeappx() or nuget_makeappx()
    store = args.name != TEST_NAME
    out = args.out / f'DocsToMD-{__version__}-{"Store" if store else "test"}.msix'
    out.unlink(missing_ok=True)
    subprocess.run([str(tool), 'pack', '/d', str(target), '/p', str(out), '/o'], check=True)
    print(json.dumps({'msix': str(out), 'bytes': out.stat().st_size, 'sha256': digest(out), 'identity': args.name,
                      'publisher': args.publisher, 'version': store_version(__version__), 'makeappx': str(tool),
                      'layout': str(target)}, indent=2))


if __name__ == '__main__':
    main()
