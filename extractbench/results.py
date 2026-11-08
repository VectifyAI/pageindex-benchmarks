"""Tables, charts and ExtractBench leaderboard rows from the runs in data/ (standard library only).

    python results.py

For each tier run (data/<tier>/<split>/<stem>.json, the extracted value, and .score.json, ExtractBench's score of
it; a run through the API by run.py also leaves .job.json, the job as the API returned it), writes results/results.md, the rows to add to
ExtractBench's leaderboard.csv in its own format (results/leaderboard-rows.csv), and two charts beside the systems on
ExtractBench's leaderboard (results/extractbench-leaderboard-4064262.csv, its leaderboard.csv at commit 4064262):
results/value_f1_vs_cost.svg and results/value_f1_leaderboard.svg.

The numbers are computed as ExtractBench's leaderboard computes them: value F1, precision and recall averaged over
documents, each the same, a document with no result (a failed job) counting zero; Overall over all 370 documents;
cost per page as the mean of each document's dollars per page, what Page Extract charges (the tier's price a page);
latency as the mean seconds a document took: from the request that started the job to its completion where the job
was run through the API, else the run's own time. Page Extract gives each list item its page, not the
boxes of its words, so the grounding columns are 0, which ExtractBench reads as not reported.

The PNG is the SVG rendered by a headless browser, e.g.:
    google-chrome --headless --hide-scrollbars --window-size=1280,860 --force-device-scale-factor=2 \\
        --screenshot=results/value_f1_vs_cost.png results/value_f1_vs_cost.svg
"""
import csv
import datetime
import html
import json
import math
import pathlib
import statistics

HERE = pathlib.Path(__file__).resolve().parent
SPLITS = ("short", "medium", "long")
COUNTS = {"short": 252, "medium": 98, "long": 20}  # ExtractBench's documents per split
TIERS = {"standard": "Standard", "pro": "Pro"}
PRICE = {"standard": 0.03, "pro": 0.05}  # dollars a page, Page Extract's price
LEADERBOARD = HERE / "results" / "extractbench-leaderboard-4064262.csv"


def when(s):
    return datetime.datetime.fromisoformat(s)


def documents(tier):
    """Per document: split, stem, value F1, precision, recall (0 to 1), dollars per page, seconds, status."""
    out = []
    for split in SPLITS:
        folder = HERE / "data" / tier / split
        stems = sorted({f.name[: -len(".score.json")] for f in folder.glob("*.score.json")}
                       | {f.name[: -len(".job.json")] for f in folder.glob("*.job.json")})
        for stem in stems:
            score_file, job_file = folder / f"{stem}.score.json", folder / f"{stem}.job.json"
            score = json.loads(score_file.read_text()) if score_file.exists() else {}
            metrics = score.get("metrics") or {}
            if job_file.exists():  # run through the API
                job = json.loads(job_file.read_text())
                status, usage = job["status"], job.get("usage") or {}
                per_page = usage["credits"] / usage["pages"] if status == "COMPLETED" and usage.get("pages") else None
                seconds = (when(job["updated_at"]) - when(job["created_at"])).total_seconds()
            else:
                status = "COMPLETED" if score else "FAILED"
                per_page = PRICE[tier] if score else None
                seconds = (score.get("run") or {}).get("seconds")
            done = status == "COMPLETED"
            out.append({
                "split": split, "stem": stem, "status": status,
                "f1": metrics.get("extract_unified_value_f1", 0) if done else 0,
                "p": metrics.get("extract_unified_value_precision", 0) if done else 0,
                "r": metrics.get("extract_unified_value_recall", 0) if done else 0,
                "per_page": per_page, "seconds": seconds,
            })
    return out


def summary(docs):
    """The leaderboard's numbers, as percentages, dollars and seconds; None where a split has no documents yet."""
    def mean(xs):
        xs = [x for x in xs if x is not None]
        return statistics.mean(xs) if xs else None

    s = {"documents": len(docs), "failed": sum(d["status"] != "COMPLETED" for d in docs),
         "Overall": mean([100 * d["f1"] for d in docs]), "Perfect": mean([100 * (d["f1"] >= 1) for d in docs]),
         "Cost_Per_Page": mean([d["per_page"] for d in docs])}
    for split in SPLITS:
        part = [d for d in docs if d["split"] == split]
        name = split.capitalize()
        s[name] = mean([100 * d["f1"] for d in part])
        s[f"n_{split}"] = len(part)
        s[f"P_{name}"] = mean([100 * d["p"] for d in part])
        s[f"R_{name}"] = mean([100 * d["r"] for d in part])
        s[f"Cost_{name}"] = mean([d["per_page"] for d in part])
        s[f"Latency_S_Per_Doc_{name}"] = mean([d["seconds"] for d in part])
    return s


