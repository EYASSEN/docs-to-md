# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Acquire the pinned, redistribution-ready JRE and Apache POI parser at build time."""
from pathlib import Path
import concurrent.futures,hashlib,json,shutil,subprocess,urllib.request,zipfile
ROOT=Path(__file__).resolve().parents[1];CACHE=ROOT/'build-cache';VENDOR=ROOT/'vendor'
ARTIFACTS=[('org.apache.poi','poi','5.4.1'),('org.apache.poi','poi-scratchpad','5.4.1'),('commons-codec','commons-codec','1.18.0'),('org.apache.commons','commons-collections4','4.4'),('org.apache.commons','commons-math3','3.6.1'),('commons-io','commons-io','2.18.0'),('com.zaxxer','SparseBitSet','1.3'),('org.apache.logging.log4j','log4j-api','2.24.3')]
URLS={f'{a}-{v}.jar':f'https://repo.maven.apache.org/maven2/{g.replace(".","/")}/{a}/{v}/{a}-{v}.jar' for g,a,v in ARTIFACTS}
URLS.update({'jre17.zip':'https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.18%2B8/OpenJDK17U-jre_x64_windows_hotspot_17.0.18_8.zip','ecj-3.40.0.jar':'https://repo.maven.apache.org/maven2/org/eclipse/jdt/ecj/3.40.0/ecj-3.40.0.jar'})

def main():
    lockpath=ROOT/'dependencies.lock.json';lock=json.loads(lockpath.read_text())
    def fetch(item):
        name,url=item;p=CACHE/name
        if not p.exists():
            print('Downloading',name,flush=True)
            with urllib.request.urlopen(url,timeout=180) as r,p.with_suffix('.part').open('wb') as w:shutil.copyfileobj(r,w)
            p.with_suffix('.part').replace(p)
        with p.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
        expected=lock.get(name,{}).get('sha256')
        if name=='jre17.zip':expected='95c9ebe3ee16baab7239531757513d9a03799ca06483ef2f3b530e81e93e7b5b'
        if expected and sha!=expected:raise RuntimeError('Dependency checksum mismatch: '+name)
        return name,{'url':url,'sha256':sha,'bytes':p.stat().st_size}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        for name,record in pool.map(fetch,URLS.items()):lock[name]=record;print('Verified',name,flush=True)
    lockpath.write_text(json.dumps(lock,indent=2),encoding='utf-8')
    jre=VENDOR/'jre'
    if not (jre/'bin'/'java.exe').exists():
        with zipfile.ZipFile(CACHE/'jre17.zip') as z:
            for info in z.infolist():
                parts=Path(info.filename).parts[1:]
                if not parts or info.is_dir():continue
                dest=jre.joinpath(*parts);dest.parent.mkdir(parents=True,exist_ok=True)
                with z.open(info) as r,dest.open('wb') as w:shutil.copyfileobj(r,w)
    jars=VENDOR/'poi';jars.mkdir(exist_ok=True)
    for _,a,v in ARTIFACTS:shutil.copy2(CACHE/f'{a}-{v}.jar',jars)
    classes=jars/'classes';classes.mkdir(exist_ok=True)
    subprocess.run([str(jre/'bin'/'java.exe'),'-jar',str(CACHE/'ecj-3.40.0.jar'),'-17','-encoding','UTF-8','-cp',';'.join(str(p) for p in jars.glob('*.jar')),'-d',str(classes),str(ROOT/'java'/'LegacyReader.java')],check=True)
    print('Offline legacy reader compiled',flush=True)

if __name__=='__main__':main()
