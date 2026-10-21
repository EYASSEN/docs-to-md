# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
import base64, io, json, os, queue, threading, time, webbrowser
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, font as tkfont
from PIL import Image, ImageDraw
from . import __version__
from .engine import run_job,DEFAULTS,HOMEPAGE
from .paths import output_path,atomic_json
from .progress import format_pages,format_pages_progress
from .runtime import data_dir,app_root

APP_NAME='Docs to MD'; APP_VERSION='v'+__version__; AUTHOR='Yassin Labs'   # brand (Cleanup19); the copyright stays personal
COPYRIGHT='Copyright (C) 2026 Yassin Abd El Aal'
WARRANTY=('This program comes with ABSOLUTELY NO WARRANTY. It is free software: you can redistribute it and/or '
          'modify it under the terms of the GNU Affero General Public License, version 3 or (at your option) any later version.')
# Two themes from the Stitch designs; the window uses the light one only, in dark blue (UI3). Every colour used by the window comes from here.
THEMES={
 'dark':dict(name='Dark',dark=True,
    WINDOW='#18181b',HEADER='#18181b',HEADER_LINE='#27272a',PANEL='#1c1d22',PANEL_LINE='#27272a',
    OPTS_HEAD='#202126',OPTS='#1b1c20',OPTS_LINE='#27272a',INSET='#1f2024',INSET_OFF='#1a1a1d',
    RAISED='#27272a',HOVER='#333338',PRESSED='#1f2024',BTN_LINE='#3f3f46',BTN_LINE_HOVER='#52525b',
    LINE='#27272a',TEXT='#f4f4f5',SOFT='#d4d4d8',MUTED='#a1a1aa',FAINT='#71717a',
    ACCENT='#2563eb',ACCENT_HOVER='#3b82f6',ACCENT_PRESSED='#1d4ed8',ACCENT_OFF='#1e3a8a',ACCENT_OFF_TEXT='#93a5c9',
    BAR='#3b82f6',BAR_FILE='#60a5fa',TRACK='#27272a',LINK='#60a5fa',CHECK_OFF='#09090b',CHECK_LINE='#3f3f46',
    CLOCK='#202126',CLOCK_LINE='#27272a',RUN='#3b82f6',DONE='#34d399',FAIL='#f87171',WAIT='#fbbf24',
    BADGES={'ok':('#1b302d','#184c3e','#34d399'),'warn':('#362d1f','#5d441b','#fbbf24'),'bad':('#352226','#5b292c','#f87171'),
            'muted':('#27272a','#3f3f46','#a1a1aa'),'brand':('#27272a','#3f3f46','#a1a1aa')},
    TAGS={'pdf':'#f87171','word':'#60a5fa','excel':'#34d399','slides':'#fb923c'}),
 'light':dict(name='Light',dark=False,
    # Cleanup19: calm stone and slate. Soft grey surfaces instead of pure white, charcoal text instead of black,
    # one muted slate accent; easy on the eyes in long sessions. No greens (UI3).
    WINDOW='#eef1f0',HEADER='#e4e9e7',HEADER_LINE='#cdd5d2',PANEL='#f3f5f4',PANEL_LINE='#d0d8d5',
    OPTS_HEAD='#e7ecea',OPTS='#f3f5f4',OPTS_LINE='#bcc7c3',INSET='#f6f8f7',INSET_OFF='#e9edeb',
    RAISED='#f7f9f8',HOVER='#e3e9e7',PRESSED='#d8e0dd',BTN_LINE='#c3ccc9',BTN_LINE_HOVER='#8597a0',
    LINE='#d9e0dd',TEXT='#22292b',SOFT='#3b4548',MUTED='#55615f',FAINT='#8b9693',
    ACCENT='#4a5f6b',ACCENT_HOVER='#5a717e',ACCENT_PRESSED='#3b4d57',ACCENT_OFF='#b4c0c6',ACCENT_OFF_TEXT='#ffffff',
    BAR='#4a5f6b',BAR_FILE='#7b909b',TRACK='#d7dedb',LINK='#3e6275',CHECK_OFF='#f7f9f8',CHECK_LINE='#b9c3c0',
    CLOCK='#e7ecea',CLOCK_LINE='#bcc7c3',RUN='#56707e',DONE='#4a5f6b',FAIL='#b4233c',WAIT='#b26b12',
    BADGES={'ok':('#e4ebea','#bccac7','#3e5560'),'warn':('#f7f0de','#e3cf9d','#8a5a0f'),'bad':('#f6e4e6','#e2b7bd','#9e2236'),
            'muted':('#e7ecea','#d3dbd8','#55615f'),'brand':('#e4ebea','#bccac7','#3e5560')},
    TAGS={'pdf':'#b4233c','word':'#3e6275','excel':'#5f6f6b','slides':'#b5622a'}),
}
FILE_KINDS={'.pdf':'pdf','.doc':'word','.docx':'word','.docm':'word','.xls':'excel','.xlsx':'excel','.xlsm':'excel',
            '.ppt':'slides','.pptx':'slides','.pptm':'slides'}
LANGS={'ara+eng':'Arabic + English','ara':'Arabic','eng':'English'}
QUALITY={'quick':'Quick','standard':'Standard','high':'High accuracy'}
QUALITY_HINT={'quick':'Fastest. May miss a rare isolated line.','standard':'Balanced speed and accuracy.',
              'high':'Most accurate OCR. About 2.5× slower.'}
SPIN='◐◓◑◒'

def _pick(root,names,fallback):
    have=set(tkfont.families(root))
    return next((n for n in names if n in have),fallback)

def _shorten(value,limit=58):
    value=str(value)
    return value if len(value)<=limit else '…'+value[-(limit-1):]

def _middle(text,font,width):
    """Shorten text in the middle (start…end) so it fits width pixels in font."""
    text=str(text)
    if width<=0 or font.measure(text)<=width: return text
    lo,hi=1,len(text)
    while lo<hi:                       # longest middle cut that still fits
        keep=(lo+hi+1)//2; head=keep//2; tail=keep-head
        if font.measure(text[:head]+'…'+text[len(text)-tail:])<=width: lo=keep
        else: hi=keep-1
    head=lo//2; tail=lo-head
    return text[:head]+'…'+text[len(text)-tail:]

