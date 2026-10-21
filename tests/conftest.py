# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests that need PRIVATE fixtures skip themselves when those files are absent.

Private fixtures (tests/fixtures/update34 ... update42) are crops, traces and ground
truth taken from the owner's work documents. They are never published, so a clone of
the public repository does not have them. Set DOCSTOMD_REQUIRE_PRIVATE=1 to make a
missing private fixture a failure again (use it on the machine that owns them).
"""
import os
import re
import pytest

PRIVATE = re.compile(r'tests/fixtures/update(3[4-9]|4\d)/')
SKIPPED = []


def _missing_private_fixture(exc):
    if not (isinstance(exc, FileNotFoundError) or type(exc).__name__ == 'FileNotFoundError'):
        return None
    found = PRIVATE.search(str(exc).replace('\\', '/'))
    return found.group(0) if found else None


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if not report.failed or call.excinfo is None or os.environ.get('DOCSTOMD_REQUIRE_PRIVATE') == '1':
        return
    folder = _missing_private_fixture(call.excinfo.value)
    if folder:
        SKIPPED.append(item.nodeid)
        report.outcome = 'skipped'
        report.longrepr = (str(item.path), 0, f'Skipped: private fixture {folder} is not distributed with the public source')


def pytest_terminal_summary(terminalreporter):
    if SKIPPED:
        terminalreporter.write_line(
            f'{len(SKIPPED)} test(s) skipped because private fixtures are absent. '
            'On the owner PC they must all run: set DOCSTOMD_REQUIRE_PRIVATE=1 to enforce that.')
