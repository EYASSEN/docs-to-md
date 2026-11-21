# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cleanup23: several light files are converted at the same time, each worker with a share of the
cores; a heavy file (a PDF of HEAVY_UNITS pages or more, with OCR on) still runs alone with the whole
PC. The output is the same as one file at a time."""
import json, re, sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from foldertomd import engine as E, runtime as R, pdf as P

GB = 1024 ** 3


def test_plan_uses_the_page_pool_budget_and_three_files_at_most(monkeypatch):
    monkeypatch.delenv('DOCSTOMD_PARALLEL_FILES', raising=False)
    assert E.parallel_plan(available_memory=32 * GB, budget=6) == (3, 2)
    assert E.parallel_plan(available_memory=32 * GB, budget=3) == (3, 1)
    assert E.parallel_plan(available_memory=32 * GB, budget=2) == (2, 1)
    assert E.parallel_plan(available_memory=32 * GB, budget=1) == (1, 1)


def test_plan_keeps_to_the_free_memory(monkeypatch):
    monkeypatch.delenv('DOCSTOMD_PARALLEL_FILES', raising=False)
    assert E.parallel_plan(available_memory=2 * GB, budget=6) == (1, 6)
    assert E.parallel_plan(available_memory=3.2 * GB, budget=6) == (2, 3)


def test_plan_can_be_forced_and_one_means_the_old_behaviour(monkeypatch):
    monkeypatch.setenv('DOCSTOMD_PARALLEL_FILES', '1')
    assert E.parallel_plan(available_memory=32 * GB, budget=6) == (1, 6)
    monkeypatch.setenv('DOCSTOMD_PARALLEL_FILES', 'x')
    assert E.parallel_plan(available_memory=32 * GB, budget=6) == (3, 2)


def test_budget_matches_the_page_pool(monkeypatch):
    monkeypatch.delenv('DOCSTOMD_THREADS', raising=False)
    assert E.thread_budget() == P._workers()


def test_heavy_files_are_long_pdfs_with_ocr_only():
    pages = {'a.pdf': 15, 'b.pdf': 14, 'c.tif': 40, 'd.docx': 90}
    on, off = {'ocr': 'auto'}, {'ocr': 'off'}
    assert E.is_heavy('a.pdf', pages, on) and not E.is_heavy('a.pdf', pages, off)
    assert not any(E.is_heavy(r, pages, on) for r in ('b.pdf', 'c.tif', 'd.docx'))


def test_worker_environment_carries_the_core_share(tmp_path, monkeypatch):
    monkeypatch.setenv('DOCSTOMD_THREADS', '5')            # never inherited from the parent
    whole = R.child_environment(tmp_path)
    assert 'DOCSTOMD_THREADS' not in whole and whole['OMP_THREAD_LIMIT'] == '2'
    share = R.child_environment(tmp_path, 1)
    # Cleanup23c: Tesseract keeps its two threads, so its reading is not changed by the share.
    assert share['DOCSTOMD_THREADS'] == '1' and share['OMP_THREAD_LIMIT'] == share['OMP_NUM_THREADS'] == '2'


def test_onnx_engine_keeps_its_own_thread_count():
    """Cleanup23c: limiting ONNX Runtime threads changed one OCR character on a real tender file, so the
    share only limits how many pages a worker reads at once."""
    source = (Path(__file__).resolve().parents[1] / 'foldertomd' / 'ocrengine.py').read_text(encoding='utf-8')
    assert 'thread_share' not in source


def test_page_pool_follows_the_share(monkeypatch):
    monkeypatch.setenv('DOCSTOMD_THREADS', '2')
    assert R.thread_share() == 2 and P._workers() == 2
    monkeypatch.setenv('DOCSTOMD_THREADS', '0')
    assert R.thread_share() is None
    monkeypatch.delenv('DOCSTOMD_THREADS')
    assert R.thread_share() is None


class Widget:
    def __init__(self): self.values = {'text': '', 'mode': 'determinate'}
    def configure(self, **kwargs): self.values.update(kwargs)
    def cget(self, key): return self.values.get(key, '')


def fake_app():
    from foldertomd.gui import App
    app = object.__new__(App)
    app.t = {'TEXT': 'black', 'SOFT': 'gray', 'MUTED': 'gray', 'TAGS': {}}
    for name in ('progress', 'file_progress', 'files_text', 'files_count', 'step_text', 'percent', 'status',
                 'tag', 'timing', 'completion_text', 'open_button', 'report_button'): setattr(app, name, Widget())
    app.pages = None; app.running = True
    app._bar = lambda bar, value=None, maximum=None: bar.configure(value=value, maximum=maximum)
    app._show_name = lambda name, colour: setattr(app, 'name', name)
    return app


def test_gui_background_events_move_only_the_overall_bar():
    app = fake_app()
    app.handle(dict(stage='Converting page', current='a.pdf', step=2, steps=4, unit='Page', unit_completed=1,
                    completed=0, discovered=3, pages_done=1, pages_total=10, running=2))
    shown = (app.name, app.step_text.cget('text'), app.percent.cget('text'))
    assert app.files_count.cget('text') == '0 of 3 files  •  2 at once'
    app.handle(dict(stage='Converting page', background=True, completed=1, discovered=3, pages_done=4,
                    pages_total=10, running=2))
    assert (app.name, app.step_text.cget('text'), app.percent.cget('text')) == shown
    assert app.progress.cget('value') == 4 and app.files_count.cget('text') == '1 of 3 files  •  2 at once'


def _folder(root):
    (root / 'sub').mkdir(parents=True)
    for i in range(7):
        (root / f'note_{i}.txt').write_text(f'Tender note {i}\n' * 40, encoding='utf-8')
        (root / 'sub' / f'items_{i}.csv').write_text('Item,Qty\n' + ''.join(f'{k},{k * 1.5}\n' for k in range(30)), encoding='utf-8')
    (root / 'odd.xyz').write_text('x')
    return root


def _markdown(out):
    clean = lambda t: re.sub(r'\.foldertomd-data-[0-9a-f]+', 'D', re.sub(r'assets/[0-9a-f]{32}', 'assets/X', t))
    return {p.relative_to(out).as_posix(): clean(p.read_text(encoding='utf-8'))
            for p in out.rglob('*.md') if '.foldertomd-data' not in p.as_posix()}


def test_parallel_job_gives_the_same_output_and_report(tmp_path, monkeypatch):
    results = {}
    for n in (1, 3):
        monkeypatch.setenv('DOCSTOMD_PARALLEL_FILES', str(n))
        source = _folder(tmp_path / f'run{n}')
        events = []
        result = E.run_job(source, {'ocr': 'off'}, notify=events.append)
        out = Path(result['output'])
        index = next(out.glob('.foldertomd-data-*')) / 'INDEX.md'
        report = Path(result['report']).read_text(encoding='utf-8')
        manifest = json.loads(Path(result['manifest']).read_text(encoding='utf-8'))
        assert result['parallel_files'] == n and f'Files converted in parallel: up to {n}' in report
        assert result['summary'].get('converted') == 14 and result['summary'].get('unsupported') == 1 and result['job_state'] == 'completed'
        assert result['files_processed'] == result['files_total'] == 15
        assert not [k for k, v in manifest['files'].items() if v['status'] in ('pending', 'committing')]
        done = [e['pages_done'] for e in events if 'pages_done' in e]
        assert done == sorted(done) and done[-1] == result['pages_total']
        if n == 1: assert not any(e.get('background') or e.get('running') for e in events)
        results[n] = (_markdown(out), index.read_text(encoding='utf-8'))
        again = E.run_job(source, {'ocr': 'off'})
        assert again['summary'].get('unchanged') == 14 and not again['summary'].get('converted')
    assert results[1] == results[3]


def test_cancel_marks_every_file_that_did_not_run(tmp_path, monkeypatch):
    import threading
    monkeypatch.setenv('DOCSTOMD_PARALLEL_FILES', '3')
    source = _folder(tmp_path / 'cancel')
    cancel = threading.Event()
    seen = []
    def notify(event):
        seen.append(event)
        if event.get('stage') == 'File finished': cancel.set()
    result = E.run_job(source, {'ocr': 'off'}, cancel=cancel, notify=notify)
    manifest = json.loads(Path(result['manifest']).read_text(encoding='utf-8'))
    statuses = [v['status'] for v in manifest['files'].values()]
    assert result['cancelled'] and 'pending' not in statuses and 'cancelled' in statuses


def test_cancel_counts_the_pages_read_by_every_running_file(tmp_path, monkeypatch):
    """Two files running at once and cancelled: both count the pages they read, neither counts as processed."""
    import threading
    from contextlib import nullcontext
    from types import SimpleNamespace
    monkeypatch.setenv('DOCSTOMD_PARALLEL_FILES', '3')
    source = tmp_path / 'input'; source.mkdir()
    for name in ('a.pdf', 'b.pdf'): (source / name).write_bytes(b'PDF test')
    cancel = threading.Event(); events = []
    monkeypatch.setattr(E, 'OutputLock', lambda meta: nullcontext())
    monkeypatch.setattr(E, 'short_work_root', lambda meta: tmp_path / 'work')
    (tmp_path / 'work').mkdir()
    monkeypatch.setattr(E, 'count_pages', lambda *a: {'a.pdf': 10, 'b.pdf': 30})
    monkeypatch.setattr(E, 'signature', lambda settings: ('signature', {}))
    started = threading.Barrier(2, timeout=10)
    class Worker:
        def __init__(self, *a, **kwargs):
            self.process = self; self.pid = 1; self.stopped = False
            Path(kwargs['cwd'], 'stage.json').write_text(json.dumps(dict(stage='Reading page', unit='Page', step=3, steps=10, unit_completed=2)))
            assert kwargs['env'].get('DOCSTOMD_THREADS')       # light files get a core share
            started.wait(); cancel.set()                         # both files are running before the cancel
        def poll(self): return 0 if self.stopped else None
        def stop(self): self.stopped = True
        def close(self): pass
        def wait(self, **k): return 0
    monkeypatch.setattr(E, 'JobProcess', Worker)
    monkeypatch.setattr(E.psutil, 'Process', lambda pid: SimpleNamespace(is_running=lambda: False, children=lambda **k: []))
    result = E.run_job(source, {'ocr': 'off'}, cancel, events.append)
    assert result['pages_done'] == 2 + 6 and result['pages_total'] == 40
    assert result['files_processed'] == 0 and result['summary']['cancelled'] == 2
    assert result['job_state'] == 'cancelled' and result['parallel_files'] == 3
