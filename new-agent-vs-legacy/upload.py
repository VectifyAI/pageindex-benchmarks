"""Put Financial QA's 40 filings (../financial-qa/corpus/pdfs/) into a PageIndex Cloud collection, created if
missing, wait until each is indexed, and record the collection in data/collection.json, which run.py checks before
a run. A filing already in the collection is not sent again. PageIndex bills indexing once per document.

    python3 upload.py [COLLECTION]      # default: financial-qa

Needs PAGEINDEX_API_KEY in the environment.
"""
import datetime
import hashlib
import json
import os
import pathlib
import sys

from pageindex import PageIndexClient

HERE = pathlib.Path(__file__).resolve().parent
CORPUS = HERE.parent / "financial-qa" / "corpus"
NAME = sys.argv[1] if len(sys.argv) > 1 else "financial-qa"


def documents(client, cid):
    out, offset = [], 0
    while True:
        page = client.list_documents(limit=100, offset=offset, collection_id=cid)
        docs = page.get("documents", [])
        out, offset = out + docs, offset + len(docs)
        if not docs or offset >= page.get("total", offset):
            return out


def main():
    client = PageIndexClient(api_key=os.environ["PAGEINDEX_API_KEY"])
    manifest = json.loads((CORPUS / "manifest.json").read_text())
    found = [c for c in client.list_collections()["collections"] if c["name"] == NAME]
    cid = found[0]["id"] if found else client.create_collection(NAME)["collection"]["id"]
    have = {d["name"] for d in documents(client, cid)}
    sent = []
    for m in manifest:
        pdf = CORPUS / "pdfs" / m["file"]
        assert hashlib.sha256(pdf.read_bytes()).hexdigest() == m["sha256"], f"{m['file']}: checksum"
        if m["file"] not in have:
            sent.append(client.submit_document(str(pdf), collection_id=cid)["doc_id"])
            print(f"submitted {m['file']}")
    for doc_id in sent:
        client.wait_document(doc_id)
    docs = {d["name"]: d for d in documents(client, cid)}
    # the cloud renames a file whose name the account already has elsewhere (NAME_1.pdf): use a fresh account
    files = {m["file"] for m in manifest}
    assert set(docs) == files, f"collection {NAME}: {sorted(set(docs) ^ files)}"
    record = {"collection": NAME, "collection_id": cid,
              "checked": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "documents": [{"file": m["file"], "sha256": m["sha256"], "pages": m["pages"],
                             **{k: docs[m["file"]][k] for k in ("id", "name", "pageNum", "status")}} for m in manifest]}
    (HERE / "data" / "collection.json").write_text(json.dumps(record, indent=1) + "\n")
    print(f"{len(docs)} documents, {sum(d['pageNum'] for d in docs.values())} pages in {NAME}")
    assert all(d["status"] == "completed" for d in docs.values()), "a document did not complete indexing"


if __name__ == "__main__":
    main()
