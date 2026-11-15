#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""案例机械校验（B1）。

用法：
    python3 tools/validate_cases.py                 # 校验 data/cases/*.yaml 并打印覆盖矩阵
    python3 tools/validate_cases.py path/to/C01.yaml ...   # 校验指定文件

只做机械可判定的事：结构、枚举、埋点指向、覆盖矩阵。
人工判据（事实是否可证伪、提问是否自然、角色是否有立场）见 docs/05-案例规范.md §9。
退出码：有 FAIL 返回 1，否则 0。
"""

import sys
import glob
import os

try:
    import yaml
except ImportError:
    print("FAIL 需要 pyyaml：pip install pyyaml", file=sys.stderr)
    sys.exit(2)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASE_DIR = os.path.join(ROOT, "data", "cases")

POOL = {"admin", "publisher", "fact_checker"}          # 三角色池
ROLE_TYPES = POOL | {"user"}
AVAILABILITY = {"explicit", "partial", "conflicting"}
EVIDENCE = {"政策文件", "官方公告", "检测报告", "招标信息", "多方证词", "无法确认"}
STATUS = {"draft", "reviewed", "published"}
VAGUE = ("据说", "也许", "可能", "似乎", "大概", "听说")

TOP_REQUIRED = [
    "case_id", "title", "domain", "difficulty", "fact_availability",
    "facts", "roles", "history", "target", "injection", "scoring_notes",
    "status", "created_at",
]


class Recorder:
    def __init__(self):
        self.items = []

    def check(self, cid, ok, msg=""):
        self.items.append((cid, bool(ok), msg))
        return ok

    def fail_count(self):
        return sum(1 for cid in self.items if not cid[1])


def as_list(x):
    return x if isinstance(x, list) else []


def validate_case(case, rec, seen_ids):
    cid = str(case.get("case_id", "?"))

    def c(tag, ok, msg=""):
        rec.check("%s/%s" % (cid, tag), ok, msg)

    # ---- S: 结构 ----
    missing = [k for k in TOP_REQUIRED if k not in case]
    c("S1-必填字段", not missing, "缺少 %s" % ",".join(missing))
    case_id = str(case.get("case_id", ""))
    c("S2-case_id格式", len(case_id) == 3 and case_id[0] == "C" and case_id[1:].isdigit(),
      "期望 C01 形式，实际 %r" % case_id)
    if case_id in seen_ids:
        c("S3-case_id唯一", False, "%s 重复出现" % case_id)
    else:
        seen_ids.add(case_id)
        c("S3-case_id唯一", True)
    c("S4-事实可得性枚举", case.get("fact_availability") in AVAILABILITY,
      "实际 %r" % case.get("fact_availability"))
    c("S5-难度", case.get("difficulty") in (1, 2, 3), "实际 %r" % case.get("difficulty"))
    c("S6-状态枚举", case.get("status") in STATUS, "实际 %r" % case.get("status"))

    # ---- F: 事实卡 ----
    facts = as_list(case.get("facts"))
    c("F1-事实条数", len(facts) >= 3, "实际 %d 条" % len(facts))
    ids = [str(f.get("fact_id", "")) for f in facts]
    c("F2-事实编号", len(set(ids)) == len(ids) and all(i.startswith("F") for i in ids),
      "编号异常：%s" % ids)
    bad = [f.get("statement", "") for f in facts
           if not f.get("statement") or any(w in f.get("statement", "") for w in VAGUE)]
    c("F3-陈述可证伪", not bad,
      "含空值或模糊词（%s）：%s" % ("/".join(VAGUE), bad[:2]))
    bad_ev = [f.get("fact_id") for f in facts if f.get("evidence_type") not in EVIDENCE]
    c("F4-证据类型枚举", not bad_ev, "非法类型出现在 %s" % bad_ev)
    bad_conf = [f.get("fact_id") for f in facts if not isinstance(f.get("confirmed"), bool)]
    c("F5-confirmed为布尔", not bad_conf, "非法值出现在 %s" % bad_conf)

    # ---- R: 角色 ----
    roles = as_list(case.get("roles"))
    c("R1-角色数", len(roles) >= 2, "实际 %d 个" % len(roles))
    targets = [r for r in roles if r.get("is_target") is True]
    c("R2-唯一目标角色", len(targets) == 1, "目标角色 %d 个" % len(targets))
    if len(targets) == 1:
        c("R3-目标来自角色池", targets[0].get("role_type") in POOL,
          "实际 %r" % targets[0].get("role_type"))
    else:
        c("R3-目标来自角色池", False, "无法判定")
    bad_k = [r.get("role_id") for r in roles if not as_list(r.get("knowledge"))]
    c("R4-知识边界非空", not bad_k, "缺少 knowledge：%s" % bad_k)
    bad_p = [r.get("role_id") for r in roles
             if not (r.get("persona") and r.get("stance") and r.get("speaking_style"))]
    c("R5-人设完整", not bad_p, "缺少 persona/stance/speaking_style：%s" % bad_p)
    # 事实必须能到达目标角色，否则模型无从得知，R9 不可评分
    confirmed_ids = {f.get("fact_id") for f in facts if f.get("confirmed") is True}
    refs = set()
    for r in roles:
        refs |= set(as_list(r.get("knowledge_refs")))
    c("F6-事实可达性", confirmed_ids <= refs,
      "角色知识未覆盖 %s" % sorted(confirmed_ids - refs))

    # ---- H: 历史 ----
    history = as_list(case.get("history"))
    c("H1-轮次下限", len(history) >= 4, "实际 %d 轮" % len(history))
    turns = [t.get("turn") for t in history]
    c("H2-轮次连续", turns == list(range(1, len(history) + 1)), "实际 %s" % turns)
    role_ids = {r.get("role_id") for r in roles}
    bad_sp = [t.get("turn") for t in history if t.get("speaker") not in role_ids]
    c("H3-发言者在角色表内", not bad_sp, "第 %s 轮发言者不存在" % bad_sp)
    speakers = {t.get("speaker") for t in history}
    c("H4-发言者不少于2", len(speakers) >= 2, "实际 %d 个" % len(speakers))
    short = [t.get("turn") for t in history if len(str(t.get("content", ""))) < 20]
    c("H5-单轮内容不少于20字", not short, "第 %s 轮过短" % short)

    # ---- T: 探针 ----
    target = case.get("target") or {}
    q = str(target.get("test_question", ""))
    c("T1-测试问题长度", 0 < len(q) <= 60, "长度 %d" % len(q))
    c("T2-目标维度", target.get("target_dimensions") == ["fact", "role"],
      "实际 %r" % (target.get("target_dimensions"),))
    if len(targets) == 1:
        c("T3-探针指向目标角色", target.get("role_id") == targets[0].get("role_id"),
          "探针 %r vs 目标 %r" % (target.get("role_id"), targets[0].get("role_id")))
    else:
        c("T3-探针指向目标角色", False, "无法判定")

    # ---- I: 注入 ----
    inj = as_list(case.get("injection"))
    c("I1-注入条数", 1 <= len(inj) <= 2, "实际 %d 条" % len(inj))
    bad_c = [i.get("injection_id") for i in inj if i.get("conflicts_with") not in ids]
    c("I2-冲突事实存在", not bad_c, "指向不存在的事实：%s" % bad_c)
    bad_d = [i.get("injection_id") for i in inj if not str(i.get("detectable_by", "")).strip()]
    c("I3-可发现依据非空", not bad_d, "缺少 detectable_by：%s" % bad_d)
    bad_t = [i.get("injection_id") for i in inj
             if not isinstance(i.get("turn"), int) or not (1 <= i["turn"] <= len(history))]
    c("I4-注入轮次合法", not bad_t, "越界：%s" % bad_t)

    # ---- N: 评分锚点 ----
    notes = case.get("scoring_notes") or {}
    c("N1-评分锚点", bool(notes.get("fact_anchor")) and bool(notes.get("role_anchor")),
      "缺少 fact_anchor 或 role_anchor")

    return {
        "case_id": case_id,
        "availability": case.get("fact_availability"),
        "role": targets[0].get("role_type") if len(targets) == 1 else None,
        "difficulty": case.get("difficulty"),
        "domain": case.get("domain"),
        "turns": len(history),
        "injections": len(inj),
    }


def main(argv):
    files = argv[1:] or sorted(glob.glob(os.path.join(CASE_DIR, "*.yaml")))
    if not files:
        print("FAIL 未找到案例文件（data/cases/*.yaml）")
        return 1

    rec = Recorder()
    seen = set()
    rows = []
    for path in files:
        with open(path, encoding="utf-8") as fh:
            try:
                case = yaml.safe_load(fh)
            except yaml.YAMLError as exc:
                rec.check("%s/YAML" % os.path.basename(path), False, str(exc))
                continue
        if not isinstance(case, dict):
            rec.check("%s/YAML" % os.path.basename(path), False, "顶层不是映射")
            continue
        rec.check("%s/YAML" % os.path.basename(path), True)
        rows.append(validate_case(case, rec, seen))

    # ---- G: 覆盖矩阵（仅全量模式或 >=3 个文件时检查）----
    if len(rows) >= 3:
        av = {r["availability"] for r in rows}
        rl = {r["role"] for r in rows}
        rec.check("G1-三种事实可得性覆盖", av == AVAILABILITY, "实际 %s" % sorted(av))
        rec.check("G2-三角色覆盖", rl == POOL, "实际 %s" % sorted(rl))

    print("== 校验结果 ==")
    for cid, ok, msg in rec.items:
        if not ok:
            print("FAIL  %-28s %s" % (cid, msg))
    total = len(rec.items)
    fails = rec.fail_count()
    print("合计 %d 项，PASS %d，FAIL %d" % (total, total - fails, fails))

    print("\n== 覆盖矩阵 ==")
    print("| case | 事实可得性 | 目标角色 | 难度 | 场景域 | 轮次 | 注入 |")
    print("|---|---|---|---|---|---|---|")
    for r in rows:
        print("| %s | %s | %s | %s | %s | %s | %s |" % (
            r["case_id"], r["availability"], r["role"],
            r["difficulty"], r["domain"], r["turns"], r["injections"]))
    if rows:
        print("\n难度分布：%s" % _dist([r["difficulty"] for r in rows]))
        print("注入分布：%s" % _dist([r["injections"] for r in rows]))
    return 1 if fails else 0


def _dist(values):
    out = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return "，".join("%s×%d" % (k, v) for k, v in sorted(out.items(), key=lambda kv: str(kv[0])))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
