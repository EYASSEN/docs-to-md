# OCR models (Cleanup17)

These ONNX files are used by foldertomd/ocrengine.py, offline. They are PaddleOCR models in the
ONNX form published by RapidOCR. Both projects are Apache-2.0 (LICENSE, MODEL_LICENSES.md).

| File | Source | Source SHA-256 | Change | File SHA-256 |
|---|---|---|---|---|
| det.onnx | PP-OCRv6_det_small.onnx in the RapidOCR 3.10.0 wheel (PyPI, rapidocr-3.10.0-py3-none-any.whl, 2fc34e26cd0f48514804a94f8832283039c7334076bff60768b1fed9ad068050) | 090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f | int8 dynamic quantization (QUInt8 weights) with ONNX Runtime 1.31.0 | d1de8192b9c8c0e68a4c341605604b76b7c18d15b0e6167624f49e1e484f7cdb |
| rec_en.onnx | PP-OCRv6_rec_small.onnx in the same wheel | 6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884 | none | 6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884 |
| rec_ar.onnx | arabic_PP-OCRv5_rec_mobile.onnx, https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/PP-OCRv5/rec/arabic_PP-OCRv5_rec_mobile.onnx | c1192e632d0baa9146ae5b756a0e635e3dc63c1733737ebfd1629e87144e9295 | int8 dynamic quantization (QUInt8 weights) with ONNX Runtime 1.31.0 | 26452270f1aee56b47cb3c4f805670da25483f714fef2aa7a0d5e03982657285 |

The quantized files are modified versions of the Apache-2.0 models: the weights were converted to
8-bit integers by `onnxruntime.quantization.quantize_dynamic(source, target, weight_type=QuantType.QUInt8)`.
scripts/make_ocr_models.py repeats the conversion and checks these hashes. Each recognition model
carries its character list in its ONNX metadata.

The detection and recognition pipeline in ocrengine.py follows RapidOCR 3.10.0 (Apache-2.0,
Copyright (c) 2021 RapidOCR Authors), rewritten without OpenCV.
