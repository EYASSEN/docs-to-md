# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
param([switch]$SkipAcquire, [switch]$SkipTests)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not [Environment]::Is64BitOperatingSystem) { throw 'Build on x64 Windows.' }
if (-not (Test-Path '.venv/Scripts/python.exe')) { python -m venv .venv; if ($LASTEXITCODE) { throw 'Python venv failed' } }
& ./.venv/Scripts/python.exe -m pip install -r requirements.lock.txt
if ($LASTEXITCODE) { throw 'Dependency installation failed' }
if (-not $SkipAcquire) { & ./.venv/Scripts/python.exe scripts/acquire.py; if ($LASTEXITCODE) { throw 'Dependency acquisition failed' } }
& ./.venv/Scripts/python.exe scripts/native_licenses.py
if ($LASTEXITCODE) { throw 'Native notices could not be verified' }
# All tests: core (Windows) and every update's regression tests (Update21)
if (-not $SkipTests) { & ./.venv/Scripts/python.exe -m pytest tests -q --junitxml=test-results/source-unit.xml; if ($LASTEXITCODE) { throw 'Source tests failed' } }
& ./.venv/Scripts/python.exe -m PyInstaller --noconfirm --clean FolderToMD.spec
if ($LASTEXITCODE) { throw 'Windows freeze failed' }
& ./.venv/Scripts/python.exe scripts/package.py
if ($LASTEXITCODE) { throw 'Packaging failed' }
Write-Host 'Portable package built. Run scripts/acceptance.py against the packaged executable before release.'
