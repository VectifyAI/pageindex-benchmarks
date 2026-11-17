"""The new PageIndex Agent (PageIndex 0.7.0 on PageIndex Cloud) against legacy PageIndex (0.4.4, ../financial-qa):
the same configurations on the same 100 questions. Accuracy from each one's grades, cost from each one's model calls
as ../financial-qa/results.py counts it, plus the new agent's PageIndex search charges.

    python3 compare.py      # -> results/results.md, and a chart per configuration, results/<config>.svg

The PNG is the SVG rendered by a headless browser, e.g.:
    google-chrome --headless --hide-scrollbars --window-size=1280,720 --force-device-scale-factor=2 \
        --screenshot=results/gpt-6.1-terra-max.png results/gpt-6.1-terra-max.svg
"""
import base64
import html
import math
import pathlib
import statistics
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.append(str(HERE.parent / "financial-qa"))
import grade  # noqa: E402  Financial QA's grade.py and results.py, pointed at this folder's data below
import results  # noqa: E402
from models import label  # noqa: E402

ROUNDS = ("round1",)  # this folder's grading rounds, in the order graded


def summary(config, correct, search_usd):
    """Accuracy per run and by question type, and the mean cost per run: model calls, PageIndex searches, total."""
    runs, qs = results.graded_runs(config, correct), grade.questions()
    accuracy = [sum(correct[(q["id"], f"{config} r{r}")] for q in qs) for r in runs]
    by_type = {t: 100 * statistics.mean(correct[(q["id"], f"{config} r{r}")]
                                        for q in qs if q["type"] == t for r in runs) for t in results.TYPES}
    llm = statistics.mean(math.fsum(results.costs(config, r)[0].values()) for r in runs)
    search = [search_usd(config, r) for r in runs]
    search = None if None in search else statistics.mean(search)
    hits = {q["id"]: sum(correct[(q["id"], f"{config} r{r}")] for r in runs) for q in qs}
    return {"accuracy": accuracy, "by_type": by_type, "llm": llm, "search": search, "hits": hits, "runs": len(runs)}


def standing_search_usd(config, run):
    """PageIndex's charge for the searches of the answers that stand (each row's pageindex_usd)."""
    return math.fsum(row.get("pageindex_usd") or 0 for row in grade.answer_rows(config, run).values())


# the homepage's chart (pageindex.ai/agent): two columns per measure from zero, legacy in grey, the new agent in blue
W, H, X0, GAP, PLOT_H, BASE = 1280, 720, 72, 56, 230, 584
# time to index a 100-page document, as pageindex.ai/agent gives it (not measured in these runs): (value drawn, text)
INDEX_TIME = {"legacy": (30, "30 s"), "new": (1, "<1 s")}
SERIF = "'New York', 'Iowan Old Style', Georgia, serif"
LOGO = HERE.parent / "financial-qa" / "assets" / "pageindex-wordmark.svg"


def text(x, y, s, size, fill, anchor="start", family=SERIF):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{family}" font-size="{size}" fill="{fill}" '
            f'text-anchor="{anchor}" style="font-variant-numeric: tabular-nums">{html.escape(s)}</text>')


def bar(cx, value, top, fill):
    h = PLOT_H * max(value / top, 0.02)
    x, y, w, r = cx - 41, BASE - h, 82, 4
    return (f'<path d="M{x:.1f},{BASE} V{y + r:.1f} Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} H{x + w - r:.1f} '
            f'Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f} V{BASE} Z" fill="{fill}"/>'), y


