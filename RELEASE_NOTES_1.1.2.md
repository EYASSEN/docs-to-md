# Docs to MD 1.1.2 — revision 58

## Several files converted at the same time (Cleanup23)

Files used to be converted one after another. A scanned PDF already read its pages in parallel,
but a folder of many small files (Word, Excel, text PDFs, single images) kept one processor core
busy while the rest of the computer waited.

Now up to three light files run at the same time, each worker with a share of the cores:

- The job reads the same number of pages at once as before: all cores but one, at most six.
- The number of files at once is three at most, fewer on a computer with fewer cores or little
  free memory (about 1.5 GB is planned per worker). The report states it: "Files converted in
  parallel: up to N".
- A heavy file, a PDF of 15 pages or more with OCR on, waits until the files before it finish and
  then runs alone with the whole computer, exactly as before. Large scans are not slowed down.
- With OCR off every file is light.
- The progress panel follows the oldest running file; the others move the overall bar, and the
  file count shows how many are running at once.

The share limits how many pages a worker reads at once. The OCR engines keep their own thread
settings (Cleanup23c): an earlier build also limited the ONNX OCR engine's threads, and on a real
tender folder that changed one character in two files ("استبيانها،" read as "استبيانهاء"), because the
engine's arithmetic depends slightly on its thread count.

The Markdown, images, index and report contents are the same as converting one file at a time.
The converter revision stays 58. Because the program code changed, the next run of an existing
output folder converts its files again, as after any update.

Setting the environment variable `DOCSTOMD_PARALLEL_FILES=1` restores one file at a time.