def fmt(v, digits=2):
    return "–" if v is None else f"{v:.{digits}f}"


def runs():
    return {t: summary(documents(t)) for t in TIERS if (HERE / "data" / t).exists()}


def leaderboard_rows(res):
    with LEADERBOARD.open() as f:
        columns = next(csv.reader(f))
    rows = []
    for tier, s in res.items():
        row = {c: "" for c in columns}
        row.update({"Provider": f"PageIndex Page Extract ({TIERS[tier]})", "Category": "Specialized APIs",
                    "Pipeline": f"pageindex_page_extract_{tier}", "Reasoning": "", "include_in_rankings": "true"})
        for c in columns:
            if c.startswith(("Word_Grounding", "Page_Grounding")):
                row[c] = "0.00"
            elif c in s and s[c] is not None:
                row[c] = f"{s[c]:.4f}" if c.startswith("Cost") else f"{s[c]:.1f}" if c.startswith("Latency") \
                    else f"{s[c]:.2f}"
        rows.append(row)
    return columns, rows


def others():
    """The systems ranked on ExtractBench's leaderboard: (name, category, Overall, cost per page or None)."""
    with LEADERBOARD.open() as f:
        return [(r["Provider"], r["Category"], float(r["Overall"]),
                 float(r["Cost_Per_Page"]) if r["Cost_Per_Page"] else None)
                for r in csv.DictReader(f) if r["include_in_rankings"] == "true" and r["Overall"]]


def markdown(res):
    lines = ["# Page Extract on ExtractBench", "",
             "Value F1 (%), averaged over documents, each the same; a failed document counts zero.", "",
             "| Tier | Overall | Short | Medium | Long | % perfect | ¢ / page | Failed | Documents |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for tier, s in res.items():
        lines.append(f"| {TIERS[tier]} | {fmt(s['Overall'])} | {fmt(s['Short'])} | {fmt(s['Medium'])} | "
                     f"{fmt(s['Long'])} | {fmt(s['Perfect'], 1)} | {fmt(None if s['Cost_Per_Page'] is None else 100 * s['Cost_Per_Page'])} | "
                     f"{s['failed']} | {s['documents']} of 370 |")
    lines += ["", "Precision, recall and seconds per document, by split:", "",
              "| Tier | Split | Documents | Value F1 | Precision | Recall | Seconds / document |",
              "|---|---|---:|---:|---:|---:|---:|"]
    for tier, s in res.items():
        for split in SPLITS:
            n = split.capitalize()
            lines.append(f"| {TIERS[tier]} | {split} | {s[f'n_{split}']} of {COUNTS[split]} | {fmt(s[n])} | "
                         f"{fmt(s[f'P_{n}'])} | {fmt(s[f'R_{n}'])} | {fmt(s[f'Latency_S_Per_Doc_{n}'], 0)} |")
    lines += ["", "Beside ExtractBench's leaderboard (commit 4064262), by Overall value F1:", "",
              "| # | System | Overall | ¢ / page |", "|---:|---|---:|---:|"]
    board = [(n, o, c) for n, _, o, c in others()]
    board += [(f"**PageIndex Page Extract ({TIERS[t]})**", s["Overall"], s["Cost_Per_Page"]) for t, s in res.items()
              if s["Overall"] is not None]
    for i, (n, o, c) in enumerate(sorted(board, key=lambda b: (-b[1], b[2] if b[2] is not None else 1e9))[:15], 1):
        lines.append(f"| {i} | {n} | {o:.2f} | {fmt(None if c is None else 100 * c)} |")
    return "\n".join(lines) + "\n"


# charts, in the style of the financial-qa charts beside this folder
W, H = 1280, 860
X0, X1, Y0, Y1 = 84, 1240, 166, 770
COST, F1 = (0.2, 100), (75, 100)               # cents per page, log scale; value F1 %
# label position for the systems named on the scatter: (dx, dy, text-anchor) from the marker, set by eye
PLACE = {"LlamaExtract Agentic Plus": (0, -14, "middle"), "Reducto Deep Extract": (0, 24, "middle"),
         "Pulse (Effort)": (11, 5, "start"), "LlamaExtract Agentic Plus (Max Effort)": (11, 5, "start"),
         "LlamaExtract Agentic": (-11, 5, "end"), "LlamaExtract Cost-Effective": (11, 5, "start"),
         "Page Extract (Pro)": (-13, -12, "end"), "Page Extract (Standard)": (-13, -10, "end")}
SCATTER_F1 = (88, 98)                          # the scatter's value F1 axis: the systems near the top, apart
SURFACE, INK, INK2, MUTED, FAINT = "#ffffff", "#000000", "#464646", "#666666", "#8f8f8f"
ACCENT, OTHER, GRID = "#2563eb", "#b4bac4", "#edf0f4"
SERIF = "font-family=\"'Iowan Old Style', Georgia, serif\""


def x(cents):
    return X0 + (math.log10(cents) - math.log10(COST[0])) / (math.log10(COST[1]) - math.log10(COST[0])) * (X1 - X0)


def y(f1, axis=F1):
    return Y1 - (f1 - axis[0]) / (axis[1] - axis[0]) * (Y1 - Y0)


def text(tx, ty, s, size=13, fill=INK2, anchor="start", weight=400, font="", halo=None):
    if halo:
        font += f' stroke="{halo}" stroke-width="4" stroke-linejoin="round" paint-order="stroke"'
    return (f'<text x="{tx:.1f}" y="{ty:.1f}" font-size="{size}" fill="{fill}" text-anchor="{anchor}" '
            f'font-weight="{weight}" {font}>{html.escape(s)}</text>')


def head(h, subtitle, legend):
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {h}" width="{W}" height="{h}" '
           f'font-family="system-ui, -apple-system, \'Segoe UI\', sans-serif">',
           f'<rect width="{W}" height="{h}" fill="{SURFACE}"/>',
           text(X0, 64, "Page Extract on ExtractBench", 40, INK, weight=650, font=SERIF),
           text(X0, 94, subtitle, 16, FAINT)]
    lx = X0
    for mark, name in legend:
        out += [mark(lx), text(lx + 22, 138, name, 15, INK)]
        lx += 22 + len(name) * 7.2 + 24
    return out


