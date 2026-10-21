# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Rebuild ocr-models from the published sources (Cleanup17). Build-time only, needs
`pip install onnx==1.23.2 onnxruntime==1.31.0` and the two source files:
  rapidocr-3.10.0-py3-none-any.whl   (PyPI)
  arabic_PP-OCRv5_rec_mobile.onnx    (RapidOCR model list, ModelScope)
Usage: python scripts/make_ocr_models.py WHEEL ARABIC_ONNX OUTPUT_FOLDER"""
import hashlib, sys, tempfile, zipfile
from pathlib import Path

SOURCES = {'wheel': '2fc34e26cd0f48514804a94f8832283039c7334076bff60768b1fed9ad068050',
           'det': '090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f',
           'rec_en': '6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884',
           'arabic': 'c1192e632d0baa9146ae5b756a0e635e3dc63c1733737ebfd1629e87144e9295'}
RESULTS = {'det.onnx': 'd1de8192b9c8c0e68a4c341605604b76b7c18d15b0e6167624f49e1e484f7cdb',
           'rec_en.onnx': '6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884',
           'rec_ar.onnx': '26452270f1aee56b47cb3c4f805670da25483f714fef2aa7a0d5e03982657285'}

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main(wheel, arabic, out):
    from onnxruntime.quantization import quantize_dynamic, QuantType
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    assert digest(wheel) == SOURCES['wheel'], 'unexpected RapidOCR wheel'
    assert digest(arabic) == SOURCES['arabic'], 'unexpected Arabic model'
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(wheel) as z:
        det = Path(z.extract('rapidocr/models/PP-OCRv6_det_small.onnx', tmp))
        rec = Path(z.extract('rapidocr/models/PP-OCRv6_rec_small.onnx', tmp))
        assert digest(det) == SOURCES['det'] and digest(rec) == SOURCES['rec_en']
        quantize_dynamic(str(det), str(out / 'det.onnx'), weight_type=QuantType.QUInt8)
        (out / 'rec_en.onnx').write_bytes(rec.read_bytes())
    quantize_dynamic(str(arabic), str(out / 'rec_ar.onnx'), weight_type=QuantType.QUInt8)
    for name, expected in RESULTS.items():
        actual = digest(out / name)
        print(name, actual, 'OK' if actual == expected else 'DIFFERS (quantizer version?)')

if __name__ == '__main__':
    main(*sys.argv[1:4])
