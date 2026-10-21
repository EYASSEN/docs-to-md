# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path
import io, json, os, uuid
from .render import url


def _progress_json(path, data):
    """Best-effort progress file: retry briefly, then skip. Never raises."""
    import time
    from .paths import atomic_json
    for attempt in range(6):
        try:
            atomic_json(path, data); return
        except OSError:
            time.sleep(0.05*(attempt+1))

class Context:
    def __init__(self, request):
        self.request = request
        self.source = Path(request['source'])
        self.work = Path(request['work'])
        self.settings = request['settings']
        self.warnings = []
        self.counts = {}
        self.assets = self.work/'assets'; self.assets.mkdir(exist_ok=True)
        self.out = (self.work/'result.md').open('w', encoding='utf-8', newline='\n')
        self.out.write('<!-- Source: '+request['relative'].replace('--', '—')+' -->\n\n')
        self.asset_index = 0
    def write(self, value): self.out.write(value)
    def warn(self, value):
        if value not in self.warnings: self.warnings.append(value)
    def stage(self, value, step=None, steps=None, unit=None):
        # step/steps (e.g. page 3 of 20) persist until the next counted stage, so
        # sub-stages such as OCR keep showing the current page in the GUI.
        self.current_stage=value
        if steps:
            self.progress = {'step': step, 'steps': steps, 'unit': unit or 'Step'}
            if unit in ('Page','Slide','Sheet','Frame'):
                self.progress['unit_completed']=max(0,(step or 0)-1)
        _progress_json(self.work/'stage.json', {'stage': value, **getattr(self, 'progress', {})})
    def complete_unit(self):
        """Publish completion after reading a page/frame, including early-return paths."""
        progress=getattr(self,'progress',{})
        unit=progress.get('unit')
        if unit not in ('Page','Slide','Sheet','Frame'): return
        progress['unit_completed']=min(progress['step'],progress['steps'])
        self.counts[{'Page':'pages','Slide':'slides','Sheet':'sheets','Frame':'frames'}[unit]+'_processed']=progress['unit_completed']
        _progress_json(self.work/'stage.json',{'stage':getattr(self,'current_stage','Reading'),**progress})
    def asset(self, data, suffix='.png'):
        self.asset_index += 1
        name = f'visual-{self.asset_index:05d}{suffix.lower()}'
        (self.assets/name).write_bytes(data)
        return url(self.request['asset_link']+'/'+name)
    def image(self, image, label, ocr=True):
        stream = io.BytesIO(); image.convert('RGB').save(stream, format='PNG')
        link = self.asset(stream.getvalue())
        self.write(f'![{label}]({link})\n\n')
        if ocr and self.settings['ocr'] != 'off':
            from .ocr import recognize
            result = recognize(image, self, label)
            if result: self.write(result+'\n\n')
        return link
    def close(self):
        self.out.flush(); os.fsync(self.out.fileno()); self.out.close()
