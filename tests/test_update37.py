# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Acceptance reruns retain strict original-input checks without hashing owned output."""
import importlib.util,sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from foldertomd.paths import prepare_output,output_path
spec=importlib.util.spec_from_file_location('acceptance_update37',ROOT/'scripts/acceptance.py')
A=importlib.util.module_from_spec(spec);spec.loader.exec_module(A)

def corpus(tmp_path):
    root=tmp_path/'Tender اختبار';root.mkdir()
    (root/'original.txt').write_text('original',encoding='utf-8')
    (root/'genuine_md').mkdir();(root/'genuine_md/keep.txt').write_text('legitimate')
    return root

def test_first_and_repeated_run_hash_only_originals_and_keep_prior_outputs(tmp_path):
    root=corpus(tmp_path);initial=A.source_hashes(root)
    output,meta=prepare_output(root)
    report=meta/'conversion_report.md';report.write_text('first report')
    (output/'original.txt.md').write_text('converted')
    old_snapshot={p.relative_to(root).as_posix():A.digest(p) for p in root.rglob('*') if p.is_file()}
    report.write_text('second report');(meta/'manifest.json').write_text('{"status":"unchanged"}')
    assert any(A.digest(root/k)!=v for k,v in old_snapshot.items())
    assert A.source_hashes(root)==initial
    assert report.read_text()=='second report' and (output/'original.txt.md').exists()

@pytest.mark.parametrize('location',['genuine_md/keep.txt','Tender اختبار_md/manual.txt'])
def test_ordinary_and_unowned_same_name_md_folders_remain_protected_inputs(tmp_path,location):
    root=corpus(tmp_path);path=root/location;path.parent.mkdir(exist_ok=True);path.write_text('before')
    before=A.source_hashes(root);assert location in before
    path.write_text('after');changes=A.input_changes(before,A.source_hashes(root))
    assert changes=={'added':[],'removed':[],'changed':[location]}

def test_owned_output_does_not_hide_real_changed_removed_or_added_sources(tmp_path):
    root=corpus(tmp_path);(root/'remove.txt').write_text('remove')
    before=A.source_hashes(root);output,meta=prepare_output(root)
    (meta/'manifest.json').write_text('{}');(output/'new-output.md').write_text('output')
    (root/'original.txt').write_text('changed');(root/'remove.txt').unlink();(root/'added.txt').write_text('new input')
    after=A.source_hashes(root)
    assert before!=after
    assert A.input_changes(before,after)=={'added':['added.txt'],'removed':['remove.txt'],'changed':['original.txt']}

def test_unrelated_marked_folder_is_still_in_the_input_integrity_snapshot(tmp_path):
    root=corpus(tmp_path);nested=root/'other';nested.mkdir();output,meta=prepare_output(nested)
    file=output/'retained.md';file.write_text('before');before=A.source_hashes(root)
    rel=file.relative_to(root).as_posix();assert rel in before
    file.write_text('after');assert A.input_changes(before,A.source_hashes(root))['changed']==[rel]
