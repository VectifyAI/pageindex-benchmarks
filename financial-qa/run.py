"""Answer the 100 questions with one configuration, through PageIndex and OpenRouter.

    python3 run.py preflight CONFIG        # check the route, the price and the reasoning setting; answer requires it
    python3 run.py answer CONFIG RUN       # one run: every question, then those that ran out of turns asked again
    python3 run.py batch CONFIGS RUNS      # e.g. batch kimi-k3-max,glm-5.3-max 1,2,3: every run at once
    python3 run.py generations CONFIG RUN  # fetch OpenRouter's records of a run's calls still missing

CONFIG is a key of models.CONFIGS. Needs OPENROUTER_API_KEY in the environment. Rows are appended as they finish,
so an interrupted run resumes where it stopped.
"""
import asyncio
import hashlib
import http.client
import importlib.metadata
import json
import logging
import os
import pathlib
import random
import secrets
import subprocess
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import litellm
import litellm.integrations.custom_logger

from models import CONFIGS

HERE = pathlib.Path(__file__).resolve().parent
DATA, QUESTIONS, LIBRARY = HERE / "data", HERE / "questions" / "questions.json", HERE / "library-w70"
WORKERS = int(os.environ.get("WORKERS", 8))  # questions answered at once in a run; data/runs.jsonl records it
MAX_TURNS = 20
# a question that runs out of MAX_TURNS is asked once more, from the start, with this many: the limit is the
# harness's, not the model's. At it, or at the context window, the answer stays wrong (METHOD.md)
REASK_TURNS = 100
REFERENCE = "Request reference: {}"

litellm.suppress_debug_info = True
for name in ("LiteLLM", "asyncio"):  # LiteLLM's logging worker complains under threads; calls are unaffected
    logging.getLogger(name).setLevel(logging.CRITICAL)


def transient(exc):
    """A provider or account error that passes: rate limits, 5xx, dropped connections, timeouts, OpenRouter's
    in-flight credit check."""
    status = getattr(exc, "status_code", None)
    return (isinstance(exc, (litellm.RateLimitError, litellm.ServiceUnavailableError, litellm.InternalServerError,
                             litellm.APIConnectionError, litellm.Timeout))
            or (isinstance(status, int) and (status == 429 or status >= 500))
            or "in-flight requests" in str(exc))


CALL_RETRIES = 8
# OpenRouter's in-flight credit check refuses a call before it runs, so waiting costs nothing, while giving up
# throws away the question's earlier turns, which were billed
IN_FLIGHT_WAIT = 1800


def with_call_retries(acompletion):
    """Sends a model call again, unchanged, after a transient error, so the agent carries on with its question
    instead of the whole question starting over. The SDK calls litellm.acompletion with LiteLLM's own retries off.
    Waits 5 s doubling to 60 s, with jitter; up to 8 attempts, or for up to IN_FLIGHT_WAIT seconds while the
    in-flight credit check refuses the call."""
    async def call(*args, **kwargs):
        started, attempt = time.time(), 0
        while True:
            try:
                return await acompletion(*args, **kwargs)
            except Exception as exc:
                attempt += 1
                waiting = "in-flight requests" in str(exc) and time.time() - started < IN_FLIGHT_WAIT
                if not transient(exc) or (attempt >= CALL_RETRIES and not waiting):
                    raise
                await asyncio.sleep(min(60, 5 * 2 ** min(attempt - 1, 4)) * random.uniform(1, 1.5))
    return call


litellm.acompletion = with_call_retries(litellm.acompletion)


def extra_body(key):
    """The provider pinned with no fallbacks, OpenRouter's per-call cost returned, and the reasoning effort if one
    is set (as reasoning.effort: LiteLLM rewrites a top-level reasoning_effort="max" to "xhigh")."""
    *_, provider, _, effort = CONFIGS[key]
    body = {"provider": {"order": [provider], "allow_fallbacks": False}, "usage": {"include": True}}
    if effort:
        body["reasoning"] = {"effort": effort}
    if provider == "Anthropic":
        # the SDK marks Claude prompts for caching only on direct Anthropic routes; ask OpenRouter for it
        body["cache_control"] = {"type": "ephemeral"}
    return body


