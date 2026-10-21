# Test fixtures

**Public (synthetic, published):** `arabic_table.pdf`, `hidden-ocr.pdf`, `pdf/`, `legacy/`.
They are generated from invented content by `tests/make_fixtures.py` and
`scripts/make_legacy_fixtures.py`. No user document is inside them.

**Private (never published):** `update34/` to `update42/`. They contain crops, OCR traces and
reference values taken from the owner's work documents. They are listed in `.gitignore`.
A clone of the public repository does not have them, so the tests that need them skip
themselves (`tests/conftest.py`). On the owner's PC set `DOCSTOMD_REQUIRE_PRIVATE=1` to make a
missing private fixture fail instead of skip.

Before adding any file here, ask: does it contain text, numbers, pixels or a name from a
document that is not ours to publish? If yes, it is private.