def svg(config, old, new):
    acc_old, acc_new = statistics.mean(old["accuracy"]), statistics.mean(new["accuracy"])
    usd_old, usd_new = old["llm"] + (old["search"] or 0), new["llm"] + new["search"]
    saved = round((1 - usd_new / usd_old) * 100)
    logo = base64.b64encode(LOGO.read_bytes()).decode("ascii")
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">',
           f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
           text(X0, 92, "The new PageIndex Agent, against legacy PageIndex", 36, "#0f172a"),
           text(X0, 134, f"Same model, same questions: {saved}% cheaper, more accurate, and indexed in under a second.",
                20, "#64748b"),
           f'<image x="{W - X0 - 150}" y="62" width="150" height="31" href="data:image/svg+xml;base64,{logo}"/>']
    (t_old, s_old), (t_new, s_new) = INDEX_TIME["legacy"], INDEX_TIME["new"]
    metrics = (("More accurate", "Accuracy", 100, (acc_old, f"{acc_old:.1f}%"), (acc_new, f"{acc_new:.1f}%")),
               (f"{saved}% less cost", "Cost per 100 questions", usd_old, (usd_old, f"${usd_old:.2f}"),
                (usd_new, f"${usd_new:.2f}")),
               ("Instant indexing", "Index time, 100 pages", t_old, (t_old, s_old), (t_new, s_new)))
    width = (W - 2 * X0 - 2 * GAP) / 3
    for i, (headline, name, top, a, b) in enumerate(metrics):
        mx = X0 + i * (width + GAP)
        cx = mx + width / 2
        out += [text(mx, 222, headline, 34, "#1a61af"), text(mx, 256, name, 19, "#64748b"),
                f'<line x1="{mx:.1f}" y1="{BASE}" x2="{mx + width:.1f}" y2="{BASE}" stroke="#cbd5e1"/>']
        for col, (value, shown), is_new in ((cx - 60, a, False), (cx + 60, b, True)):
            mark, y = bar(col, value, top, "#3788d8" if is_new else "#cbd5e1")
            ink, accent = ("#0f172a", "#1a61af") if is_new else ("#64748b", "#64748b")
            out += [mark, text(col, y - 12, shown, 28 if is_new else 23, ink, "middle"),
                    text(col, BASE + 32, "New Agent" if is_new else "Legacy", 19, accent, "middle")]
    out += [text(X0, BASE + 96, f"{label(config)} · mean of {len(new['accuracy'])} runs", 17, "#737b8c",
                 family="system-ui, -apple-system, 'Segoe UI', sans-serif"), "</svg>"]
    return "\n".join(out) + "\n"


def main():
    old_correct = grade.grades()
    configs = sorted({m for m, _ in (p.stem.rsplit("_run", 1) for p in (HERE / "data" / "answers").glob("*.jsonl"))})
    old = {m: summary(m, old_correct, lambda m, r: None) for m in configs}  # a local library: no PageIndex charge
    grade.DATA, grade.GRADES = HERE / "data", HERE / "data" / "grading"
    correct = {}
    for rnd in ROUNDS:
        correct |= {k: v for k, v in grade.round_grades(rnd).items() if not k[1].startswith("anchor ")}
    new = {m: summary(m, correct, standing_search_usd) for m in configs}

    n = {t: sum(q["type"] == t for q in grade.questions()) for t in results.TYPES}
    lines = ["| Configuration | PageIndex | Accuracy (%) | Runs | "
             + " | ".join(f"{t} ({n[t]})" for t in results.TYPES)
             + " | $ model calls | $ PageIndex search | $ per run |", "|---|---|---|---|---|---|---|---|---|---|"]
    notes = []
    for m in configs:
        for name, s in (("legacy, 0.4.4", old[m]), ("new agent, 0.7.0", new[m])):
            search = "–" if s["search"] is None else f"{s['search']:.2f}"
            lines.append(f"| {label(m)} | {name} | {statistics.mean(s['accuracy']):.1f} | "
                         f"{'/'.join(map(str, s['accuracy']))} | "
                         + " | ".join(f"{s['by_type'][t]:.1f}" for t in results.TYPES)
                         + f" | {s['llm']:.2f} | {search} | {s['llm'] + (s['search'] or 0):.2f} |")
        a, b = new[m], old[m]  # per question, the share of correct runs, as results.py compare
        den = math.lcm(a["runs"], b["runs"])
        diffs = [a["hits"][i] * den // a["runs"] - b["hits"][i] * den // b["runs"] for i in a["hits"]]
        notes.append(f"- {label(m)}, per question, new agent : legacy = {sum(d > 0 for d in diffs)} : "
                     f"{sum(d < 0 for d in diffs)}, paired p = {results.paired_p(diffs):.2f}")
    out = HERE / "results" / "results.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines + [""] + notes) + "\n")
    for m in configs:
        (HERE / "results" / f"{m}.svg").write_text(svg(m, old[m], new[m]))
    print(out.read_text())


if __name__ == "__main__":
    main()
