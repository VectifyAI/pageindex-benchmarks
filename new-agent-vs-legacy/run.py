"""Answer Financial QA's 100 questions with one configuration on PageIndex v2: the agent of PageIndex 0.7.0 with
PageIndex Cloud's tools, over the filings in a cloud collection (upload.py), the model through OpenRouter as in
../financial-qa/run.py.

    python3 run.py preflight CONFIG        # as ../financial-qa/run.py: route, standard-tier price, reasoning
    python3 run.py answer CONFIG RUN       # one run: every question, up to 100 turns each
    python3 run.py generations CONFIG RUN  # fetch OpenRouter's records of a run's calls still missing

CONFIG is a key of ../financial-qa/models.py. Needs OPENROUTER_API_KEY and PAGEINDEX_API_KEY in the environment.
Writes data/ as ../financial-qa/run.py does; each answer row also counts the agent's tool calls and its PageIndex
search charges.
"""
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import pathlib
import re
import sys
import time

import litellm

HERE = pathlib.Path(__file__).resolve().parent
BENCH = HERE.parent / "financial-qa"  # its questions, configurations and run code
sys.path.append(str(BENCH))
from models import CONFIGS  # noqa: E402

_spec = importlib.util.spec_from_file_location("financial_qa_run", BENCH / "run.py")
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)  # ../financial-qa/run.py: call retries, logging, preflight, OpenRouter records
base.DATA = HERE / "data"

MAX_TURNS = base.REASK_TURNS  # 100 from the start, as for ../financial-qa/run.py's FIRST_TURNS
COLLECTION = HERE / "data" / "collection.json"
# PageIndex's list prices (pageindex.ai/pricing, 2026-11-16) for the agent's priced tools: USD per 1,000 pages
# (search_pages) or documents (search_documents) a call searches, for its first question and for each extra one.
# The tool's result says how many it searched ("Searched 93 page(s) ...", "Searched 40 document(s).")
SEARCH_PRICES = {"search_pages": (0.10, 0.02, r"Searched (\d+) page"),
                 "search_documents": (0.30, 0.10, r"Searched (\d+) document")}


def cloud_env(client):
    """The collection as the cloud has it at the start of a run, checked against data/collection.json, and the
    tool set and system prompt the agent gets. Goes into the run's line in data/runs.jsonl."""
    rec = json.loads(COLLECTION.read_text())
    docs = sorted((d["name"], d["id"], d["pageNum"], d["status"])
                  for d in client.list_documents(limit=100, collection_id=rec["collection_id"])["documents"])
    assert docs == sorted((d["name"], d["id"], d["pageNum"], d["status"]) for d in rec["documents"]), \
        f"collection {rec['collection']} differs from {COLLECTION.name}: run upload.py"
    return {"collection": rec["collection"], "collection_id": rec["collection_id"], "documents": len(docs),
            "pages": sum(d[2] for d in docs), "documents_sha256": hashlib.sha256(json.dumps(docs).encode()).hexdigest(),
            "tools": sorted(f.__name__ for f in client.agent_tools()),
            "instructions_sha256": hashlib.sha256(client.agent_instructions().encode()).hexdigest()}


def pictures(value):
    """Page images in a transcript: base64 data URLs, and the data of image blocks."""
    if isinstance(value, dict):
        image = (value.get("type") in ("image", "input_image")
                 or str(value.get("mimeType") or value.get("mime_type") or "").startswith("image/"))
        return sum(1 if isinstance(v, str) and len(v) > 2000 and (v.startswith("data:image") or (image and k == "data"))
                   else pictures(v) for k, v in value.items())
    if isinstance(value, list):
        return sum(pictures(v) for v in value)
    return int(isinstance(value, str) and value.startswith("data:image") and len(value) > 2000)


def tool_text(content):
    if isinstance(content, list):
        return "".join(b.get("text") or "" for b in content if isinstance(b, dict))
    return content if isinstance(content, str) else json.dumps(content)


def agent_record(messages):
    """For the answer row: each tool's number of calls, and each priced search with its charge at SEARCH_PRICES
    (the SDK reports no PageIndex charge, so it is computed from what the search result says it read)."""
    asked, tools, searches = {}, {}, []
    for m in messages:
        for t in (m.get("tool_calls") or []) if isinstance(m, dict) else []:
            name = (t.get("function") or {}).get("name") or t.get("name")
            asked[t.get("id")] = (name, (t.get("function") or {}).get("arguments"))
            tools[name] = tools.get(name, 0) + 1
    for m in messages:
        if not (isinstance(m, dict) and m.get("role") == "tool"):
            continue
        name, args = asked.get(m.get("tool_call_id"), (None, None))
        if name not in SEARCH_PRICES:
            continue
        first, extra, pattern = SEARCH_PRICES[name]
        try:
            questions = len(json.loads(args or "{}").get("questions") or [None])
        except ValueError:
            questions = 1
        found = re.search(pattern, tool_text(m.get("content")))
        units = int(found.group(1)) if found else None
        searches.append({"tool": name, "questions": questions, "read": units,
                         "usd": None if units is None else units / 1000 * (first + extra * (questions - 1))})
    return {"tools": tools, "searches": searches, "pageindex_usd": round(sum(s["usd"] or 0 for s in searches), 6),
            "pictures": pictures(messages)}