def scatter(res):
    ours = [(f"Page Extract ({TIERS[t]})", s["Overall"], 100 * s["Cost_Per_Page"]) for t, s in res.items()
            if s["Overall"] is not None and s["Cost_Per_Page"]]
    lo, hi = SCATTER_F1
    rest = [(n, o, 100 * c) for n, _, o, c in others() if o >= lo and c]
    out = head(H, f"Value F1 vs. cost per page on 370 documents (4,869 pages), beside the systems on ExtractBench's "
                  f"leaderboard above {lo}",
               [(lambda lx: f'<circle cx="{lx + 8}" cy="133" r="7" fill="{ACCENT}"/>', "Page Extract"),
                (lambda lx: f'<circle cx="{lx + 8}" cy="133" r="6" fill="{OTHER}"/>', "Systems on ExtractBench's leaderboard")])
    for a in range(lo, hi + 1, 2):
        out += [f'<line x1="{X0}" y1="{y(a, SCATTER_F1):.1f}" x2="{X1}" y2="{y(a, SCATTER_F1):.1f}" stroke="{GRID}" stroke-width="1"/>',
                text(X0 - 14, y(a, SCATTER_F1) + 4, f"{a}", 13, MUTED, "end")]
    for c in (0.2, 0.5, 1, 2, 3, 5, 10, 20, 50, 100):
        out += [f'<line x1="{x(c):.1f}" y1="{Y1 + 3}" x2="{x(c):.1f}" y2="{Y1 + 9}" stroke="{MUTED}" stroke-width="1"/>',
                text(x(c), Y1 + 26, f"{c:g}¢", 13, MUTED, "middle")]
    out += [text((X0 + X1) / 2, Y1 + 58, "Cost per page (US cents, log scale)", 15, INK, "middle"),
            f'<g transform="translate(26 {(Y0 + Y1) / 2}) rotate(-90)">'
            + text(0, 0, "Value F1 (%, mean over documents)", 15, INK, "middle") + "</g>"]
    for n, o, c in rest:
        px, py = x(min(max(c, COST[0]), COST[1])), y(o, SCATTER_F1)
        out.append(f'<g><title>{html.escape(n)}: {o:.2f}, {c:.2f}¢ a page</title>'
                   f'<circle cx="{px:.1f}" cy="{py:.1f}" r="12" fill="transparent"/>'
                   f'<circle cx="{px:.1f}" cy="{py:.1f}" r="6" fill="{OTHER}" stroke="{SURFACE}" stroke-width="1"/></g>')
        if n in PLACE:  # the leaders, and the cheapest close to them, named; the rest on hover
            dx, dy, anchor = PLACE[n]
            out.append(text(px + dx, py + dy, n, 13, MUTED, anchor, halo=SURFACE))
    for n, o, c in ours:
        px, py = x(c), y(o, SCATTER_F1)
        dx, dy, anchor = PLACE.get(n, (-12, -10, "end"))
        out += [f'<g><title>{html.escape(n)}: {o:.2f}, {c:.2f}¢ a page</title>'
                f'<circle cx="{px:.1f}" cy="{py:.1f}" r="12" fill="transparent"/>'
                f'<circle cx="{px:.1f}" cy="{py:.1f}" r="7.5" fill="{ACCENT}" stroke="{SURFACE}" stroke-width="2"/></g>',
                text(px + dx, py + dy, f"{n}  {o:.2f}", 14, INK, anchor, weight=600, halo=SURFACE)]
    return "\n".join(out + ["</svg>"]) + "\n"


