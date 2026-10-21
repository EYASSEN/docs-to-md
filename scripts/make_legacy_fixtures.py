# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build-time only. Convert OUR synthetic DOCX/PPTX into binary regression fixtures.
The application uses AppContainer for inputs; this fixture generator has no user inputs."""
from pathlib import Path
import os,shutil,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from foldertomd.runtime import JobProcess
PROFILE='''<?xml version="1.0" encoding="UTF-8"?><oor:items xmlns:oor="http://openoffice.org/2001/registry"><item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop><prop oor:name="DisableMacrosExecution" oor:op="fuse"><value>true</value></prop></item></oor:items>'''

def main():
    output=ROOT/'tests'/'fixtures'/'legacy';output.mkdir(parents=True,exist_ok=True)
    work=ROOT/'test-work'/'legacy-fixture-build';work.mkdir(exist_ok=True)
    profile=work/'profile';(profile/'user').mkdir(parents=True,exist_ok=True);(profile/'user'/'registrymodifications.xcu').write_text(PROFILE,encoding='utf-8')
    for filename,fmt,target in [('same.docx','doc:MS Word 97','legacy.doc'),('slides.pptx','ppt:MS PowerPoint 97','legacy.ppt')]:
        inp=ROOT/'test-work'/'corpus-v2'/filename
        assert inp.is_file()
        cmd=[str(ROOT/'vendor'/'libreoffice'/'program'/'soffice.com'),'-env:UserInstallation='+profile.as_uri(),'--headless','--nologo','--nodefault','--norestore','--nofirststartwizard','--convert-to',fmt,'--outdir',str(output),str(inp)]
        with (work/(target+'.log')).open('wb') as log:
            process=JobProcess(cmd,stdout=log,stderr=log)
            try:code=process.process.wait(timeout=60)
            except subprocess.TimeoutExpired:process.stop();raise
            finally:process.close()
        if code:raise RuntimeError('Fixture generation failed '+str(code))
        generated=output/(Path(filename).stem+'.'+fmt.split(':')[0]);generated.replace(output/target)
        print('Created',target,flush=True)

if __name__=='__main__':main()
