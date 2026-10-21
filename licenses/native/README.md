# Native OCR dependencies

These are unmodified, separate DLLs from the Tesseract 5.5.0.20241111 Windows release.
`sources.json` records URLs and SHA-256 hashes for the accompanying license notices.
The build computes their actual PE import closure; the portable package includes only
that closure and Windows system APIs are listed in `licenses/ocr-native-imports.json`.

| Libraries | Source/build location | Terms |
|---|---|---|
| Tesseract 5.5.0 | https://github.com/tesseract-ocr/tesseract/tree/5.5.0 | Apache-2.0 |
| Leptonica 1.85.0 | https://github.com/DanBloomberg/leptonica/tree/1.85.0 | BSD-style |
| libarchive, libb2 | https://github.com/libarchive/libarchive ; https://github.com/BLAKE2/libb2 | BSD-style / CC0 |
| Brotli, bzip2, libdeflate, LZ4, XZ/liblzma, zstd, zlib | https://github.com/google/brotli ; https://sourceware.org/bzip2/ ; https://github.com/ebiggers/libdeflate ; https://github.com/lz4/lz4 ; https://github.com/tukaani-project/xz ; https://github.com/facebook/zstd ; https://github.com/madler/zlib | Respective permissive/dual licenses in the accompanying texts |
| OpenSSL, curl, libssh2, libpsl, expat | https://github.com/openssl/openssl ; https://github.com/curl/curl ; https://github.com/libssh2/libssh2 ; https://github.com/rockdaboot/libpsl ; https://github.com/libexpat/libexpat | Apache-2.0 / MIT-style / BSD-style |
| libiconv, libidn2, gettext/libintl, libunistring | https://www.gnu.org/software/libiconv/ ; https://www.gnu.org/software/libidn/ ; https://www.gnu.org/software/gettext/ ; https://www.gnu.org/software/libunistring/ | LGPL/GPL options; license texts included; DLLs are separately replaceable |
| GCC libgcc/libstdc++ | https://gcc.gnu.org/ ; https://github.com/gcc-mirror/gcc | GPL with GCC Runtime Library Exception |
| winpthreads | https://github.com/mingw-w64/mingw-w64 | MinGW-w64 winpthreads license |
| GIF, JPEG, PNG, TIFF, OpenJPEG, WebP, LERC | https://sourceforge.net/projects/giflib/ ; https://github.com/libjpeg-turbo/libjpeg-turbo ; https://github.com/pnggroup/libpng ; https://gitlab.com/libtiff/libtiff ; https://github.com/uclouvain/openjpeg ; https://github.com/webmproject/libwebp ; https://github.com/Esri/lerc | Respective codec licenses and copyright notices included |
| JBIG-KIT | https://www.cl.cam.ac.uk/~mgk25/jbigkit/ | GPL-2.0-or-later; accompanying GPL-2.0 text |

Windows dependency build recipes and source download references are available from
https://github.com/msys2/MINGW-packages. Tesseract's Windows release/build information is
at https://github.com/UB-Mannheim/tesseract/wiki and its upstream release page.
Exact shipped binary hashes are provided even where the upstream installer does not
include a complete machine-readable SBOM. A full binary-to-corresponding-source audit
of every transitive native component was not completed; treat that as a redistribution
review gate before a public release. This local deliverable includes upstream notices
and source/build links, not a claim of a completed legal review.
