import argparse
import html
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ARTIFACT = ROOT / "ai_engineer_training.html"
CJK = re.compile(r"[一-鿿぀-ヿ가-힯]")
HEX = re.compile(r"#[0-9A-Fa-f]{3,8}")
LEVELS = {"мидл", "сеньор", "база"}


class Report:
    def __init__(self):
        self.failures = []
        self.notes = []

    def check(self, ok, label, detail=""):
        if ok:
            self.notes.append(f"  ok   {label}")
        else:
            self.failures.append(f"  FAIL {label}" + (f" — {detail}" if detail else ""))
        return ok

    def note(self, text):
        self.notes.append(f"  --   {text}")

    def emit(self):
        for line in self.notes:
            print(line)
        for line in self.failures:
            print(line)
        return not self.failures


def load_sources(paths):
    quiz_blocks, quiz_questions, faq_sections = [], [], []
    for p in paths:
        data = json.loads(Path(p).read_text(encoding="utf-8"))
        quiz_blocks += data.get("blocks", [])
        quiz_questions += data.get("questions", [])
        faq_sections += data.get("sections", [])
    return quiz_blocks, quiz_questions, faq_sections


def extract_js_literal(js, name):
    m = re.search(r"const " + name + r" = (\{.*?\n\});", js, re.S)
    if not m:
        raise SystemExit(f"не найден литерал {name} в HTML")
    return json.loads(m.group(1))


