#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 A 门禁自动校验（P0 §5 A1–A4 + §8 输出协议）。

只做"机器能一眼判定"的检查：编号是否齐全、表格是否有空格、必备章节是否存在、
无来源数字是否被标注。语义质量（写得对不对、有没有真读懂申报表）不由本脚本判定，
由人复核 —— 脚本通过 ≠ 门禁通过，这一点写在输出的第一行，防止自欺。

用法：
    python3 tools/check_gate_a.py            # 全部检查，有失败则退出码 1
    python3 tools/check_gate_a.py --quiet    # 只打印失败项
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

RESULTS: list[tuple[str, str, str]] = []  # (检查ID, 状态 PASS/FAIL, 说明)


def read(name: str) -> str:
    p = DOCS / name
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8")


def check(cid: str, ok: bool, msg: str) -> None:
    RESULTS.append((cid, "PASS" if ok else "FAIL", msg))


def ids_present(text: str, pattern: str, ids: list[str], label: str) -> None:
    missing = [i for i in ids if not re.search(pattern.format(re.escape(i)), text)]
    check(label, not missing, f"缺少 {', '.join(missing)}" if missing else f"{len(ids)} 条齐全")


# ---------------------------------------------------------------- 01 需求基线
def check_01() -> None:
    t = read("01-需求基线.md")
    check("A1-存在", bool(t), "docs/01-需求基线.md")
    if not t:
        return
    ids_present(t, r"###\s*R{}\b", [f"{i}" for i in range(1, 18)], "A1-R1..R17")
    ids_present(t, r"\|\s*C{}\s*\|", [f"{i}" for i in range(1, 8)], "A1-C1..C7")
    ids_present(t, r"\|\s*N{}\s*\|", [f"{i}" for i in range(1, 6)], "A1-N1..N5")
    ids_present(t, r"\|\s*L{}\s*\|", [f"{i}" for i in range(1, 5)], "A1-L1..L4")
    terms = set(re.findall(r"\|\s*T(\d+)\s*\|", t))
    check("A1-术语≥15", len(terms) >= 15, f"术语 {len(terms)} 条")
    # 每个术语必须同时有"可操作定义"和"反例"两列内容（该表 4 列：#, 术语, 定义, 反例）
    bad_rows = [
        ln for ln in t.splitlines()
        if re.match(r"\|\s*T\d+\s*\|", ln) and (ln.count("|") < 5 or "|  |" in ln or "||" in ln)
    ]
    check("A1-术语有反例", not bad_rows, f"{len(bad_rows)} 行缺列" if bad_rows else "定义/反例两列齐全")
    qs = set(re.findall(r"\|\s*Q(\d+)\s*\|", t))
    check("A1-模糊点≥8", len(qs) >= 8, f"模糊点 {len(qs)} 条")
    check("A1-差异登记≥3", len(set(re.findall(r"D(\d+)", t))) >= 3, "原文↔P0 差异登记")
    check("A1-声明'不是已完成'", ("待实现" in t) or ("计划" in t) or ("未执行" in t),
          "文档须区分计划与已执行（§9 禁令第 9 条）")


# ---------------------------------------------------------------- 03 需求规格
def check_03() -> None:
    t = read("03-需求规格.md")
    check("A3-存在", bool(t), "docs/03-需求规格.md")
    if not t:
        return
    for label, pat, least in [
        ("A3-US≥10", r"\|\s*US-\d+", 10),
        ("A3-UC≥7", r"###\s*UC-\d+", 7),
        ("A3-ADR≥10", r"###\s*ADR-\d+", 10),
        ("A3-FR≥20", r"\|\s*FR-\d+\s*\|", 20),
        ("A3-NFR≥8", r"\|\s*NFR-\d+", 8),
    ]:
        n = len(re.findall(pat, t))
        check(label, n >= least, f"实际 {n}")

    # RTM：17 行，每行 5 列且无空单元格
    rtm = re.search(r"##\s*7\.\s*需求追踪矩阵.*?\n(.*?)\n##\s", t, re.S)
    if not rtm:
        check("A3-RTM存在", False, "未找到 RTM 章节")
        return
    body = rtm.group(1).split("**覆盖率自检**")[0]
    rows = [ln for ln in body.splitlines() if ln.strip().startswith("|") and "---" not in ln]
    rows = [r for r in rows if not re.search(r"需求\s*\|", r)]  # 去表头
    check("A3-RTM行数=17", len(rows) == 17, f"实际 {len(rows)} 行")
    empty = []
    for r in rows:
        cells = [c.strip() for c in r.strip().strip("|").split("|")]
        if len(cells) < 5 or any(c in ("", "-", "—", "TBD", "待定") for c in cells):
            empty.append(r[:40])
    check("A3-RTM无空格", not empty, f"{len(empty)} 行有空单元格" if empty else "85 格全非空")
    r_nums = sorted({int(m) for r in rows for m in re.findall(r"R(\d+)", r)})
    check("A3-RTM覆盖R1..R17", r_nums == list(range(1, 18)), f"实际覆盖 {r_nums}")
    check("A3-预算320h", "320" in t, "工时预算表")
    check("A3-降级顺序E1..E4", all(k in t for k in ("E-1", "E-2", "E-3", "E-4")), "降级项 E-1..E-4")
    check("A3-不降级清单", ("不可砍" in t) or ("不得降级" in t), "R1–R17 不进入降级清单")


