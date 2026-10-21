# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Dedicated binary Office reader. No Office process, recalculation, or macro engine."""
import base64,io,json,os,shutil,subprocess
from PIL import Image
from .runtime import resources,child_environment
from .render import text,table

def events(ctx,mode):
    root=resources();java=root/'jre'/'bin'/'java.exe';poi=root/'poi'
    if not java.is_file() or not (poi/'classes'/'LegacyReader.class').is_file():
        raise RuntimeError('Bundled legacy reader is missing. Extract the complete portable ZIP again.')
    temp=ctx.work/'legacy';temp.mkdir(exist_ok=True)
    source=temp/('input'+ctx.source.suffix);shutil.copyfile(ctx.source,source)
    result=temp/'events.jsonl';policy=temp/'offline.policy'
    def path(p):return str(p.resolve()).replace('\\','/')
    policy.write_text('''grant {
      permission java.util.PropertyPermission "*", "read,write";
      permission java.lang.RuntimePermission "accessDeclaredMembers";
      permission java.lang.RuntimePermission "getClassLoader";
      permission java.lang.RuntimePermission "getProtectionDomain";
      permission java.lang.RuntimePermission "accessSystemModules";
      permission java.lang.RuntimePermission "getenv.*";
      permission java.lang.RuntimePermission "getStackWalkerWithClassReference";
      permission java.lang.reflect.ReflectPermission "suppressAccessChecks";
      permission java.io.FilePermission "'''+path(root)+'''/-", "read";
      permission java.io.FilePermission "'''+path(temp)+'''/-", "read,write,delete";
    };''',encoding='utf-8')
    env={key:os.environ[key] for key in ('SystemRoot','WINDIR','SYSTEMDRIVE') if key in os.environ}
    env.update({'TEMP':str(temp),'TMP':str(temp),'USERPROFILE':str(temp),'APPDATA':str(temp),'LOCALAPPDATA':str(temp),'PATH':str(java.parent)})
    command=[str(java),'-Xmx512m','-Djava.awt.headless=true','-Djava.security.manager','-Djava.security.policy=='+policy.as_uri(),'-Dfile.encoding=UTF-8','-cp','classes;*','LegacyReader',source.as_uri(),result.as_uri(),mode]
    proc=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=str(poi),creationflags=0x08000000,env=env)
    if proc.returncode or not result.exists():
        error=proc.stderr.decode('utf-8','replace')
        import re
        classes=re.findall(r'(?:[A-Za-z_][A-Za-z0-9_]*\.)+[A-Za-z_][A-Za-z0-9_]*(?:Exception|Error)',error)
        raise RuntimeError('Legacy document could not be read (protected, corrupt, unsupported, or reader permission failure). '+', '.join(dict.fromkeys(classes)))
    with result.open(encoding='utf-8') as f:
        for line in f:yield json.loads(line)

def consume(ctx,mode):
    rows=[]
    for event in events(ctx,mode):
        kind=event['kind'];value=event.get('text','')
        if kind=='heading':ctx.write('### '+text(value)+'\n\n')
        elif kind=='slide':ctx.write('## Slide '+value+'\n\n');ctx.counts['slides']=int(value)
        elif kind=='text':ctx.write(text(value)+'\n\n')
        elif kind=='list':ctx.write('- '+text(value)+'\n\n')
        elif kind=='table_start':rows=[]
        elif kind=='row':rows.append(event['cells'])
        elif kind=='table_end':ctx.write(table(rows));rows=[]
        elif kind=='warning':ctx.warn(value)
        elif kind=='image':
            try:
                with Image.open(io.BytesIO(base64.b64decode(event['data']))) as image:ctx.image(image,'Legacy embedded image')
            except Exception:ctx.warn('Legacy embedded vector/image could not be rendered locally.')

def extract_legacy(ctx):
    ctx.stage('Reading legacy document contents')
    consume(ctx,ctx.source.suffix.lower().lstrip('.'))

def extract_xls_images(ctx): consume(ctx,'xls-images')