def read(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def unprocessed(row):
    """An answer row with no answer and no prompt tokens: the provider returned an empty response without
    processing the request. Not the model's answer, so the question is asked again, as after any provider error."""
    return not (row.get("answer") or "").strip() and row.get("input_tokens") == 0


def cut_off(answers, calls):
    """Questions whose standing answer is empty because the provider cut the response off mid-stream (the attempt's
    last call produced tokens yet was not billed), or because its last call came back empty without being processed
    (no tokens and no upstream cost). Not the model's answer, so they are asked again. A model's malformed tool
    call also produces no tokens, but OpenRouter bills it with an upstream cost of 0: it stays a wrong answer."""
    standing = {r["id"]: r for r in read(answers)}
    last = {}
    for c in read(calls):
        r = standing.get(c.get("id"))
        if c.get("ok") and r and c["start"] >= r["started"] and c["start"] >= last.get(c["id"], {}).get("start", 0):
            last[c["id"]] = c
    return {i for i, r in standing.items() if not (r.get("answer") or "").strip() and "error" not in r
            and not r.get("max_turns") and not r.get("model_error") and not r.get("context_limit") and i in last
            and last[i]["cost"] == 0
            and (last[i]["completion_tokens"] > 0 or (last[i]["prompt_tokens"] == 0 and last[i].get("cost_details") is None))}


def collect(path, items, work, redo=(), counts=lambda row: True):
    rows = read(path)
    done = {r["id"] for r in rows if counts(r) and "error" not in r and not unprocessed(r) and r["id"] not in redo}
    todo = [q for q in items if q["id"] not in done]
    lock = threading.Lock()
    path.parent.mkdir(parents=True, exist_ok=True)

    def one(q):
        row = work(q)
        with lock, path.open("a") as f:
            f.write(json.dumps(row) + "\n")
        return "error" in row or unprocessed(row)

    with ThreadPoolExecutor(WORKERS) as pool:
        errors = sum(pool.map(one, todo))
    print(f"{path.relative_to(HERE)}: {len(todo)} new, {errors} errors")
    return errors


def run_reference(path, run):
    """The line sent with every question of a run, so that a run never reuses another run's prompt cache. A resumed
    run keeps the reference its first rows carry."""
    return next((r["ref"] for r in read(path) if r.get("ref")), f"r{run}-{secrets.token_hex(4)}")


class CallLog(litellm.integrations.custom_logger.CustomLogger):
    """Writes one row per model call of a run (data/calls/) and sums what OpenRouter charged for data/runs.jsonl. A
    call is matched to its question by the question text and to its run by the reference line; a call without them
    is still logged and billed, with id or ref None."""

    def __init__(self, path, ref, items):
        self.path, self.ref, self.lock = path, ref, threading.Lock()
        self.questions = {q["question"]: q["id"] for q in items}
        self.reset()
        path.parent.mkdir(parents=True, exist_ok=True)

    def reset(self):
        self.calls, self.usd, self.tokens = 0, 0.0, [0, 0, 0]

    def _context(self, kwargs):
        msgs = kwargs.get("messages") or []
        system = " ".join(str(m.get("content")) for m in msgs if m.get("role") in ("system", "developer"))
        user = next((str(m.get("content")) for m in msgs if m.get("role") == "user"), "")
        tool_chars = 0
        for m in reversed(msgs):  # tool results added since the model's previous turn
            if m.get("role") != "tool":
                break
            tool_chars += len(str(m.get("content")))
        return {"ref": self.ref if REFERENCE.format(self.ref) in system else None,
                "id": next((i for text, i in self.questions.items() if text in user), None),
                "turn": sum(m.get("role") == "assistant" for m in msgs) + 1, "n_messages": len(msgs),
                "new_tool_chars": tool_chars}

    def _write(self, row):
        with self.lock, self.path.open("a") as f:
            f.write(json.dumps(row) + "\n")

    def log_success_event(self, kwargs, response_obj, start_time, end_time):
        context = self._context(kwargs)
        r = response_obj.model_dump() if hasattr(response_obj, "model_dump") else {}
        usage = r.get("usage") or {}
        prompt_details = usage.get("prompt_tokens_details") or {}
        choice = (r.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        first_token = (kwargs.get("standard_logging_object") or {}).get("completionStartTime")
        row = {**context, "ok": True, "gen_id": r.get("id"), "provider": r.get("provider"), "served_model": r.get("model"),
               "start": start_time.timestamp(), "end": end_time.timestamp(),
               "seconds": round((end_time - start_time).total_seconds(), 3),
               "ttft": round(first_token - start_time.timestamp(), 3) if isinstance(first_token, float) else None,
               "prompt_tokens": usage.get("prompt_tokens") or 0, "cached_tokens": prompt_details.get("cached_tokens") or 0,
               "cache_write_tokens": prompt_details.get("cache_write_tokens") or 0,
               "completion_tokens": usage.get("completion_tokens") or 0,
               "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0,
               "cost": usage.get("cost") or 0, "cost_details": usage.get("cost_details"),
               "finish_reason": choice.get("finish_reason"),
               "tool_calls": [{"name": t["function"]["name"], "args": t["function"]["arguments"]}
                              for t in message.get("tool_calls") or []],
               "content": message.get("content") or ""}
        with self.lock:
            self.calls += 1
            self.usd += row["cost"]
            self.tokens = [a + b for a, b in zip(self.tokens, (row["prompt_tokens"], row["cached_tokens"],
                                                                row["completion_tokens"]))]
        self._write(row)

    def log_failure_event(self, kwargs, response_obj, start_time, end_time):
        self._write({**self._context(kwargs), "ok": False, "start": start_time.timestamp(),
                     "end": end_time.timestamp(), "error": str(kwargs.get("exception"))[:300]})

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        self.log_success_event(kwargs, response_obj, start_time, end_time)

    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
        self.log_failure_event(kwargs, response_obj, start_time, end_time)


EFFORT_PROBE = ("How many ordered pairs (a, b) of integers with 1 <= a <= 60 and 1 <= b <= 60 satisfy "
                "a^2 + b^2 divisible by 13? Reply with only the number.")


def price_at(pricing, when):
    """USD per token (input, cache read, output) on an endpoint at a moment: its base prices, or the time-of-day
    override in force. Long-context tiers do not apply to the short probe prompts this is used for."""
    day, hhmm = time.strftime("%A", time.gmtime(when)).lower(), int(time.strftime("%H%M", time.gmtime(when)))
    for o in pricing.get("overrides") or []:
        start, end = o.get("utc_start"), o.get("utc_end")
        if day in o.get("utc_days", []) and (start is None or start <= hhmm < (end or 2400)):
            pricing = {**pricing, **o}
    return tuple(float(pricing.get(k) or pricing.get("prompt") or 0) for k in ("prompt", "input_cache_read", "completion"))


def preflight(key, repeats=4):
    """Checks a configuration before its runs and writes data/preflight/<key>.json, which answer() requires to have
    passed:
    - the pinned provider serves the model with tool calls, and answers every probe call;
    - every probe call is billed at that provider's standard-tier price, the endpoint with the plainest tag (not
      flex, fast or priority): a lower bill means a cheaper tier or provider served it;
    - a level set is one the model lists;
    - the model reasons under the settings answer() sends.
    It also records OpenRouter's declared default level and the reasoning tokens on one prompt with nothing sent
    and at each listed level."""
    _, _, model, provider, _, effort = CONFIGS[key]
    with urllib.request.urlopen("https://openrouter.ai/api/v1/models") as r:
        info = next(m for m in json.load(r)["data"] if m["id"] == model)
    with urllib.request.urlopen(f"https://openrouter.ai/api/v1/models/{model}/endpoints") as r:
        endpoint = min((e for e in json.load(r)["data"]["endpoints"] if e["provider_name"].lower() == provider.lower()),
                       key=lambda e: len((e.get("tag") or "").split("/")), default=None)
    levels = (info.get("reasoning") or {}).get("supported_efforts") or []
    base = {k: v for k, v in extra_body(key).items() if k != "reasoning"}
    settings = [None, *levels]

    def call(setting):
        sent_at = time.time()
        # LiteLLM's default timeout is 6,000 s; a stalled probe call should fail sooner
        r = litellm.completion(model=f"openrouter/{model}", num_retries=3, timeout=600,
                               extra_body=base | ({"reasoning": {"effort": setting}} if setting else {}),
                               messages=[{"role": "user", "content": EFFORT_PROBE}]).model_dump()
        usage = r.get("usage") or {}
        cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
        rate = price_at(endpoint["pricing"], sent_at) if endpoint else (0, 0, 0)
        expected = ((usage.get("prompt_tokens") or 0) - cached) * rate[0] + cached * rate[1] + (usage.get("completion_tokens") or 0) * rate[2]
        return {"setting": setting, "gen_id": r.get("id"), "provider": r.get("provider"), "cost": usage.get("cost") or 0,
                "standard_price_cost": expected,
                "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0}

    with ThreadPoolExecutor(8) as pool:
        calls = list(pool.map(call, [s for s in settings for _ in range(repeats)]))
    medians = {str(s): sorted(c["reasoning_tokens"] for c in calls if c["setting"] == s)[repeats // 2] for s in settings}
    # billed / standard-tier price per call; up to 1.3 allows a first cache write, which costs more than input
    ratios = sorted(c["cost"] / c["standard_price_cost"] for c in calls if c["standard_price_cost"])
    checks = [(endpoint is not None, f"{provider} does not serve {model}"),
              (endpoint is None or "tools" in endpoint.get("supported_parameters", []), f"{provider} has no tool calls"),
              (all((c["provider"] or "").lower() == provider.lower() for c in calls), "a call was served by another provider"),
              (ratios and 0.97 <= ratios[0] and ratios[-1] <= 1.3,
               f"billed / standard price ran {ratios[0] if ratios else 0:.2f}-{ratios[-1] if ratios else 0:.2f}, not 0.97-1.3"),
              (effort is None or effort in levels, f"level {effort!r} is not one of {levels}"),
              (medians.get(str(effort), 0) > 0 or not info.get("reasoning"), "no reasoning with the settings answer() sends")]
    failures = [message for ok, message in checks if not ok]
    result = {"model": key, "route": model, "provider": provider, "reasoning_setting": effort,
              "checked": time.strftime("%Y-%m-%d %H:%M:%S %z"), "openrouter_reasoning": info.get("reasoning"),
              "declared_default": (info.get("reasoning") or {}).get("default_effort"),
              "pricing": info.get("pricing"), "endpoint_tag": (endpoint or {}).get("tag"),
              "endpoint_pricing": (endpoint or {}).get("pricing"),
              "billed_over_standard": [round(ratios[0], 3), round(ratios[-1], 3)] if ratios else None,
              "reasoning_tokens_median": medians, "calls": calls, "cost": round(sum(c["cost"] for c in calls), 6),
              "passed": not failures, "failures": failures}
    out = DATA / "preflight" / f"{key}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps({k: result[k] for k in ("reasoning_setting", "declared_default", "endpoint_tag", "billed_over_standard",
                                              "reasoning_tokens_median", "cost", "passed", "failures")}))


def preflight_passed(key):
    check = DATA / "preflight" / f"{key}.json"
    return check.exists() and json.loads(check.read_text())["passed"]


def environment(max_turns):
    """What a run's answers depend on besides the configuration; runs compared or added later must share it."""
    library = hashlib.sha256()
    for p in sorted(p for p in LIBRARY.rglob("*") if p.is_file() and p.name != ".lock"):
        library.update(p.relative_to(LIBRARY).as_posix().encode() + b"\0" + p.read_bytes())
    return {"pageindex": importlib.metadata.version("pageindex"), "litellm": importlib.metadata.version("litellm"),
            "max_turns": max_turns, "reference": REFERENCE,
            "questions_sha256": hashlib.sha256(QUESTIONS.read_bytes()).hexdigest(),
            "library": LIBRARY.name, "library_sha256": library.hexdigest()}


def model_fault(exc):
    """Whether the model itself broke the run: the agent library's ModelBehaviorError (a call to a tool that does
    not exist, tool input that is not JSON, ...) or ModelRefusalError, which the SDK reports as "The agent backend
    failed" and chains as the cause. A user would get no answer either, so the question is graded wrong rather
    than asked again; provider and account errors are retried."""
    from agents.exceptions import ModelBehaviorError, ModelRefusalError
    for _ in range(10):  # the cause chain is short; a cap guards against a cycle
        if exc is None:
            return False
        if isinstance(exc, (ModelBehaviorError, ModelRefusalError)):
            return True
        exc = exc.__cause__ or exc.__context__
    return False


def context_overflow(exc):
    """The conversation outgrew the model's context window: the model's own limit, so the answer stands as wrong
    and is not asked again, as each retry would run the same long conversation."""
    text = str(exc).lower()
    return any(s in text for s in ("maximum context length", "context_length_exceeded", "context length",
                                   "context window", "prompt is too long", "input is too long"))


def capped(path):
    """Questions of a run that ran out of MAX_TURNS and have not yet been answered again with REASK_TURNS."""
    rows = read(path)
    asked_again = {r["id"] for r in rows if r.get("max_turns_limit") and "error" not in r}
    return sorted({r["id"] for r in rows if r.get("max_turns") and not r.get("max_turns_limit")} - asked_again)


RETRY_PAUSES = (60, 180, 420)  # seconds before each re-try of the questions that ended in an error


def answer(key, run):
    """One run of the questions with MAX_TURNS each, then the questions that ran out of turns asked again, from the
    start, with REASK_TURNS; those rows stand in place of the earlier ones (grade.py answer_rows). Each pass
    writes a line to data/runs.jsonl."""
    from pageindex import PageIndexClient

    if not preflight_passed(key):
        sys.exit(f"data/preflight/{key}.json missing or failed: run `python3 run.py preflight {key}` first")
    _, _, model, provider, _, effort = CONFIGS[key]
    client = PageIndexClient(index_model="openrouter/openai/gpt-6-luna", chat_model=f"openrouter/{model}",
                             storage_path=str(LIBRARY))
    questions = json.loads(QUESTIONS.read_text())
    path, calls_path = DATA / "answers" / f"{key}_run{run}.jsonl", DATA / "calls" / f"{key}_run{run}.jsonl"
    ref = run_reference(path, run)
    log = CallLog(calls_path, ref, questions)
    litellm.callbacks = [log]

    def one_pass(items, turns):
        def work(q):
            started = time.time()
            row = {"id": q["id"], "model": key, "run": run, "route": model, "ref": ref, "started": round(started, 3)}
            if turns == REASK_TURNS:
                row["max_turns_limit"] = turns
            try:
                r = client.chat(q["question"], doc_id=None, protocol="chat_completions", max_turns=turns,
                                extra_body=extra_body(key), instructions=REFERENCE.format(ref))
            except Exception as exc:
                row = {**row, "seconds": round(time.time() - started, 1)}
                if "did not finish within max_turns" in str(exc):
                    return {**row, "answer": None, "max_turns": True}  # a result, graded wrong; asked again below
                if context_overflow(exc):  # a result, graded wrong; not retried
                    return {**row, "answer": None, "context_limit": f"{type(exc).__name__}: {exc}"[:500]}
                if model_fault(exc):  # a result, graded wrong; not retried, its cost counted
                    return {**row, "answer": None, "model_error": f"{type(exc).__name__}: {exc}"[:500]}
                return {**row, "error": f"{type(exc).__name__}: {exc}"[:500]}
            usage = r["usage"]
            details = usage.get("prompt_tokens_details") or {}
            return {**row, "answer": r["choices"][0]["message"]["content"], "seconds": round(time.time() - started, 1),
                    "input_tokens": usage["prompt_tokens"], "cached_tokens": details.get("cached_tokens") or 0,
                    "output_tokens": usage["completion_tokens"], "usage": usage}

        # in the second pass only rows of asking again count as done, so its errors are retried as usual
        counts = (lambda row: row.get("max_turns_limit") == REASK_TURNS) if turns == REASK_TURNS else (lambda row: True)
        log.reset()
        started = time.time()
        redo = lambda: cut_off(path, calls_path) & {q["id"] for q in items}  # noqa: E731
        errors = collect(path, items, work, redo(), counts) + len(redo())
        for pause in RETRY_PAUSES:  # provider rate limits and outages pass; a question that keeps failing needs a look
            if not errors:
                break
            print(f"{errors} errors; retrying them in {pause} s")
            time.sleep(pause)
            errors = collect(path, items, work, redo(), counts) + len(redo())
        with (DATA / "runs.jsonl").open("a") as f:  # one line per pass; a resumed run adds lines
            f.write(json.dumps({"model": key, "run": run, "ref": ref, "calls": log.calls, "usd": round(log.usd, 6),
                                "prompt_tokens": log.tokens[0], "cached_tokens": log.tokens[1],
                                "output_tokens": log.tokens[2], "errors_left": errors, "route": model,
                                "provider": provider, "reasoning": effort, "workers": WORKERS,
                                "started": round(started, 3), "ended": round(time.time(), 3), "env": environment(turns),
                                **({"reask": sorted(q["id"] for q in items)} if turns == REASK_TURNS else {}),
                                "source": "OpenRouter usage.cost per call, summed by run.py"}) + "\n")
        print(f"billed ${log.usd:.4f} over {log.calls} calls" + (f"; {errors} questions still failing" if errors else ""))

    one_pass(questions, MAX_TURNS)
    if again := capped(path):
        print(f"{len(again)} questions ran out of {MAX_TURNS} turns; asking them again with up to {REASK_TURNS}")
        one_pass([q for q in questions if q["id"] in again], REASK_TURNS)
    generations(key, run)


def batch(keys, runs, procs=12):
    """answer() for every configuration x run at once, at most `procs` processes at a time (one answer() per process,
    as LiteLLM keeps a process's loggers registered). Each writes logs/<key>_run<N>.log. Calls of parallel runs are
    told apart by their reference, so costs stay exact."""
    if missing := [k for k in keys if not preflight_passed(k)]:
        sys.exit(f"no passed preflight for {missing}: run `python3 run.py preflight CONFIG` first")
    (HERE / "logs").mkdir(exist_ok=True)

    def one(job):
        key, r = job
        with (HERE / "logs" / f"{key}_run{r}.log").open("a") as log:
            return key, r, subprocess.run([sys.executable, __file__, "answer", key, str(r)], cwd=HERE,
                                          stdout=log, stderr=subprocess.STDOUT).returncode

    with ThreadPoolExecutor(procs) as pool:
        for key, r, code in pool.map(one, [(k, r) for r in runs for k in keys]):
            print(f"{key} run {r}: " + ("done" if code == 0 else f"exit {code}, see logs/{key}_run{r}.log"))


def generations(key, run):
    """Saves OpenRouter's own record of each logged call (/api/v1/generation: provider attempts, latency, native
    token counts, cost) next to the call log, less the account's workspace_id and app_id. Records show up a minute or
    two after the call; any still missing are fetched by `python3 run.py generations CONFIG RUN`."""
    calls, out = DATA / "calls" / f"{key}_run{run}.jsonl", DATA / "generations" / f"{key}_run{run}.jsonl"
    done = {g["id"] for g in read(out)}
    ids = [c["gen_id"] for c in read(calls) if c.get("gen_id") and c["gen_id"] not in done]
    headers = {"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"}

    def fetch(gen_id):
        for attempt in range(7):  # waits up to about two minutes in all
            try:
                with urllib.request.urlopen(urllib.request.Request(
                        f"https://openrouter.ai/api/v1/generation?id={gen_id}", headers=headers), timeout=60) as r:
                    record = json.load(r)["data"]
                return {k: v for k, v in record.items() if k not in ("workspace_id", "app_id")}
            except (OSError, http.client.HTTPException):  # not ready yet, or a dropped connection
                time.sleep(2 ** attempt)
        return None

    out.parent.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(4) as pool:
        records = list(pool.map(fetch, ids))
    with out.open("a") as f:
        for record in filter(None, records):
            f.write(json.dumps(record) + "\n")
    print(f"{out.relative_to(HERE)}: {sum(r is not None for r in records)} saved, {records.count(None)} not found yet")
    logged = {c["gen_id"]: c["cost"] for c in read(calls) if c.get("gen_id")}
    kept = {g["id"]: g["total_cost"] for g in read(out)}
    differ = [i for i in logged.keys() & kept.keys() if abs(logged[i] - kept[i]) > 1e-9]
    print(f"  logged ${sum(logged.values()):.6f} over {len(logged)} calls; OpenRouter's records "
          f"${sum(kept[i] for i in logged.keys() & kept.keys()):.6f} for {len(logged.keys() & kept.keys())} of them; "
          f"{len(differ)} differ, {len(logged.keys() - kept.keys())} missing")


if __name__ == "__main__":
    stage, key, *rest = sys.argv[1:] + [""] * (2 - len(sys.argv[1:]))
    keys = key.split(",")
    assert stage in ("preflight", "answer", "batch", "generations") and (stage == "preflight" or rest), __doc__
    assert set(keys) <= set(CONFIGS), f"CONFIG must be one of {list(CONFIGS)}"
    {"preflight": lambda: preflight(key), "answer": lambda: answer(key, int(rest[0])),
     "batch": lambda: batch(keys, tuple(map(int, rest[0].split(",")))),
     "generations": lambda: generations(key, int(rest[0]))}[stage]()
