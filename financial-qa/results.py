"""The results, computed from data/: the table, a CSV of every run, the accuracy-vs-cost chart, and comparisons.

    python3 results.py                  # -> results/results.md, results/runs.csv, results/accuracy_vs_cost.svg
    python3 results.py compare A B      # per question, A's correct runs vs B's: better : worse, sign-test p

The PNG is the SVG rendered by a headless browser, e.g.:
    google-chrome --headless --hide-scrollbars --window-size=1280,860 --force-device-scale-factor=2 \
        --screenshot=results/accuracy_vs_cost.png results/accuracy_vs_cost.svg
"""
import base64
import csv
import html
import math
import pathlib
import statistics
import sys

import grade
from models import CONFIGS, label

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "results"
TYPES = ("SET", "WHY", "XCO")


def costs(config, run):
    """question id -> USD OpenRouter billed for the attempt whose answer stands (calls not matched to a question,
    under None), and the USD of the other attempts: those that ended in an account error and were retried, and
    those that ran out of turns and were asked again. An attempt's calls fall between its row's start and end."""
    standing, kept, other = grade.answer_rows(config, run), {}, 0.0
    for c in grade.read(grade.DATA / "calls" / f"{config}_run{run}.jsonl"):
        if not c.get("ok"):
            continue
        row = standing.get(c["id"])
        if row is None or row["started"] <= c["start"] <= row["started"] + (row.get("seconds") or 0) + 5:
            kept[c["id"]] = kept.get(c["id"], 0) + c["cost"]
        else:
            other += c["cost"]
    return kept, other


def graded_runs(config, correct):
    """The runs of a configuration that a round in grade.ROUNDS has graded; runs not graded yet are left out."""
    return [r for r in grade.runs_of(config) if all((q["id"], f"{config} r{r}") in correct for q in grade.questions())]


def results():
    """config -> (accuracy % per run, by question type % over its runs, mean USD per run, the runs), for every
    configuration with graded runs."""
    correct, qs, out = grade.grades(), grade.questions(), {}
    for m in CONFIGS:
        runs = graded_runs(m, correct)
        if not runs:
            continue
        by_type = {t: 100 * statistics.mean(correct[(q["id"], f"{m} r{r}")] for q in qs if q["type"] == t for r in runs)
                   for t in TYPES}
        out[m] = ([100 * sum(correct[(q["id"], f"{m} r{r}")] for q in qs) / len(qs) for r in runs], by_type,
                  statistics.mean(math.fsum(costs(m, r)[0].values()) for r in runs), runs)
    return out


def pareto(points):
    """Configurations no other beats on both cost and accuracy, cheapest first."""
    front, best = [], -1
    for m, (acc, cost) in sorted(points.items(), key=lambda p: (p[1][1], -p[1][0])):
        if acc > best:
            front.append(m)
            best = acc
    return front


def table(res):
    """Every configuration as a Markdown table, by accuracy."""
    qs = grade.questions()
    points = {m: (statistics.mean(runs), cost) for m, (runs, _, cost, _) in res.items()}
    front = pareto(points)
    logo = base64.b64encode((HERE / "assets" / "pageindex-wordmark.svg").read_bytes()).decode("ascii")
    out = ["| # | Model | Reasoning | Accuracy (%) | Runs | " + " | ".join(f"{t} ({sum(q['type'] == t for q in qs)})" for t in TYPES)
           + " | $ per run | Pareto |", "|" + "---|" * 4 + "---|" * 6]
    for n, (m, (acc, cost)) in enumerate(sorted(points.items(), key=lambda p: (-p[1][0], p[1][1])), 1):
        runs, by_type, *_ = res[m]
        out.append(f"| {n} | {CONFIGS[m][0]} | {CONFIGS[m][4] or '–'} | {acc:.1f} | {'/'.join(f'{r:.0f}' for r in runs)} | "
                   + " | ".join(f"{by_type[t]:.1f}" for t in TYPES) + f" | {cost:.2f} | {'✓' if m in front else ''} |")
    return "\n".join(out) + "\n"


def runs_csv(path, res):
    """Per run: correct answers, by type; answers asked again after running out of turns; usd, the cost in the
    results; billed_usd, every call of the run, retried and replaced attempts included (data/runs.jsonl)."""
    correct, qs, lines = grade.grades(), grade.questions(), grade.read(grade.DATA / "runs.jsonl")
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["config", "model", "reasoning", "run", "correct", *TYPES, "asked_again", "usd", "billed_usd"])
        for m, (*_, runs) in res.items():
            for r in runs:
                hits = {t: sum(correct[(q["id"], f"{m} r{r}")] for q in qs if q["type"] == t) for t in TYPES}
                again = sum("max_turns_limit" in row for row in grade.answer_rows(m, r).values())
                billed = math.fsum(b["usd"] for b in lines if b["model"] == m and b["run"] == r)
                w.writerow([m, CONFIGS[m][0], CONFIGS[m][4] or "", r, sum(hits.values()), *hits.values(), again,
                            f"{math.fsum(costs(m, r)[0].values()):.6f}", f"{billed:.6f}"])


