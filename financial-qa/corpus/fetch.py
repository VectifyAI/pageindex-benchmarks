"""Download the corpus, 40 Form 10-K PDFs, into corpus/pdfs/ from the URLs in manifest.json (the PDF each company's
investor-relations site serves, exhibits included), and check each against SHA256SUMS. Only needed to rebuild the
library (index.py) or to read the evidence pages; the questions are answered from library-w70/.

    python3 corpus/fetch.py

JPMorgan's site refuses scripted downloads: save its five PDFs by hand from the filing pages the script lists.
"""
import hashlib
import json
import pathlib
import time
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
PDFS = HERE / "pdfs"
UA = {"User-Agent": "pageindex-benchmarks corpus download"}
MANUAL = "JPM_"  # Akamai answers scripts with 403


def download(url):
    for attempt in range(4):
        time.sleep(0.3 + 2 * attempt)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                return r.read()
        except OSError:
            if attempt == 3:
                raise


def main():
    PDFS.mkdir(exist_ok=True)
    sums = dict(line.split()[::-1] for line in (HERE / "SHA256SUMS").read_text().splitlines())
    missing = []
    for f in json.loads((HERE / "manifest.json").read_text()):
        pdf = PDFS / f["file"]
        if not pdf.exists():
            if f["file"].startswith(MANUAL):
                missing.append(f"  {f['file']}: open {f['ir_page']} and save the PDF as corpus/pdfs/{f['file']}")
                continue
            pdf.write_bytes(download(f["url"]))
        assert hashlib.sha256(pdf.read_bytes()).hexdigest() == sums[f["file"]], f"{f['file']} differs from SHA256SUMS"
        print(f"{f['file']}: ok", flush=True)
    if missing:
        print("download by hand:\n" + "\n".join(missing))


if __name__ == "__main__":
    main()