class Tip:
    """Small hover tooltip showing a label's full text."""
    def __init__(self,widget,text_fn,t):
        self.widget=widget; self.text_fn=text_fn; self.t=t; self.win=None
        widget.bind('<Enter>',self.show,add='+'); widget.bind('<Leave>',self.hide,add='+')
    def show(self,_=None):
        text=self.text_fn()
        if not text or self.win: return
        self.win=tk.Toplevel(self.widget); self.win.wm_overrideredirect(True)
        tk.Label(self.win,text=text,bg=self.t['RAISED'],fg=self.t['TEXT'],bd=0,padx=8,pady=4,justify='left',wraplength=640,
                 highlightthickness=1,highlightbackground=self.t['BTN_LINE']).pack()
        x=self.widget.winfo_rootx(); y=self.widget.winfo_rooty()+self.widget.winfo_height()+4
        self.win.wm_geometry(f'+{x}+{y}')
    def hide(self,_=None):
        if self.win: self.win.destroy(); self.win=None

def _clock(seconds):
    s=int(seconds); return f'{s//3600:d}:{s%3600//60:02d}:{s%60:02d}'

def _photo(image):
    # Tk 8.6 reads PNG natively, so PIL.ImageTk (an extra frozen dependency) is not needed.
    stream=io.BytesIO(); image.save(stream,format='PNG')
    return tk.PhotoImage(data=base64.b64encode(stream.getvalue()).decode('ascii'))

def _icon(size,colour):
    # Rounded square with a document glyph, drawn at 4x and scaled down for smooth edges.
    k=4; s=size*k; im=Image.new('RGBA',(s,s),(0,0,0,0)); d=ImageDraw.Draw(im)
    d.rounded_rectangle((0,0,s-1,s-1),radius=int(s*.24),fill=colour)
    w=int(s*.44); h=int(s*.56); x=(s-w)//2; y=(s-h)//2; f=int(w*.34); lw=max(k,int(s*.055))
    d.line([(x,y),(x+w-f,y),(x+w,y+f),(x+w,y+h),(x,y+h),(x,y)],fill='white',width=lw,joint='curve')
    d.line([(x+w-f,y),(x+w-f,y+f),(x+w,y+f)],fill='white',width=lw)
    for r in (.52,.72): d.line([(x+w*.22,y+h*r),(x+w*.78,y+h*r)],fill='white',width=lw)
    return im.resize((size,size),Image.Resampling.LANCZOS)

def _check(size,on,t):
    k=4; s=size*k; im=Image.new('RGBA',(s,s),(0,0,0,0)); d=ImageDraw.Draw(im)
    d.rounded_rectangle((0,0,s-1,s-1),radius=int(s*.2),fill=t['ACCENT'] if on else t['CHECK_OFF'],
                        outline=t['ACCENT'] if on else t['CHECK_LINE'],width=int(k*1.5))
    if on: d.line([(s*.24,s*.52),(s*.43,s*.70),(s*.77,s*.31)],fill='white',width=int(s*.12),joint='curve')
    return im.resize((size,size),Image.Resampling.LANCZOS)

def _theme_glyph(size,t):
    # Sun (switch to light) or moon (switch to dark) for the header toggle.
    k=4; s=size*k; im=Image.new('RGBA',(s,s),(0,0,0,0)); d=ImageDraw.Draw(im); c=t['MUTED']; lw=int(s*.08)
    if t['dark']:
        r=s*.2; d.ellipse((s/2-r,s/2-r,s/2+r,s/2+r),outline=c,width=lw)
        import math
        for i in range(8):
            a=i*math.pi/4; d.line([(s/2+math.cos(a)*s*.32,s/2+math.sin(a)*s*.32),(s/2+math.cos(a)*s*.44,s/2+math.sin(a)*s*.44)],fill=c,width=lw)
    else:
        d.ellipse((s*.14,s*.14,s*.86,s*.86),fill=c); d.ellipse((s*.34,s*.02,s*1.02,s*.70),fill=(0,0,0,0))
    return im.resize((size,size),Image.Resampling.LANCZOS)

def _chevron(size,open_,colour):
    k=4; s=size*k; im=Image.new('RGBA',(s,s),(0,0,0,0)); d=ImageDraw.Draw(im); lw=int(s*.13)
    pts=[(s*.3,s*.38),(s*.5,s*.6),(s*.7,s*.38)] if open_ else [(s*.4,s*.28),(s*.62,s*.5),(s*.4,s*.72)]
    d.line(pts,fill=colour,width=lw,joint='curve')
    return im.resize((size,size),Image.Resampling.LANCZOS)

class Badge(tk.Label):
    def __init__(self,parent,colours,**kw):
        bg,border,fg=colours
        super().__init__(parent,bd=0,padx=6,pady=1,highlightthickness=1,bg=bg,fg=fg,highlightbackground=border,highlightcolor=border,**kw)

