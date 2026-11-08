"""Run ExtractBench through Page Extract's public API, and score each document with ExtractBench's own scorer.

    export PAGEINDEX_SEARCH_API_KEY=pis_live_...      # one key serves Page Search and Page Extract
    python run.py --bench ../ExtractBench --tier standard [--at-once 6] [--only stem,stem]

--bench is a checkout of https://github.com/run-llama/ExtractBench with its data downloaded
(`uv run extract-bench download`), which leaves <stem>.pdf and <stem>.test.json under data/short, data/medium and
data/long. For each document this:

  1. uploads the PDF to Page Search (an upload of a PDF already there returns the same document, at no cost),
  2. starts an extraction with the document's JSON Schema at the tier given, and waits for it,
  3. saves the job, as the API returns it, to data/<tier>/<split>/<stem>.job.json and its result to <stem>.json,
  4. scores the result with `extract-bench evaluation score_case`, to <stem>.score.json.

A document already scored is skipped, so a run can be stopped and started again. A job that fails is saved too and
scores zero, as the benchmark counts it.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
from pageindex_search import PageSearch

EXTRACT_URL = os.environ.get("PAGE_EXTRACT_URL", "https://api.extract.pageindex.ai/v1")
HERE = Path(__file__).resolve().parent
SPLITS = ("short", "medium", "long")
POLL = 5  # seconds between looks at a running job


def say(*parts):
    print(*parts, file=sys.stderr, flush=True)


def extract(http: httpx.Client, document: str, schema: dict, tier: str) -> dict:
    """Start an extraction and wait for it: the finished job, as the API returns it."""
    r = http.post("/extract", json={"document": document, "configuration": {"data_schema": schema, "tier": tier}})
    if r.status_code >= 400:
        raise RuntimeError(f"starting the extraction: {r.status_code} {r.text[:500]}")
    job = r.json()
    while job["status"] in ("PENDING", "RUNNING"):
        time.sleep(POLL)
        r = http.get(f"/extract/{job['id']}")
        if r.status_code >= 500:
            continue  # a passing error: look again
        r.raise_for_status()
        job = r.json()
    return job


def score(bench: Path, case: Path, pdf: Path, prediction: Path, out: Path) -> dict | None:
    r = subprocess.run(["uv", "run", "--project", str(bench), "extract-bench", "evaluation", "score_case", str(case),
                        str(prediction), "--source_file", str(pdf), "--output", str(out)],
                       capture_output=True, text=True, cwd=bench)
    if r.returncode:
        say(f"  scoring {case.name} failed:\n{r.stderr[-1500:]}")
        return None
    return json.loads(out.read_text())


def one(args, search: PageSearch, http: httpx.Client, split: str, case: Path):
    stem = case.name[: -len(".test.json")]
    out = HERE / "data" / args.tier / split
    out.mkdir(parents=True, exist_ok=True)
    scored = out / f"{stem}.score.json"
    if scored.exists():
        return
    pdf = case.with_name(stem + ".pdf")
    schema = json.loads(case.read_text())["data_schema"]
    try:
        doc = search.documents.upload(str(pdf))
        if doc.status != "ready":
            doc = search.documents.wait(doc)
        job = extract(http, doc.id, schema, args.tier)
    except Exception as e:  # noqa: BLE001 - a document that cannot run is left unscored; the rest go on
        say(f"== {split}/{stem}: could not run: {e!r}")
        return
    result = job.pop("extract_result", None)
    (out / f"{stem}.job.json").write_text(json.dumps(job, ensure_ascii=False, indent=1))
    prediction = out / f"{stem}.json"
    prediction.write_text(json.dumps(result if result is not None else {}, ensure_ascii=False, indent=1))
    s = score(args.bench, case, pdf, prediction, scored)
    f1 = ((s or {}).get("metrics") or {}).get("extract_unified_value_f1")
    say(f"== {split}/{stem}: {job['status'].lower()}, {job.get('usage', {}).get('pages', '?')} pages, "
        f"value F1 {'-' if f1 is None else f'{100 * f1:.2f}'}")


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--bench", type=Path, required=True, help="a checkout of ExtractBench, its data downloaded")
    p.add_argument("--tier", choices=("standard", "pro"), default="standard")
    p.add_argument("--at-once", type=int, default=6, help="documents in flight at once")
    p.add_argument("--only", help="comma-separated stems, to run only these")
    args = p.parse_args()
    args.bench = args.bench.resolve()
    key = os.environ["PAGEINDEX_SEARCH_API_KEY"]

    cases = [(split, c) for split in SPLITS for c in sorted((args.bench / "data" / split).glob("*.test.json"))]
    if args.only:
        wanted = set(args.only.split(","))
        cases = [(s, c) for s, c in cases if c.name[: -len(".test.json")] in wanted]
    if not cases:
        sys.exit(f"No cases under {args.bench / 'data'}: run `uv run extract-bench download` there first.")
    say(f"{len(cases)} documents, tier {args.tier}, {args.at_once} at once")

    search = PageSearch(key)
    with httpx.Client(base_url=EXTRACT_URL, headers={"Authorization": f"Bearer {key}"}, timeout=60) as http, \
            ThreadPoolExecutor(args.at_once) as pool:
        for f in [pool.submit(one, args, search, http, s, c) for s, c in cases]:
            f.result()


if __name__ == "__main__":
    main()
