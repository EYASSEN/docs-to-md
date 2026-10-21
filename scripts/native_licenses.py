# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build-only acquisition of native OCR copyright and license notices."""
from pathlib import Path
import concurrent.futures,hashlib,json,urllib.request
ROOT=Path(__file__).resolve().parents[1]
FILES={
 'libarchive':'libarchive/libarchive/v3.7.7/COPYING',
 'libb2':'BLAKE2/libb2/master/COPYING',
 'brotli':'google/brotli/v1.1.0/LICENSE',
 'bzip2':'libarchive/bzip2/bzip2-1.0.8/LICENSE',
 'openssl':'openssl/openssl/openssl-3.4.0/LICENSE.txt',
 'curl':'curl/curl/curl-8_11_0/COPYING',
 'libdeflate':'ebiggers/libdeflate/v1.22/COPYING',
 'expat':'libexpat/libexpat/R_2_6_4/expat/COPYING',
 'gcc-GPL3':'gcc-mirror/gcc/releases/gcc-14.2.0/COPYING3',
 'gcc-runtime-exception':'gcc-mirror/gcc/releases/gcc-14.2.0/COPYING.RUNTIME',
 'giflib':'mirrorer/giflib/master/COPYING',
 'libiconv-LGPL':'arthenica/libiconv/master/COPYING.LIB',
 'libidn2':'libidn/libidn2/master/COPYING',
 'gettext':'autotools-mirror/gettext/master/COPYING',
 'jbig-GPL2':'gcc-mirror/gcc/master/COPYING',
 'libjpeg-turbo':'libjpeg-turbo/libjpeg-turbo/3.0.4/LICENSE.md',
 'libjpeg-BSD':'libjpeg-turbo/libjpeg-turbo/3.0.4/README.ijg',
 'leptonica':'DanBloomberg/leptonica/1.85.0/leptonica-license.txt',
 'lerc':'Esri/lerc/v4.0.0/LICENSE',
 'lz4':'lz4/lz4/v1.10.0/lib/LICENSE',
 'xz':'tukaani-project/xz/v5.6.3/COPYING',
 'openjpeg':'uclouvain/openjpeg/v2.5.2/LICENSE',
 'libpng':'pnggroup/libpng/v1.6.44/LICENSE',
 'libpsl':'rockdaboot/libpsl/0.21.5/COPYING',
 'libssh2':'libssh2/libssh2/libssh2-1.11.0/COPYING',
 'libtiff':'libsdl-org/libtiff/v4.7.0/LICENSE.md',
 'libunistring':'gnosis/libunistring/master/COPYING.LIB',
 'libwebp':'webmproject/libwebp/v1.4.0/COPYING',
 'libwebp-patents':'webmproject/libwebp/v1.4.0/PATENTS',
 'winpthreads':'mingw-w64/mingw-w64/v12.0.0/mingw-w64-libraries/winpthreads/COPYING',
 'zstd-BSD':'facebook/zstd/v1.5.6/LICENSE',
 'zstd-GPL2':'facebook/zstd/v1.5.6/COPYING',
 'zlib':'madler/zlib/v1.3.1/LICENSE',
}

def main():
    dest=ROOT/'licenses'/'native';dest.mkdir(parents=True,exist_ok=True)
    lockfile=dest/'sources.json';lock=json.loads(lockfile.read_text()) if lockfile.exists() else {}
    def fetch(item):
        name,path=item;p=dest/(name+'.txt');url='https://raw.githubusercontent.com/'+path
        try:
            if not p.exists():p.write_bytes(urllib.request.urlopen(url,timeout=30).read())
            sha=hashlib.sha256(p.read_bytes()).hexdigest()
            if lock.get(name,{}).get('sha256') and lock[name]['sha256']!=sha:raise RuntimeError('License checksum mismatch')
            return name,{'url':url,'sha256':sha}
        except Exception as e:return name,{'error':str(e),'url':url}
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        for name,value in pool.map(fetch,FILES.items()):lock[name]=value;print(name,'OK' if 'sha256'in value else value['error'],flush=True)
    lockfile.write_text(json.dumps(lock,indent=2),encoding='utf-8')
    if any('error' in r for r in lock.values()):raise RuntimeError('Some license downloads failed; inspect licenses/native/sources.json')

if __name__=='__main__':main()