# PageIndex benchmark chart; vendor colors identify model providers.
COLOR = {"OpenAI": "#1f1f1f", "Anthropic": "#c8795a", "Google": "#36a854", "Alibaba": "#ff7017", "Z AI": "#1880f6",
         "Xiaomi": "#ff6903", "Kimi": "#0b81ff", "DeepSeek": "#2243e5", "MiniMax": "#ed3769", "Meta": "#0489f3",
         "SpaceXAI": "#726dd3"}
VENDORS = ("OpenAI", "Anthropic", "Google", "Alibaba", "Z AI", "Xiaomi", "Kimi", "DeepSeek", "MiniMax", "Meta", "SpaceXAI")
# label position per configuration: (dx, dy, text-anchor) from the marker, set by eye against the rendered chart
PLACE = {"kimi-k3.1-pro-max": (11, -5, "start"), "minimax-m3.1-flash-max": (11, 4, "start"), "gpt-6.1-sol-low": (-11, 4, "end"), "minimax-m3.1-flash-xhigh": (-11, 4, "end"),
         "minimax-m3.1-flash-medium": (8, 24, "start"), "mimo-v2.6-flash": (11, 9, "start"),
         "glm-5.3-flash-max": (-9, -9, "end"), "glm-5.3-max": (0, 22, "middle"),
         "muse-spark-open-xhigh": (0, -14, "middle"), "gpt-6.1-sol-medium": (-10, -10, "end"),
         "muse-wonder-adaptive": (-11, 4, "end"), "claude-opus-5.5-medium": (0, 22, "middle"),
         "qwen3.8-max-xhigh": (0, -12, "middle"), "gemini-4-argon-medium": (-10, -10, "end"),
         "gemini-4-argon-high": (0, -12, "middle"), "claude-sonnet-5.5-max": (11, 16, "start"),
         "claude-haiku-5.5-max": (0, -12, "middle"), "claude-opus-5.5-max": (0, -12, "middle")}
# in the table, not on the chart, to declutter: three models shown at a higher level; MiniMax at high and low, within
# noise of a point shown (high) or below another model (low)
HIDE = ("gpt-6-luna-medium", "claude-haiku-5.5-medium", "grok-4.7-high", "minimax-m3.1-flash-high", "minimax-m3.1-flash-low")
W, H = 1280, 860
X0, X1, Y0, Y1 = 84, 1240, 166, 770            # plot area
COST, ACC = (1, 200), (70, 100)                # USD per run, log scale; accuracy %
SURFACE, INK, INK2, MUTED, FAINT = "#ffffff", "#000000", "#464646", "#666666", "#8f8f8f"
ACCENT, GRID = "#2563eb", "#edf0f4"


def x(cost):
    return X0 + (math.log10(cost) - math.log10(COST[0])) / (math.log10(COST[1]) - math.log10(COST[0])) * (X1 - X0)


def y(acc):
    return Y1 - (acc - ACC[0]) / (ACC[1] - ACC[0]) * (Y1 - Y0)


def text(tx, ty, s, size=13, fill=INK2, anchor="start", weight=400, font="", halo=None):
    """halo: the background's color, drawn around the letters so a line under them does not cut through."""
    if halo:
        font += f' stroke="{halo}" stroke-width="4" stroke-linejoin="round" paint-order="stroke"'
    return (f'<text x="{tx:.1f}" y="{ty:.1f}" font-size="{size}" fill="{fill}" text-anchor="{anchor}" '
            f'font-weight="{weight}" {font}>{html.escape(s)}</text>')


def legend(items, ty):
    """One legend row: (mark drawn at the item's x, label), spaced by an estimate of each label's width."""
    out, lx = [], X0
    for mark, name in items:
        out += [mark(lx), text(lx + 22, ty + 5, name, 15, INK)]
        lx += 22 + len(name) * 7.2 + 22
    return out