class App:
    def __init__(self,root):
        self.root=root; root.title(APP_NAME); root.minsize(540,0)
        self.queue=queue.Queue(); self.cancel=threading.Event(); self.running=False; self.result=None; self.started=0; self.spin=0
        self.last_event=None; self.result_event=None; self.options_open=False; self._elements=set(); self.final_time='0:00:00'
        self.pages=None; self.current_name=''; self.dialog=None
        self.ui=_pick(root,('Segoe UI Variable Text','Segoe UI','Noto Sans','DejaVu Sans'),'TkDefaultFont')
        self.mono=_pick(root,('Cascadia Mono','Cascadia Code','Consolas','DejaVu Sans Mono'),'TkFixedFont')
        saved=DEFAULTS.copy()
        try: saved.update(json.loads((data_dir()/'settings.json').read_text()))
        except (OSError,ValueError,RuntimeError): pass
        if saved.get('quick') and saved.get('quality','standard')=='standard': saved['quality']='quick'
        # Tk variables live on the root, so they survive a theme switch that rebuilds the widgets.
        self.source=tk.StringVar()
        self.language=tk.StringVar(value=LANGS.get(saved['language'],'Arabic + English'))
        self.quality=tk.StringVar(value=QUALITY.get(saved.get('quality','standard'),'Standard'))
        self.ocr=tk.BooleanVar(value=saved['ocr']!='off'); self.timeout=tk.StringVar(value=str(int(float(saved['timeout']))))
        self.source.trace_add('write',self._update_preview)
        for var in (self.language,self.quality,self.ocr): var.trace_add('write',lambda *_:self._update_options())
        # The theme is a window preference, kept apart from conversion settings (which affect the output cache).
        self.theme='light'   # light theme only (UI3)
        self.shell=None; self._build()
        root.protocol('WM_DELETE_WINDOW',self.close); root.after(100,self.poll)

    # ---------- building ----------
    def _build(self):
        t=self.t=THEMES[self.theme]; u,m=self.ui,self.mono
        if self.shell: self.shell.destroy()
        self.root.configure(bg=t['WINDOW'])
        self._images={'icon':_photo(_icon(26,t['ACCENT'])),'app':_photo(_icon(64,t['ACCENT'])),'toggle':_photo(_theme_glyph(16,t)),
                      'off':_photo(_check(15,False,t)),'on':_photo(_check(15,True,t)),
                      'closed':_photo(_chevron(14,False,t['LINK'])),'open':_photo(_chevron(14,True,t['LINK']))}
        try: self.root.iconphoto(True,self._images['app'])
        except tk.TclError: pass
        self._styles(); self._titlebar()
        shell=self.shell=tk.Frame(self.root,bg=t['WINDOW']); shell.pack(fill='both',expand=True)

        # Header
        head=tk.Frame(shell,bg=t['HEADER']); head.pack(fill='x')
        inner=tk.Frame(head,bg=t['HEADER']); inner.pack(fill='x',padx=16,pady=(12,10))
        tk.Label(inner,image=self._images['icon'],bg=t['HEADER']).pack(side='left')
        names=tk.Frame(inner,bg=t['HEADER']); names.pack(side='left',padx=(10,0))
        top=tk.Frame(names,bg=t['HEADER']); top.pack(anchor='w')
        tk.Label(top,text=APP_NAME,bg=t['HEADER'],fg=t['TEXT'],font=(u,11,'bold')).pack(side='left')
        Badge(top,t['BADGES']['brand'],text=APP_VERSION,font=(m,7)).pack(side='left',padx=(7,0))
        sub=tk.Frame(names,bg=t['HEADER']); sub.pack(anchor='w')
        tk.Label(sub,text=f'Documents → Markdown  •  offline  •  by {AUTHOR}',bg=t['HEADER'],fg=t['MUTED'],font=(u,8)).pack(side='left')
        home=tk.Label(sub,text='GitHub ↗',bg=t['HEADER'],fg=t['LINK'],font=(u,8),cursor='hand2'); home.pack(side='left',padx=(8,0))
        home.bind('<Button-1>',lambda e:webbrowser.open(HOMEPAGE))
        about=tk.Label(inner,text='About',bg=t['HEADER'],fg=t['MUTED'],font=(u,8),cursor='hand2',padx=6,pady=3); about.pack(side='right')
        about.bind('<Button-1>',lambda e:self.about())
        about.bind('<Enter>',lambda e:about.configure(fg=t['TEXT'])); about.bind('<Leave>',lambda e:about.configure(fg=t['MUTED']))
        tk.Frame(shell,bg=t['HEADER_LINE'],height=1).pack(fill='x')

        body=tk.Frame(shell,bg=t['WINDOW']); body.pack(fill='both',expand=True,padx=16,pady=(12,12))
        # Folder picker
        tk.Label(body,text='FOLDER TO CONVERT',bg=t['WINDOW'],fg=t['SOFT'],font=(u,8,'bold')).pack(anchor='w')
        row=tk.Frame(body,bg=t['WINDOW']); row.pack(fill='x',pady=(5,4))
        self.field=ttk.Entry(row,textvariable=self.source,style='Path.TEntry',font=(m,9)); self.field.pack(side='left',fill='x',expand=True,ipady=4)
        self.browse=ttk.Button(row,text='Browse…',style='Ghost.TButton',command=self.pick); self.browse.pack(side='left',padx=(8,0))
        saves=tk.Frame(body,bg=t['WINDOW']); saves.pack(fill='x')
        self.copy=tk.Label(saves,text='⧉ Copy',bg=t['WINDOW'],fg=t['LINK'],font=(u,8),cursor='hand2'); self.copy.pack(side='right',padx=(8,0))
        tk.Label(saves,text='Saves to:',bg=t['WINDOW'],fg=t['MUTED'],font=(u,8)).pack(side='left')
        self.preview=tk.Label(saves,bg=t['WINDOW'],fg=t['MUTED'],font=(m,8),anchor='w'); self.preview.pack(side='left',padx=(4,0),fill='x',expand=True)
        self.copy.bind('<Button-1>',self.copy_output)

        # Options accordion
        opts=tk.Frame(body,bg=t['OPTS_HEAD'],highlightthickness=1,highlightbackground=t['OPTS_LINE']); opts.pack(fill='x',pady=(12,0))
        bar=tk.Frame(opts,bg=t['OPTS_HEAD'],cursor='hand2'); bar.pack(fill='x')
        self.chev=tk.Label(bar,image=self._images['closed'],bg=t['OPTS_HEAD'],cursor='hand2'); self.chev.pack(side='left',padx=(10,4),pady=6)
        title=tk.Label(bar,text='Options',bg=t['OPTS_HEAD'],fg=t['TEXT'],font=(u,9,'bold'),cursor='hand2'); title.pack(side='left')
        self.summary_opts=tk.Label(bar,bg=t['OPTS_HEAD'],fg=t['MUTED'],font=(u,8),cursor='hand2'); self.summary_opts.pack(side='right',padx=10)
        for w in (bar,self.chev,title,self.summary_opts): w.bind('<Button-1>',lambda e:self.show_settings())
        self.settings_frame=grid=tk.Frame(opts,bg=t['OPTS'])
        tk.Frame(grid,bg=t['OPTS_LINE'],height=1).grid(row=0,column=0,columnspan=3,sticky='ew')
        for c in range(3): grid.columnconfigure(c,weight=1,uniform='opt')
        def label(text,col): tk.Label(grid,text=text,bg=t['OPTS'],fg=t['SOFT'],font=(u,8)).grid(row=1,column=col,sticky='w',padx=(10 if col==0 else 6,6),pady=(8,3))
        label('Text language',0); label('OCR quality',1); label('Time limit / file (sec)',2)
        ttk.Combobox(grid,textvariable=self.language,values=list(LANGS.values()),state='readonly',style='App.TCombobox',font=(u,9)).grid(row=2,column=0,sticky='ew',padx=(10,6))
        ttk.Combobox(grid,textvariable=self.quality,values=list(QUALITY.values()),state='readonly',style='App.TCombobox',font=(u,9)).grid(row=2,column=1,sticky='ew',padx=6)
        ttk.Spinbox(grid,textvariable=self.timeout,from_=60,to=86400,increment=600,style='App.TSpinbox',font=(m,9)).grid(row=2,column=2,sticky='ew',padx=(6,10))
        self.quality_hint=tk.Label(grid,bg=t['OPTS'],fg=t['FAINT'],font=(u,8)); self.quality_hint.grid(row=3,column=0,columnspan=3,sticky='w',padx=10,pady=(4,0))
        ttk.Checkbutton(grid,text='  Read text in scans and images',variable=self.ocr,style='App.TCheckbutton').grid(row=4,column=0,columnspan=3,sticky='w',padx=10,pady=(6,10))
        if self.options_open: self.settings_frame.pack(fill='x'); self.chev.configure(image=self._images['open'])

        # Actions
        self.actions=tk.Frame(body,bg=t['WINDOW']); self.actions.pack(fill='x',pady=(12,0))
        self.convert=ttk.Button(self.actions,text='▶  Convert',style='Primary.TButton',command=self.start); self.convert.pack(side='left')
        self.cancel_button=ttk.Button(self.actions,text='Cancel',style='Ghost.TButton',command=self.stop,state='disabled'); self.cancel_button.pack(side='left',padx=(8,0))
        clock=tk.Frame(self.actions,bg=t['CLOCK'],highlightthickness=1,highlightbackground=t['CLOCK_LINE']); clock.pack(side='right')
        self.dot=tk.Label(clock,text='●',bg=t['CLOCK'],fg=t['FAINT'],font=(u,7)); self.dot.pack(side='left',padx=(8,3),pady=3)
        tk.Label(clock,text='Elapsed:',bg=t['CLOCK'],fg=t['MUTED'],font=(u,8)).pack(side='left')
        self.timing=tk.Label(clock,text='0:00:00',bg=t['CLOCK'],fg=t['TEXT'],font=(m,9,'bold')); self.timing.pack(side='left',padx=(4,8))

        # Progress panel
        prog=tk.Frame(body,bg=t['PANEL'],highlightthickness=1,highlightbackground=t['PANEL_LINE']); prog.pack(fill='x',pady=(12,0))
        inner=tk.Frame(prog,bg=t['PANEL']); inner.pack(fill='x',padx=12,pady=10)
        top=tk.Frame(inner,bg=t['PANEL']); top.pack(fill='x')
        tk.Label(top,text='All files',bg=t['PANEL'],fg=t['TEXT'],font=(u,9,'bold')).pack(side='left')
        self.files_text=Badge(top,t['BADGES']['brand'],text='—',font=(m,8)); self.files_text.pack(side='right')
        self.progress=ttk.Progressbar(inner,style='All.Horizontal.TProgressbar',mode='determinate'); self.progress.pack(fill='x',pady=(7,4))
        counts=tk.Frame(inner,bg=t['PANEL']); counts.pack(fill='x',pady=(0,9))
        self.files_count=tk.Label(counts,text='',bg=t['PANEL'],fg=t['MUTED'],font=(m,8)); self.files_count.pack(side='left')
        tk.Frame(inner,bg=t['LINE'],height=1).pack(fill='x')
        # File name and "Page 240 of 356" in separate columns; the name is shortened in the middle to fit (Update21)
        mid=tk.Frame(inner,bg=t['PANEL']); mid.pack(fill='x',pady=(9,0)); mid.columnconfigure(1,weight=1)
        self.tag=tk.Label(mid,text='',bg=t['PANEL'],fg=t['FAINT'],font=(m,7,'bold')); self.tag.grid(row=0,column=0,sticky='w')
        self.name_font=tkfont.Font(family=m,size=8)
        self.current=tk.Label(mid,text='No file in progress',bg=t['PANEL'],fg=t['MUTED'],font=self.name_font,anchor='w',width=1)
        self.current.grid(row=0,column=1,sticky='ew',padx=(4,10))
        self.step_text=tk.Label(mid,text='',bg=t['PANEL'],fg=t['MUTED'],font=(m,8),anchor='e'); self.step_text.grid(row=0,column=2,sticky='e')
        self.current.bind('<Configure>',lambda e:self._show_name())
        Tip(self.current,lambda:self.current_name if self.current.cget('text')!=self.current_name else '',t)
        self.file_progress=ttk.Progressbar(inner,style='File.Horizontal.TProgressbar',mode='determinate'); self.file_progress.pack(fill='x',pady=(6,5))
        low=tk.Frame(inner,bg=t['PANEL']); low.pack(fill='x')
        self.status=tk.Label(low,text='Ready',bg=t['PANEL'],fg=t['MUTED'],font=(u,8,'italic')); self.status.pack(side='left')
        self.percent=tk.Label(low,text='',bg=t['PANEL'],fg=t['MUTED'],font=(m,8)); self.percent.pack(side='right')
        # This line stays hidden until the complete folder has finished.
        self.results_line=tk.Frame(inner,bg=t['PANEL'])
        tk.Frame(self.results_line,bg=t['LINE'],height=1).pack(fill='x',pady=(9,7))
        self.badges=tk.Frame(self.results_line,bg=t['PANEL']); self.badges.pack(side='left')
        tk.Label(self.results_line,text='Offline OCR',bg=t['PANEL'],fg=t['FAINT'],font=(u,8)).pack(side='right')

        # Footer
        tk.Frame(shell,bg=t['HEADER_LINE'],height=1).pack(fill='x')
        foot=tk.Frame(shell,bg=t['WINDOW']); foot.pack(fill='x',padx=16,pady=9)
        self.open_button=ttk.Button(foot,text='↗  Open output folder',style='Small.TButton',state='disabled',command=lambda:self.open_result('output')); self.open_button.pack(side='left')
        self.report_button=ttk.Button(foot,text='≡  View report',style='Small.TButton',state='disabled',command=lambda:self.open_result('report')); self.report_button.pack(side='left',padx=(8,0))
        self.state_text=tk.Label(foot,text='Ready',bg=t['WINDOW'],fg=t['MUTED'],font=(u,8)); self.state_text.pack(side='right')
        self.state_dot=tk.Label(foot,text='●',bg=t['WINDOW'],fg=t['FAINT'],font=(u,7)); self.state_dot.pack(side='right',padx=(0,5))
        self.completion_text=tk.Label(shell,text='',bg=t['WINDOW'],fg=t['FAIL'],font=(u,8,'bold'),anchor='w',justify='left')
        self.completion_text.pack(fill='x',padx=16,pady=(0,9))

        self._update_preview(); self._update_options(); self._restore(); self._fit()

    def _show_name(self,name=None,colour=None):
        if name is not None: self.current_name=name
        if colour: self.current.configure(fg=colour)
        width=self.current.winfo_width()-4
        self.current.configure(text=_middle(self.current_name,self.name_font,width) if width>20 else self.current_name)

    def _dialog(self,title,message,buttons,default):
        """Themed modal dialog; buttons = [(key, text)], the default one first in keyboard focus. Returns the key."""
        t=self.t; u=self.ui; choice={'key':default}
        win=self.dialog=tk.Toplevel(self.root); win.title(title); win.configure(bg=t['WINDOW']); win.resizable(False,False)
        win.transient(self.root)
        body=tk.Frame(win,bg=t['WINDOW']); body.pack(fill='both',expand=True,padx=18,pady=(16,12))
        tk.Label(body,text=title,bg=t['WINDOW'],fg=t['TEXT'],font=(u,10,'bold'),anchor='w',justify='left').pack(fill='x')
        tk.Label(body,text=message,bg=t['WINDOW'],fg=t['SOFT'],font=(u,9),anchor='w',justify='left',wraplength=420).pack(fill='x',pady=(8,14))
        row=tk.Frame(body,bg=t['WINDOW']); row.pack(fill='x')
        def pick(key): choice['key']=key; win.destroy()
        first=None
        for key,text in reversed(buttons):
            b=ttk.Button(row,text=text,style='Primary.TButton' if key==default else 'Ghost.TButton',command=lambda k=key:pick(k))
            b.pack(side='right',padx=(8,0))
            if key==default: first=b
        win.bind('<Escape>',lambda e:pick(default)); win.bind('<Return>',lambda e:pick(default))
        win.protocol('WM_DELETE_WINDOW',lambda:pick(default))
        win.update_idletasks()
        x=self.root.winfo_rootx()+(self.root.winfo_width()-win.winfo_reqwidth())//2
        y=self.root.winfo_rooty()+max(0,(self.root.winfo_height()-win.winfo_reqheight())//3)
        win.geometry(f'+{max(0,x)}+{max(0,y)}')
        try: win.grab_set()
        except tk.TclError: pass
        if first: first.focus_set()
        self.root.wait_window(win); self.dialog=None
        return choice['key']

    def about(self):
        """About screen with the notices the GNU AGPL asks an interactive program to show."""
        if self.dialog: return
        t=self.t; u=self.ui
        win=self.dialog=tk.Toplevel(self.root); win.title('About '+APP_NAME); win.configure(bg=t['WINDOW']); win.resizable(False,False)
        win.transient(self.root)
        body=tk.Frame(win,bg=t['WINDOW']); body.pack(fill='both',expand=True,padx=20,pady=(18,14))
        top=tk.Frame(body,bg=t['WINDOW']); top.pack(fill='x')
        tk.Label(top,image=self._images['icon'],bg=t['WINDOW']).pack(side='left')
        tk.Label(top,text=f'{APP_NAME} {__version__}',bg=t['WINDOW'],fg=t['TEXT'],font=(u,12,'bold')).pack(side='left',padx=(10,0))
        tk.Label(body,text=f'by {AUTHOR}',bg=t['WINDOW'],fg=t['MUTED'],font=(u,9),anchor='w').pack(fill='x',pady=(8,0))
        tk.Label(body,text=COPYRIGHT,bg=t['WINDOW'],fg=t['SOFT'],font=(u,9),anchor='w').pack(fill='x',pady=(2,10))
        tk.Label(body,text=WARRANTY,bg=t['WINDOW'],fg=t['SOFT'],font=(u,9),anchor='w',justify='left',wraplength=430).pack(fill='x')
        tk.Label(body,text='Runs offline. The GitHub button only opens the project page in your browser.',bg=t['WINDOW'],
                 fg=t['FAINT'],font=(u,8),anchor='w',justify='left',wraplength=430).pack(fill='x',pady=(10,14))
        row=tk.Frame(body,bg=t['WINDOW']); row.pack(fill='x')
        def close(): win.destroy()
        ttk.Button(row,text='Close',style='Primary.TButton',command=close).pack(side='right')
        ttk.Button(row,text='GitHub ↗',style='Ghost.TButton',command=lambda:webbrowser.open(HOMEPAGE)).pack(side='right',padx=(0,8))
        ttk.Button(row,text='View license',style='Ghost.TButton',command=self.view_license).pack(side='right',padx=(0,8))
        win.bind('<Escape>',lambda e:close()); win.protocol('WM_DELETE_WINDOW',close)
        win.update_idletasks()
        x=self.root.winfo_rootx()+(self.root.winfo_width()-win.winfo_reqwidth())//2
        y=self.root.winfo_rooty()+max(0,(self.root.winfo_height()-win.winfo_reqheight())//3)
        win.geometry(f'+{max(0,x)}+{max(0,y)}')
        try: win.grab_set()
        except tk.TclError: pass
        self.root.wait_window(win); self.dialog=None

    def view_license(self):
        path=app_root()/'LICENSE'
        if not path.is_file():
            messagebox.showinfo('License','The license file is missing from this copy. The text of the GNU AGPL v3 is at https://www.gnu.org/licenses/agpl-3.0.html'); return
        try: os.startfile(str(path))
        except (AttributeError,OSError): webbrowser.open(path.as_uri())

    def _restore(self):
        # Re-show the job state after a theme switch.
        if self.running:
            for w in (self.convert,self.browse,self.field): w.configure(state='disabled')
            self.cancel_button.configure(state='disabled' if self.cancel.is_set() else 'normal')
            self._state('Cancelling' if self.cancel.is_set() else 'Processing batch','WAIT' if self.cancel.is_set() else 'RUN')
            self.timing.configure(text=_clock(time.monotonic()-self.started))
            if self.last_event: self.handle(self.last_event,replay=True)
            else: self._bar(self.progress)
        elif self.result_event:
            if self.last_event: self.handle(self.last_event,replay=True)
            self.handle(self.result_event,replay=True); self.timing.configure(text=self.final_time)

    def _styles(self):
        t=self.t; u=self.ui
        for key,value in (('background',t['RAISED']),('foreground',t['TEXT']),('selectBackground',t['ACCENT']),
                          ('selectForeground','white'),('font',(u,9)),('borderWidth',0)):
            self.root.option_add('*TCombobox*Listbox.'+key,value)
        s=ttk.Style(); s.theme_use('clam')
        s.configure('.',font=(u,9),background=t['WINDOW'],foreground=t['TEXT'],bordercolor=t['BTN_LINE'],lightcolor=t['BTN_LINE'],darkcolor=t['BTN_LINE'],
                    focuscolor=t['ACCENT'],troughcolor=t['TRACK'],selectbackground=t['ACCENT'],selectforeground='white',insertcolor=t['TEXT'])
        s.configure('Path.TEntry',fieldbackground=t['INSET'],foreground=t['SOFT'],padding=(9,3),insertcolor=t['TEXT'],
                    bordercolor=t['BTN_LINE'],lightcolor=t['BTN_LINE'],darkcolor=t['BTN_LINE'])
        s.map('Path.TEntry',bordercolor=[('focus',t['ACCENT'])],lightcolor=[('focus',t['ACCENT'])],darkcolor=[('focus',t['ACCENT'])],
              fieldbackground=[('disabled',t['INSET_OFF'])],foreground=[('disabled',t['FAINT'])])
        field=t['RAISED']
        for name in ('App.TCombobox','App.TSpinbox'):
            s.configure(name,fieldbackground=field,background=field,foreground=t['TEXT'],arrowcolor=t['MUTED'],padding=(8,3),arrowsize=11,
                        insertcolor=t['TEXT'],bordercolor=t['BTN_LINE'],lightcolor=field,darkcolor=field)
            s.map(name,fieldbackground=[('readonly',field),('disabled',t['INSET_OFF'])],foreground=[('disabled',t['FAINT']),('readonly',t['TEXT'])],
                  bordercolor=[('focus',t['ACCENT'])],lightcolor=[('focus',field)],darkcolor=[('focus',field)],background=[('active',t['HOVER'])],
                  selectbackground=[('readonly',field)],selectforeground=[('readonly',t['TEXT'])])
        s.configure('Primary.TButton',background=t['ACCENT'],foreground='white',font=(u,9,'bold'),padding=(18,6),borderwidth=0,
                    bordercolor=t['ACCENT'],lightcolor=t['ACCENT'],darkcolor=t['ACCENT'],focuscolor=t['ACCENT'])
        s.map('Primary.TButton',background=[('disabled',t['ACCENT_OFF']),('pressed',t['ACCENT_PRESSED']),('active',t['ACCENT_HOVER'])],
              foreground=[('disabled',t['ACCENT_OFF_TEXT'])],lightcolor=[('active',t['ACCENT_HOVER']),('disabled',t['ACCENT_OFF'])],
              darkcolor=[('active',t['ACCENT_HOVER']),('disabled',t['ACCENT_OFF'])],bordercolor=[('active',t['ACCENT_HOVER']),('disabled',t['ACCENT_OFF'])])
        for name,pad,size in (('Ghost.TButton',(14,6),9),('Small.TButton',(10,4),8)):
            s.configure(name,background=t['RAISED'],foreground=t['TEXT'],padding=pad,borderwidth=1,bordercolor=t['BTN_LINE'],lightcolor=t['RAISED'],
                        darkcolor=t['RAISED'],font=(u,size),focuscolor=t['RAISED'])
            s.map(name,background=[('disabled',t['WINDOW']),('pressed',t['PRESSED']),('active',t['HOVER'])],foreground=[('disabled',t['FAINT'])],
                  bordercolor=[('disabled',t['LINE']),('active',t['BTN_LINE_HOVER'])],lightcolor=[('active',t['HOVER']),('disabled',t['WINDOW'])],
                  darkcolor=[('active',t['HOVER']),('disabled',t['WINDOW'])])
        element='check.'+self.theme
        if element not in self._elements:
            s.element_create(element,'image',self._images['off'],('selected',self._images['on'])); self._elements.add(element)
            self._keep=getattr(self,'_keep',{}); self._keep[element]=(self._images['off'],self._images['on'])
        s.layout('App.TCheckbutton',[('Checkbutton.padding',{'sticky':'nswe','children':[(element,{'side':'left','sticky':''}),
                  ('Checkbutton.label',{'side':'left','sticky':'nswe'})]})])
        s.configure('App.TCheckbutton',background=t['OPTS'],foreground=t['SOFT'],font=(u,9),padding=0)
        s.map('App.TCheckbutton',background=[('active',t['OPTS'])],foreground=[('disabled',t['FAINT'])])
        for name,colour,thick in (('All',t['BAR'],8),('File',t['BAR_FILE'],6)):
            s.configure(name+'.Horizontal.TProgressbar',troughcolor=t['TRACK'],background=colour,bordercolor=t['TRACK'],lightcolor=colour,darkcolor=colour,thickness=thick)

    def _titlebar(self):
        # Windows 10/11: match the title bar to the theme.
        if os.name!='nt': return
        try:
            import ctypes
            self.root.update_idletasks(); hwnd=ctypes.windll.user32.GetParent(self.root.winfo_id())
            value=ctypes.c_int(1 if self.t['dark'] else 0)
            for attribute in (20,19):
                if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd,attribute,ctypes.byref(value),ctypes.sizeof(value))==0: break
            # Nudge Windows to repaint the non-client area with the new colour.
            self.root.withdraw(); self.root.deiconify()
        except Exception: pass

    def _fit(self):
        self.root.update_idletasks()
        width=max(560,self.root.winfo_width() if self.root.winfo_ismapped() else 560)
        self.root.geometry(f'{width}x{self.root.winfo_reqheight()}')

    def _update_preview(self,*_):
        if not getattr(self,'preview',None): return
        value=self.source.get()
        if not value: self.preview.configure(text='a new folder inside the one you choose',fg=self.t['MUTED']); return
        self.preview.configure(text=_shorten(output_path(value),46),fg=self.t['SOFT'])

    def _update_options(self):
        if not getattr(self,'quality_hint',None): return
        q={v:k for k,v in QUALITY.items()}.get(self.quality.get(),'standard')
        self.quality_hint.configure(text=QUALITY_HINT[q])
        self.summary_opts.configure(text=f"{self.language.get()}  •  OCR {'on' if self.ocr.get() else 'off'}  •  {self.quality.get()}")

    def _badge_row(self,parts):
        for w in self.badges.winfo_children(): w.destroy()
        for text,kind in parts: Badge(self.badges,self.t['BADGES'][kind],text='● '+text,font=(self.ui,8)).pack(side='left',padx=(0,6))
        if parts: self.results_line.pack(fill='x')
        else: self.results_line.pack_forget()

    def _bar(self,bar,value=None,maximum=None):
        if value is None:
            if str(bar.cget('mode'))!='indeterminate': bar.configure(mode='indeterminate'); bar.start(16)
        else:
            if str(bar.cget('mode'))=='indeterminate': bar.stop()
            bar.configure(mode='determinate',maximum=max(maximum or 1,1)); bar.configure(value=value)

    def _state(self,text,colour_key):
        colour=self.t[colour_key]; self.state_text.configure(text=text); self.state_dot.configure(fg=colour); self.dot.configure(fg=colour)

    # ---------- behaviour ----------
    def switch_theme(self):
        # Light theme only (UI3); kept so older callers still work.
        return
    def pick(self):
        result=filedialog.askdirectory(title='Choose the folder to convert',mustexist=True)
        if result:self.source.set(result)
    def copy_output(self,_=None):
        if not self.source.get(): return
        self.root.clipboard_clear(); self.root.clipboard_append(str(output_path(self.source.get())))
        label=self.copy; label.configure(text='✓ Copied')
        self.root.after(1500,lambda:label.winfo_exists() and label.configure(text='⧉ Copy'))
    def show_settings(self):
        if self.running: return
        self.options_open=not self.options_open
        if self.options_open: self.settings_frame.pack(fill='x'); self.chev.configure(image=self._images['open'])
        else: self.settings_frame.pack_forget(); self.chev.configure(image=self._images['closed'])
        self._fit()
    def start(self):
        if self.running:return
        if not self.source.get(): self.pick(); return
        try:
            timeout=float(self.timeout.get())
            if not 1<=timeout<=86400: raise ValueError()
            settings={'language':{v:k for k,v in LANGS.items()}[self.language.get()],'ocr':'auto' if self.ocr.get() else 'off','timeout':timeout,
                      'quality':{v:k for k,v in QUALITY.items()}[self.quality.get()]}
            atomic_json(data_dir()/'settings.json',settings)
        except (ValueError,RuntimeError,OSError) as e: messagebox.showerror('Options',str(e) or 'Enter a time limit from 1 to 86400 seconds.'); return
        self.cancel.clear(); self.running=True; self.started=time.monotonic(); self.result=None; self.last_event=None; self.result_event=None
        self.pages=None; self.files_count.configure(text='')
        for w in (self.convert,self.browse,self.field,self.open_button,self.report_button): w.configure(state='disabled')
        self.cancel_button.configure(state='normal')
        self._bar(self.progress); self._bar(self.file_progress,0,1)
        self.files_text.configure(text='Finding files…'); self.step_text.configure(text=''); self.percent.configure(text='')
        self.completion_text.configure(text='')
        self._show_name('—',self.t['MUTED']); self.tag.configure(text=''); self.status.configure(text='Starting'); self._badge_row([])
        self._state('Processing batch','RUN')
        source=self.source.get()
        def task():
            try: run_job(source,settings,self.cancel,self.queue.put)
            except Exception as e:self.queue.put({'error':str(e)})
        threading.Thread(target=task,daemon=True).start()
    def stop(self):
        if not self.running or self.cancel.is_set() or self.dialog: return
        key=self._dialog('Stop the conversion?','Files already converted are kept. The file being converted now is stopped, '
                         'and running the same folder again later continues from where it stopped.',
                         [('keep','Keep converting'),('stop','Stop')],'keep')
        if key=='stop' and self.running: self._stop()
    def _stop(self):
        self.cancel.set(); self.status.configure(text='Cancelling — finished files are kept.'); self.cancel_button.configure(state='disabled')
        self._state('Cancelling','WAIT')
    def finish(self):
        self.running=False
        for bar in (self.progress,self.file_progress):
            if str(bar.cget('mode'))=='indeterminate': bar.stop(); bar.configure(mode='determinate',value=0)
        for w in (self.convert,self.browse,self.field): w.configure(state='normal')
        self.cancel_button.configure(state='disabled')
    def handle(self,event,replay=False):
        t=self.t
        if 'error' in event:
            self.finish(); self.status.configure(text='Could not complete this job.'); self._state('Stopped','FAIL')
            messagebox.showerror(APP_NAME,event['error']); return
        if 'result' not in event and not replay: self.last_event=event
        stage=event.get('stage',''); done=event.get('completed',0); total=event.get('discovered',0)
        if 'pages_total' in event:
            self.pages=(event['pages_done'],event['pages_total'],event.get('pages_skipped',0))
        if stage in ('Finding files','Counting pages'):
            self._bar(self.progress); self.files_text.configure(text='Counting pages…' if stage=='Counting pages' else 'Finding files…')
        elif self.pages and self.pages[1]>0:
            self._bar(self.progress,self.pages[0],self.pages[1]); self.files_text.configure(text=format_pages_progress(self.pages[0],self.pages[1]))
            self.files_count.configure(text=f'{done} of {total} files')
        else: self._bar(self.progress,done,total); self.files_text.configure(text=f'{done} of {total} files')
        if event.get('current'):
            name=event['current']; ext=os.path.splitext(name)[1].lower()
            self._show_name(name,t['TEXT'])
            self.tag.configure(text=ext[1:].upper()[:4] if ext else '',fg=t['TAGS'].get(FILE_KINDS.get(ext),t['MUTED']))
        step,steps,unit=event.get('step'),event.get('steps'),event.get('unit') or 'Step'
        if stage=='File finished':
            fraction=event.get('file_fraction',1 if event.get('status') in ('converted','partial','unchanged') else 0)
            self._bar(self.file_progress,fraction,1)
            self.step_text.configure(text='Stopped' if event.get('status')=='cancelled' else 'Failed' if event.get('status')=='failed' else 'Done')
            self.percent.configure(text=f'{100*fraction:.0f}%')
        elif stage=='Checking file':
            self._bar(self.file_progress,0,1); self.step_text.configure(text=''); self.percent.configure(text='')
        elif steps:
            self.step_text.configure(text=f'{unit} {step} of {steps}')
            finished=event.get('unit_completed',max(0,step-1)) if unit in ('Page','Slide','Sheet','Frame') else step
            self._bar(self.file_progress,finished,steps)
            self.percent.configure(text=f'{int(100*finished/steps)}%')
        elif stage not in ('Finding files','Finished'):
            self._bar(self.file_progress); self.step_text.configure(text='Working…'); self.percent.configure(text='')
        self.status.configure(text=stage)
        if 'result' in event:
            if not replay: self.final_time=self.timing.cget('text')
            self.result=event['result']; self.result_event=event; self.finish(); s=self.result['summary']
            stopped=self.result.get('cancelled',False) or bool(s.get('cancelled'))
            if self.pages and self.pages[1]>0:
                self._bar(self.progress,self.pages[0],self.pages[1])
                self.files_text.configure(text=format_pages_progress(self.pages[0],self.pages[1]))
                self.files_count.configure(text=f'{done} of {total} files')
            else:
                self._bar(self.progress,done,total); self.files_text.configure(text=f'{done} of {total} files'); self.files_count.configure(text='')
            self._show_name('Conversion stopped' if stopped else 'All files processed',t['SOFT']); self.tag.configure(text='')
            self.status.configure(text='Stopped' if stopped else 'Finished with failures' if s.get('failed') else 'Finished')
            if 'finished_at' not in self.result:
                self.result['finished_at']=datetime.now().astimezone().isoformat(timespec='seconds')
            completed_at=datetime.fromisoformat(self.result['finished_at']).strftime('%d/%m/%Y %H:%M:%S')
            if stopped:
                self.completion_text.configure(text=f'Conversion stopped on {completed_at}')
            elif s.get('failed'):
                late=len(self.result.get('timed_out') or [])
                self.completion_text.configure(text=f'Conversion completed with errors on {completed_at}'+(f' — {late} file(s) reached the time limit; raise it in Options and run again' if late else ''))
            else:
                self.completion_text.configure(text=f'Folder conversion completed on {completed_at}')
            # "partial" files were converted too; they only carry review notes (e.g. OCR text).
            parts=[(f'{s.get("converted",0)+s.get("partial",0)} converted','ok')]
            for key,label,kind in (('partial','need review','warn'),('failed','failed','bad'),('unchanged','unchanged','muted'),
                                   ('unsupported','unsupported','muted'),('cancelled','cancelled','muted')):
                if s.get(key): parts.append((f'{s[key]} {label}',kind))
            self._badge_row(parts)
            if not replay: self._fit()
            self._state('Stopped' if stopped else 'Finished with failures' if s.get('failed') else 'Finished','FAIL' if stopped or s.get('failed') else 'DONE')
            self.open_button.configure(state='normal');self.report_button.configure(state='normal')
    def poll(self):
        try:
            while True: self.handle(self.queue.get_nowait())
        except queue.Empty:pass
        if self.running:
            self.timing.configure(text=_clock(time.monotonic()-self.started))
            self.spin=(self.spin+1)%40
            if self.spin%10==0:
                self.status.configure(text=SPIN[self.spin//10]+'  '+self.status.cget('text').lstrip(SPIN+' '))
        self.root.after(100,self.poll)
    def open_result(self,key):
        if self.result:os.startfile(self.result[key])
    def close(self):
        if self.dialog: return
        if self.running:
            key=self._dialog('A conversion is still running','Closing stops it. Files already converted are kept; '
                             'run the same folder again later to continue.',[('keep','Keep converting'),('close','Close anyway')],'keep')
            if key!='close': return
            if self.running:
                if not self.cancel.is_set(): self._stop()
                self.root.after(200,self.close_when_stopped); return
        self.root.destroy()
    def close_when_stopped(self):
        if self.running:self.root.after(200,self.close_when_stopped)
        else:self.root.destroy()

def main():
    root=tk.Tk(); App(root); root.mainloop()