def check_sources(rep, paths):
    for p in paths:
        path = Path(p)
        if not rep.check(path.exists(), f"источник существует: {path.name}"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            rep.check(False, f"JSON валиден: {path.name}", str(exc))
            continue
        rep.check(True, f"JSON валиден: {path.name}")
        blob = json.dumps(data, ensure_ascii=False)
        found = CJK.findall(blob)
        rep.check(not found, f"нет иероглифов: {path.name}", f"найдено {found[:5]}")


def check_quiz_integrity(rep, blocks, questions, require_tracks=False):
    ids = [b["id"] for b in blocks]
    rep.check(len(ids) == len(set(ids)), "id блоков уникальны", f"дубли: {[k for k, v in Counter(ids).items() if v > 1]}")
    for b in blocks:
        rep.check(bool(b.get("title")), f"блок {b['id']}: есть title")
        rep.check(b.get("level") in LEVELS, f"блок {b['id']}: уровень корректен", repr(b.get("level")))
        if require_tracks:
            rep.check(bool(b.get("track")), f"блок {b['id']}: есть track")
    known = set(ids)
    bad_ref = sorted({q["block"] for q in questions if q["block"] not in known})
    rep.check(not bad_ref, "все вопросы ссылаются на существующий блок", str(bad_ref))
    empty = sorted(known - {q["block"] for q in questions})
    rep.check(not empty, "у каждого блока есть вопросы", str(empty))
    for i, q in enumerate(questions, 1):
        tag = f"вопрос {i} ({q.get('block')})"
        if not rep.check(len(q.get("options", [])) == 4, f"{tag}: 4 варианта", str(len(q.get("options", [])))):
            continue
        rep.check(isinstance(q.get("correct"), int) and 0 <= q["correct"] < 4, f"{tag}: correct в диапазоне", repr(q.get("correct")))
        rep.check(bool(q.get("why")), f"{tag}: есть разбор")
        rep.check(len(set(q["options"])) == 4, f"{tag}: варианты не дублируются")


def check_faq_integrity(rep, sections, block_ids):
    ids = [s["id"] for s in sections]
    rep.check(len(ids) == len(set(ids)), "id разделов уникальны", f"дубли: {[k for k, v in Counter(ids).items() if v > 1]}")
    missing = sorted(set(block_ids) - set(ids))
    rep.check(not missing, "у каждого блока есть раздел справочника", str(missing))
    for s in sections:
        tag = f"раздел {s['id']}"
        rep.check(bool(s.get("title")), f"{tag}: есть title")
        rep.check(bool(s.get("lead")), f"{tag}: есть lead")
        rep.check(bool(s.get("drill")), f"{tag}: есть практика")
        rep.check(s.get("level") in LEVELS, f"{tag}: уровень корректен", repr(s.get("level")))
        rep.check(len(s.get("terms", [])) >= 5, f"{tag}: минимум 5 терминов", str(len(s.get("terms", []))))
        rep.check(len(s.get("pitfalls", [])) >= 3, f"{tag}: минимум 3 частые ошибки", str(len(s.get("pitfalls", []))))
        for t in s.get("terms", []):
            for key in ("t", "d", "m"):
                rep.check(bool(t.get(key)), f"{tag}/{t.get('t', '?')[:24]}: поле {key} заполнено")


def check_verbatim(rep, page, blocks, questions, sections):
    missing = []

    def probe(text, label):
        if not text:
            return
        variants = (text, json.dumps(text, ensure_ascii=False)[1:-1], html.escape(text))
        if not any(v in page for v in variants):
            missing.append((label, text[:70]))

    for i, q in enumerate(questions, 1):
        probe(q["q"], f"q{i}.q")
        for j, o in enumerate(q["options"]):
            probe(o, f"q{i}.opt{j}")
        probe(q.get("why"), f"q{i}.why")
        probe(q.get("case"), f"q{i}.case")
    for b in blocks:
        probe(b["title"], f"block {b['id']}.title")
        probe(b.get("note"), f"block {b['id']}.note")
    for s in sections:
        probe(s["title"], f"faq {s['id']}.title")
        probe(s["lead"], f"faq {s['id']}.lead")
        probe(s["drill"], f"faq {s['id']}.drill")
        for t in s.get("terms", []):
            for key in ("t", "d", "m"):
                probe(t.get(key), f"faq {s['id']}.{key}")
        for p in s.get("pitfalls", []):
            probe(p, f"faq {s['id']}.pitfall")
    rep.check(not missing, "весь текст источников перенесён дословно", f"пропущено {len(missing)}: {missing[:5]}")


def check_artifact_constraints(rep, page):
    lowered = page.lower()
    for tag in ("<!doctype", "<html", "<head>", "<body>"):
        rep.check(tag not in lowered, f"нет запрещённой обёртки {tag}")
    for pattern in ("http://", "https://", "@font-face", "fetch(", "src=\"//"):
        rep.check(pattern not in page, f"нет внешнего ресурса: {pattern}")
    rep.check("<!--" not in page and "/*" not in page, "нет комментариев в коде")
    title = re.search(r"<title>(.*?)</title>", page)
    rep.check(bool(title), "есть <title>")
    rep.check(bool(re.search(r"^\s*:root\s*\{", page, re.M)), "есть голый :root с полной палитрой")
    rep.check("prefers-color-scheme: dark" in page, "есть блок prefers-color-scheme: dark")
    rep.check(':root:not([data-theme="light"])' in page, "тёмная media защищена от явной светлой темы")
    rep.check(':root[data-theme="dark"]' in page, "есть переопределение для data-theme=dark")
    rep.check("background: var(--paper)" in page or "background: var(--ground)" in page, "body красится токеном")
    rep.check("prefers-reduced-motion: reduce" in page, "уважает prefers-reduced-motion")

    stray = []
    in_tokens = False
    for num, line in enumerate(page.split("\n"), 1):
        stripped = line.strip()
        if re.match(r"^(:root|@media \(prefers-color-scheme)", stripped) or stripped.startswith(':root['):
            in_tokens = True
        if in_tokens and stripped == "}":
            in_tokens = False
        if HEX.search(line) and not stripped.startswith("--"):
            stray.append(num)
    rep.check(not stray, "нет цветовых литералов вне определения токенов", f"строки {stray[:8]}")


def check_js(rep, page, tmp):
    try:
        js = page.split("<script>")[1].split("</script>")[0]
    except IndexError:
        rep.check(False, "в HTML есть блок <script>")
        return None
    tmp.write_text(js, encoding="utf-8")
    for node in ("node", str(Path.home() / ".local/share/node-v24.19.0-darwin-arm64/bin/node")):
        try:
            proc = subprocess.run([node, "--check", str(tmp)], capture_output=True, text=True)
        except FileNotFoundError:
            continue
        rep.check(proc.returncode == 0, "JS проходит node --check", proc.stderr.strip()[:200])
        return js
    rep.note("node не найден — синтаксис JS не проверен")
    return js


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", nargs="+", required=True)
    ap.add_argument("--artifact", default=str(ARTIFACT))
    ap.add_argument("--min-questions", type=int, default=0)
    ap.add_argument("--min-sections", type=int, default=0)
    ap.add_argument("--require-tracks", action="store_true")
    args = ap.parse_args()

    rep = Report()
    print("== источники ==")
    check_sources(rep, args.sources)
    if rep.failures:
        rep.emit()
        print("\nПРОВАЛ: источники невалидны, дальше не идём")
        return 1

    blocks, questions, sections = load_sources(args.sources)
    print("== целостность содержания ==")
    check_quiz_integrity(rep, blocks, questions, require_tracks=args.require_tracks)
    check_faq_integrity(rep, sections, [b["id"] for b in blocks])

    page_path = Path(args.artifact)
    if not rep.check(page_path.exists(), f"артефакт существует: {page_path.name}"):
        rep.emit()
        return 1
    page = page_path.read_text(encoding="utf-8")

    print("== артефакт ==")
    check_artifact_constraints(rep, page)
    js = check_js(rep, page, ROOT / ".check_artifact_tmp.js")

    print("== перенос содержания ==")
    check_verbatim(rep, page, blocks, questions, sections)

    if js:
        try:
            quiz = extract_js_literal(js, "QUIZ_DATA")
            faq = extract_js_literal(js, "FAQ_DATA")
        except (SystemExit, json.JSONDecodeError) as exc:
            rep.check(False, "литералы QUIZ_DATA и FAQ_DATA разбираются как JSON", str(exc)[:160])
        else:
            rep.check(len(quiz["questions"]) == len(questions), "число вопросов в артефакте равно числу в источниках", f"{len(quiz['questions'])} против {len(questions)}")
            rep.check(len(faq["sections"]) == len(sections), "число разделов в артефакте равно числу в источниках", f"{len(faq['sections'])} против {len(sections)}")
            rep.check(len(quiz["questions"]) >= args.min_questions, f"вопросов не меньше {args.min_questions}", str(len(quiz["questions"])))
            rep.check(len(faq["sections"]) >= args.min_sections, f"разделов не меньше {args.min_sections}", str(len(faq["sections"])))
            bad_level = [b["id"] for b in quiz["blocks"] if b.get("level") not in LEVELS]
            rep.check(not bad_level, "у всех блоков В АРТЕФАКТЕ корректен уровень", str(bad_level))
            lost_case = sum(1 for q in questions if q.get("case")) - sum(1 for q in quiz["questions"] if q.get("case"))
            rep.check(lost_case == 0, "сборка не потеряла поля case", f"потеряно {lost_case}")
            src_ids = {b["id"] for b in blocks}
            art_ids = {b["id"] for b in quiz["blocks"]}
            rep.check(src_ids == art_ids, "набор блоков в артефакте совпадает с источниками", str(src_ids ^ art_ids))
            if args.require_tracks:
                tracks = {b.get("track") for b in quiz["blocks"]}
                rep.check(all(tracks) and len(tracks) >= 4, "блоки разложены минимум по 4 трекам", str(sorted(tracks)))
                rep.check("TRACKS" in js, "в JS есть список треков TRACKS")
                untracked = [b["id"] for b in quiz["blocks"] if not b.get("track")]
                rep.check(not untracked, "у всех блоков В АРТЕФАКТЕ проставлен трек", str(untracked))
            by_level = Counter(b["level"] for b in quiz["blocks"])
            by_track = Counter(b.get("track", "—") for b in quiz["blocks"])
            terms = sum(len(s["terms"]) for s in faq["sections"])
            rep.note(f"вопросов {len(quiz['questions'])}, блоков {len(quiz['blocks'])}, разделов {len(faq['sections'])}, терминов {terms}")
            rep.note(f"блоков по уровням: {dict(by_level)}")
            rep.note(f"блоков по трекам: {dict(by_track)}")

    ok = rep.emit()
    tmp = ROOT / ".check_artifact_tmp.js"
    if tmp.exists():
        tmp.unlink()
    print()
    print("ИТОГ: всё чисто" if ok else f"ИТОГ: провалов {len(rep.failures)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