def svg(res):
    points = {m: (statistics.mean(runs), cost) for m, (runs, _, cost, _) in res.items() if m not in HIDE}
    front = pareto(points)
    logo = base64.b64encode((HERE / "assets" / "pageindex-wordmark.svg").read_bytes()).decode("ascii")
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
           f'font-family="system-ui, -apple-system, \'Segoe UI\', sans-serif">',
           f'<rect width="{W}" height="{H}" fill="{SURFACE}"/>',
           text(X0, 64, "PageIndex Financial QA Benchmark", 40, INK, weight=650, font="font-family=\"'Iowan Old Style', Georgia, serif\""),
           text(X0, 94, "Question Answering Accuracy vs. Cost on 40 10-K Documents Across 8 Companies", 16, FAINT),
           f'<image x="{X1 - 170}" y="37" width="170" height="35" href="data:image/svg+xml;base64,{logo}"/>',
           f'<line x1="{X1 - 130}" y1="133" x2="{X1 - 106}" y2="133" stroke="{ACCENT}" stroke-width="2"/>',
           text(X1 - 98, 138, "Pareto frontier", 13, MUTED)]
    out += legend([(lambda lx, v=v: f'<circle cx="{lx + 8}" cy="133" r="6.5" fill="{COLOR[v]}"/>', v) for v in VENDORS], 133)
    for a in range(ACC[0], ACC[1] + 1, 5):
        out += [f'<line x1="{X0}" y1="{y(a):.1f}" x2="{X1}" y2="{y(a):.1f}" stroke="{GRID}" stroke-width="1"/>',
                f'<line x1="{X0 - 9}" y1="{y(a):.1f}" x2="{X0 - 3}" y2="{y(a):.1f}" stroke="{MUTED}" stroke-width="1"/>',
                text(X0 - 14, y(a) + 4, f"{a}", 13, MUTED, "end")]
    for c in (1, 2, 3, 4, 5, 7, 10, 20, 30, 40, 50, 70, 100, 200):
        out += [f'<line x1="{x(c):.1f}" y1="{Y1 + 3}" x2="{x(c):.1f}" y2="{Y1 + 9}" stroke="{MUTED}" stroke-width="1"/>',
                text(x(c), Y1 + 26, f"${c}", 13, MUTED, "middle")]
    out += [text((X0 + X1) / 2, Y1 + 58, "Cost per 100-question run (USD, log scale)", 15, INK, "middle"),
            f'<g transform="translate(26 {(Y0 + Y1) / 2}) rotate(-90)">'
            + text(0, 0, "Accuracy (%, mean of 3 runs)", 15, INK, "middle") + "</g>"]
    path = " ".join(f"{'M' if i == 0 else 'L'}{x(points[m][1]):.1f},{y(points[m][0]):.1f}" for i, m in enumerate(front))
    out.append(f'<path d="{path}" fill="none" stroke="{ACCENT}" stroke-width="2" '
               f'stroke-linecap="round" stroke-linejoin="round"/>')
    for m, (acc, cost) in sorted(points.items(), key=lambda p: p[1][1]):
        px, py = x(cost), y(acc)
        dx, dy, anchor = PLACE.get(m, (11, 4, "start"))
        runs = "/".join(f"{r:.0f}" for r in res[m][0])
        if m in front:
            out.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="9" fill="{SURFACE}" stroke="{ACCENT}" stroke-width="1.5"/>')
        out += [f'<g><title>{html.escape(label(m))}: {acc:.1f}% ({runs}), ${cost:.2f} per run</title>'
                f'<circle cx="{px:.1f}" cy="{py:.1f}" r="12" fill="transparent"/>'
                f'<circle cx="{px:.1f}" cy="{py:.1f}" r="6.5" fill="{COLOR[CONFIGS[m][1]]}" stroke="{SURFACE}" stroke-width="1"/></g>',
                text(px + dx, py + dy, label(m), 13, INK2, anchor, halo=SURFACE)]
    return "\n".join(out + ["</svg>"]) + "\n"


def sign_test(better, worse):
    n, k = better + worse, min(better, worse)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n) if n else 1.0


def compare(a, b):
    """Per question, the share of each configuration's runs answered correctly; the sign test counts the questions
    where one is higher."""
    correct = grade.grades()
    share = {m: {q["id"]: statistics.mean(correct[(q["id"], f"{m} r{r}")] for r in graded_runs(m, correct))
                 for q in grade.questions()} for m in (a, b)}
    better = sum(share[a][i] > share[b][i] for i in share[a])
    worse = sum(share[a][i] < share[b][i] for i in share[a])
    print(f"{label(a)} vs {label(b)}: {better} : {worse} questions, sign-test p = {sign_test(better, worse):.3f}")


if __name__ == "__main__":
    if sys.argv[1:2] == ["compare"]:
        assert len(sys.argv) == 4 and set(sys.argv[2:]) <= set(CONFIGS), "usage: results.py compare CONFIG CONFIG"
        sys.exit(compare(*sys.argv[2:4]))
    res = results()
    OUT.mkdir(exist_ok=True)
    (OUT / "results.md").write_text(table(res))
    runs_csv(OUT / "runs.csv", res)
    (OUT / "accuracy_vs_cost.svg").write_text(svg(res))
    print(f"wrote {OUT.relative_to(HERE)}/results.md, runs.csv, accuracy_vs_cost.svg")
