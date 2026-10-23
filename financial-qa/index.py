"""Build library-w70/, the PageIndex library every configuration answers from: the 40 filings in corpus/pdfs/
(corpus/fetch.py), indexed once with GPT-6 Luna, node summaries capped at 70 words, the SDK's other settings at
their defaults. The library is in the repo, and the runs record its hash: a rebuilt library has other trees and
summaries, so runs over it are not comparable with these.

    python3 index.py   # needs OPENROUTER_API_KEY; filings already in the library are skipped
"""
import pathlib
import time
from concurrent.futures import ThreadPoolExecutor

from pageindex import PageIndexClient

HERE = pathlib.Path(__file__).resolve().parent
# fewer simultaneous summary calls than the default 64, since four filings index at once
client = PageIndexClient(index_model="openrouter/openai/gpt-6-luna", storage_path=str(HERE / "library-w70"),
                         summary_concurrency=16, summary_max_words=70)


def index(pdf):
    try:
        return pdf.name, client.get_document_id(pdf.name), "already indexed"
    except Exception:
        started = time.time()
        doc_id = client.submit_document(str(pdf))["doc_id"]
        return pdf.name, doc_id, f"{time.time() - started:.0f}s"


if __name__ == "__main__":
    with ThreadPoolExecutor(4) as pool:
        for name, doc_id, note in pool.map(index, sorted((HERE / "corpus" / "pdfs").glob("*.pdf"))):
            print(f"{name}: {doc_id} ({note})", flush=True)