# ---------------------------------------------------------------- 04 效度与风险
def check_04() -> None:
    t = read("04-效度与风险.md")
    check("A4-存在", bool(t), "docs/04-效度与风险.md")
    if not t:
        return
    cats = {
        "构念": "构念效度",
        "内部": "内部效度",
        "统计": "统计效度",
        "外部": "外部效度",
        "评分者": "评分者效度",
    }
    for short, full in cats.items():
        check(f"A4-覆盖{short}效度", full in t, full)
    ts = set(re.findall(r"T-\d{2}", t))
    check("A4-威胁≥10", len(ts) >= 10, f"T-xx {len(ts)} 条")
    rks = set(re.findall(r"RK-\d{2}", t))
    check("A4-工程风险≥5", len(rks) >= 5, f"RK {len(rks)} 条")
    for col in ("落地位置", "残余风险", "对策"):
        check(f"A4-列:{col}", col in t, f"每条威胁须有「{col}」")
    check("A4-成本列", "工时" in t or "h)" in t, "对策成本（小时）")
    check("A4-未执行不写已落实", "已落实" not in t, "禁止把计划写成已完成")


# ---------------------------------------------------------------- 02 文献与原理
def check_02() -> None:
    t = read("02-文献与原理.md")
    check("A2-存在", bool(t), "docs/02-文献与原理.md")
    if not t:
        return
    cards = len(re.findall(r"###\s*L\d", t))
    check("A2-文献卡≥5", cards >= 5, f"文献卡 {cards} 张")
    for key in ("AutoGen", "AgentBench", "G-Eval", "RAIDEN", "RMTBench"):
        check(f"A2-含{key}", key in t, key)
    n_reuse = t.count("不可照搬")
    check("A2-不可照搬≥3", n_reuse >= 3, f"出现 {n_reuse} 次（需 ≥3 处独立论证）")
    check("A2-核实台账", "核实台账" in t or "待核实清单" in t, "未核实数字必须集中登记")
    # 若引用了具体数字，必须要么紧跟来源，要么带 [待核实]
    suspect = []
    for ln in t.splitlines():
        if "[待核实]" in ln or "§" in ln:
            continue
        for m in re.finditer(r"(?<![\d.])\d+\.\d+\s*(×|%|个百分点)", ln):
            suspect.append((m.group(0), ln[:60]))
    check("A2-数字须可溯源", not suspect,
          f"{len(suspect)} 处裸数字需标注来源或[待核实]：{suspect[:3]}" if suspect else "无裸数字")
    check("A2-差异化声明", "差异化" in t or "本课题不同" in t, "与已有工作的区别声明")


def main() -> int:
    quiet = "--quiet" in sys.argv
    DOCS.mkdir(parents=True, exist_ok=True)
    for fn in (check_01, check_02, check_03, check_04):
        fn()

    fails = [r for r in RESULTS if r[1] == "FAIL"]
    if not quiet:
        print("注：本脚本只检查「编号/结构/表格完备性」，不检查语义正确性；脚本 PASS ≠ 门禁 PASS。\n")
        print(f"{'检查项':<26}{'结果':<8}说明")
        print("-" * 78)
        for cid, st, msg in RESULTS:
            print(f"{cid:<26}{st:<8}{msg}")
        print("-" * 78)
    print(f"合计 {len(RESULTS)} 项，PASS {len(RESULTS) - len(fails)}，FAIL {len(fails)}")
    if fails:
        print("\n失败项：")
        for cid, _, msg in fails:
            print(f"  - {cid}: {msg}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