def environment(cloud):
    return {"pageindex": importlib.metadata.version("pageindex"), "litellm": importlib.metadata.version("litellm"),
            "max_turns": MAX_TURNS, "reference": base.REFERENCE,
            "questions_sha256": hashlib.sha256(base.QUESTIONS.read_bytes()).hexdigest(), "cloud": cloud}


def answer(key, run):
    """One run of the questions with up to MAX_TURNS each; errors retried as in ../financial-qa/run.py. Writes a line to
    data/runs.jsonl."""
    from pageindex import PageIndexClient

    if not base.preflight_passed(key):
        sys.exit(f"data/preflight/{key}.json missing or failed: run `python3 run.py preflight {key}` first")
    _, _, model, provider, _, effort = CONFIGS[key]
    client = PageIndexClient(api_key=os.environ["PAGEINDEX_API_KEY"], chat_model=f"openrouter/{model}")
    cloud = cloud_env(client)
    questions = json.loads(base.QUESTIONS.read_text())
    path, calls_path = base.DATA / "answers" / f"{key}_run{run}.jsonl", base.DATA / "calls" / f"{key}_run{run}.jsonl"
    ref = base.run_reference(path, run)
    log = base.CallLog(calls_path, ref, questions)
    litellm.callbacks = [log]

    def work(q):
        started = time.time()
        row = {"id": q["id"], "model": key, "run": run, "route": model, "ref": ref, "started": round(started, 3)}
        try:
            r = client.chat(q["question"], collection_id=cloud["collection_id"], protocol="chat_completions",
                            max_turns=MAX_TURNS, extra_body=base.extra_body(key),
                            instructions=base.REFERENCE.format(ref))
        except Exception as exc:
            row = {**row, "seconds": round(time.time() - started, 1)}
            if "did not finish within max_turns" in str(exc):
                return {**row, "answer": None, "max_turns": True}
            if base.context_overflow(exc):
                return {**row, "answer": None, "context_limit": f"{type(exc).__name__}: {exc}"[:500]}
            if base.model_fault(exc):
                return {**row, "answer": None, "model_error": f"{type(exc).__name__}: {exc}"[:500]}
            return {**row, "error": f"{type(exc).__name__}: {exc}"[:500]}
        usage = r["usage"]
        details = usage.get("prompt_tokens_details") or {}
        return {**row, "answer": r["choices"][0]["message"]["content"], "seconds": round(time.time() - started, 1),
                "input_tokens": usage["prompt_tokens"], "cached_tokens": details.get("cached_tokens") or 0,
                "output_tokens": usage["completion_tokens"], "usage": usage, **agent_record(r.get("messages") or [])}

    started = time.time()
    redo = lambda: base.cut_off(path, calls_path)  # noqa: E731
    errors = base.collect(path, questions, work, redo()) + len(redo())
    for pause in base.RETRY_PAUSES:
        if not errors:
            break
        print(f"{errors} errors; retrying them in {pause} s")
        time.sleep(pause)
        errors = base.collect(path, questions, work, redo()) + len(redo())
    with (base.DATA / "runs.jsonl").open("a") as f:
        f.write(json.dumps({"model": key, "run": run, "ref": ref, "calls": log.calls, "usd": round(log.usd, 6),
                            "prompt_tokens": log.tokens[0], "cached_tokens": log.tokens[1],
                            "output_tokens": log.tokens[2], "errors_left": errors, "route": model,
                            "provider": provider, "reasoning": effort, "workers": base.WORKERS,
                            "started": round(started, 3), "ended": round(time.time(), 3), "env": environment(cloud),
                            "source": "OpenRouter usage.cost per call, summed by run.py"}) + "\n")
    print(f"billed ${log.usd:.4f} over {log.calls} calls" + (f"; {errors} questions still failing" if errors else ""))
    base.generations(key, run)


if __name__ == "__main__":
    stage, key, *rest = sys.argv[1:] + [""] * (2 - len(sys.argv[1:]))
    assert stage in ("preflight", "answer", "generations") and (stage == "preflight" or rest), __doc__
    assert key in CONFIGS, f"CONFIG must be one of {list(CONFIGS)}"
    {"preflight": lambda: base.preflight(key), "answer": lambda: answer(key, int(rest[0])),
     "generations": lambda: base.generations(key, int(rest[0]))}[stage]()