ROW, BAR, TOP_N = 28, 16, 15
LB_Y0 = 176
LB_X0, LB_X1 = X0 + 330, X1 - 150             # bar area, F1[0] to 100


def bx(f1):
    return LB_X0 + (f1 - F1[0]) / (100 - F1[0]) * (LB_X1 - LB_X0)


def bars(res):
    board = [(n, o, c, False) for n, _, o, c in others()]
    board += [(f"Page Extract ({TIERS[t]})", s["Overall"], s["Cost_Per_Page"], True) for t, s in res.items()
              if s["Overall"] is not None]
    board = sorted(board, key=lambda b: (-b[1], b[2] if b[2] is not None else 1e9))[:TOP_N]
    h = LB_Y0 + len(board) * ROW + 90
    out = head(h, f"Overall value F1 on 370 documents: the top {TOP_N}, with ExtractBench's leaderboard (commit 4064262)",
               [(lambda lx: f'<rect x="{lx + 1}" y="127" width="14" height="12" rx="2" fill="{ACCENT}"/>', "Page Extract"),
                (lambda lx: f'<rect x="{lx + 1}" y="127" width="14" height="12" rx="2" fill="{OTHER}"/>', "Systems on ExtractBench's leaderboard")])
    bottom = LB_Y0 + len(board) * ROW
    for a in range(F1[0], 101, 5):
        out += [f'<line x1="{bx(a):.1f}" y1="{LB_Y0 - 6}" x2="{bx(a):.1f}" y2="{bottom + 2}" stroke="{GRID}" stroke-width="1"/>',
                text(bx(a), bottom + 22, f"{a}", 13, MUTED, "middle")]
    out += [text((LB_X0 + LB_X1) / 2, bottom + 54, f"Value F1 (%; the axis starts at {F1[0]})", 15, INK, "middle"),
            text(X1, LB_Y0 - 14, "¢ / page", 13, MUTED, "end")]
    for i, (n, o, c, mine) in enumerate(board, 1):
        mid = LB_Y0 + (i - 1) * ROW + ROW / 2
        out += [text(X0 + 22, mid + 5, f"{i}", 14, FAINT, "end"),
                text(X0 + 36, mid + 5, n, 14, INK, weight=650 if mine else 400),
                f'<g><title>{html.escape(n)}: {o:.2f}, {fmt(None if c is None else 100 * c)}¢ a page</title>'
                f'<rect x="{LB_X0}" y="{mid - BAR / 2:.1f}" width="{bx(o) - LB_X0:.1f}" height="{BAR}" rx="2" '
                f'fill="{ACCENT if mine else OTHER}"/></g>',
                text(bx(o) + 8, mid + 5, f"{o:.2f}", 14, INK, weight=650 if mine else 400),
                text(X1, mid + 5, fmt(None if c is None else 100 * c), 14, INK2, "end")]
    return "\n".join(out + ["</svg>"]) + "\n"


def main():
    res = runs()
    out = HERE / "results"
    (out / "results.md").write_text(markdown(res))
    columns, rows = leaderboard_rows(res)
    with (out / "leaderboard-rows.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, columns)
        w.writeheader()
        w.writerows(rows)
    (out / "value_f1_vs_cost.svg").write_text(scatter(res))
    (out / "value_f1_leaderboard.svg").write_text(bars(res))
    for tier, s in res.items():
        print(f"{TIERS[tier]}: {s['documents']} documents, {s['failed']} failed, Overall {fmt(s['Overall'])} "
              f"(short {fmt(s['Short'])}, medium {fmt(s['Medium'])}, long {fmt(s['Long'])}), "
              f"{fmt(None if s['Cost_Per_Page'] is None else 100 * s['Cost_Per_Page'])}¢ a page")


if __name__ == "__main__":
    main()
