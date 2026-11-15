#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""信息等价性审计（B2，p2 版：含阅读说明、示例、字段标签）。

核心判据（机械）：
1. 两个变体的「命题单元集合」必须完全相同且 100% 出现；
2. 共享块（阅读说明 / 任务要求 / 需要回复的消息 / 输出要求）必须逐字相同；
3. 示例块的命题内容（角色、历史、问题、回复）必须两版一致，仅格式不同；
4. 无泄漏：不得出现事实编号、评分锚点、注入标记等字段名。

用法：
    python3 tools/audit_equivalence.py            # 审计全部案例，写 data/prompts/AUDIT.md
    python3 tools/audit_equivalence.py --stdout   # 只打印不写文件
"""

import argparse
import os
import re
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_prompt as rp  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASE_DIR = os.path.join(ROOT, "data", "cases")
OUT = os.path.join(ROOT, "data", "prompts", "AUDIT.md")
SHARED = ("guide", "task", "question", "tail")

try:  # 可选：有 tiktoken 时按真实 BPE 计 token，否则整表标 [待实测]
    import tiktoken
    ENC = tiktoken.get_encoding(os.environ.get("TOKENIZER_ENCODING", "o200k_base"))
except Exception:  # pragma: no cover
    tiktoken, ENC = None, None

CJK = re.compile(r"[\u4e00-\u9fff]")
WORD = re.compile(r"[A-Za-z0-9]+")
FORBIDDEN = [r"\bF\d+\b", r"scoring_notes", r"fact_anchor", r"role_anchor",
             r"\binjection\b", r"\bstatus\b", r"confirmed", r"case_id"]


def ntokens(text):
    """None 表示无 tokenizer，调用方须标 [待实测]，不得用字符数冒充。"""
    if ENC is None:
        return None
    return len(ENC.encode(text))


def norm(s):
    return re.sub(r"\s+", "", str(s))


def case_units(case):
    t = [r for r in case["roles"] if r.get("is_target")][0]
    u = [("角色名", t["name"]), ("身份", t["persona"]), ("立场", t["stance"]),
         ("说话风格", t["speaking_style"])]
    for i, k in enumerate(t["knowledge"], 1):
        u.append(("掌握信息%d" % i, k))
    for h in case["history"]:
        u.append(("历史第%d轮" % h["turn"], h["content"]))
    u.append(("测试问题", case["target"]["test_question"].strip()))
    return u


def example_units():
    ex = rp.EXAMPLE_CASE
    t = [r for r in ex["roles"] if r.get("is_target")][0]
    u = [("示例角色名", t["name"]), ("示例身份", t["persona"]),
         ("示例立场", t["stance"]), ("示例说话风格", t["speaking_style"])]
    for i, k in enumerate(t["knowledge"], 1):
        u.append(("示例掌握信息%d" % i, k))
    for h in ex["history"]:
        u.append(("示例历史第%d轮" % h["turn"], h["content"]))
    u.append(("示例问题", ex["test_question"]))
    u.append(("示例回复", ex["reply"]))
    return u


def audit_case(case):
    bf, bs = rp.blocks(case, "flat"), rp.blocks(case, "struct")
    flat, struct = rp.render(case, "flat"), rp.render(case, "struct")
    n_flat, n_struct = norm(flat), norm(struct)

    shared_ok = {k: (bf[k] == bs[k]) for k in SHARED}
    rows, missing = [], 0
    for label, text in case_units(case) + example_units():
        key = norm(text)
        in_f, in_s = key in n_flat, key in n_struct
        if not (in_f and in_s):
            missing += 1
        rows.append((label, in_f, in_s))

    leak = []
    for pat in FORBIDDEN:
        for name, body in (("flat", flat), ("struct", struct)):
            m = re.search(pat, body)
            if m:
                leak.append("%s:%s" % (name, m.group(0)))
    return {
        "case_id": case["case_id"],
        "units": len(rows), "missing": missing, "rows": rows, "leak": leak,
        "shared_ok": shared_ok,
        "flat_chars": len(flat), "struct_chars": len(struct),
        "flat_tok": ntokens(flat), "struct_tok": ntokens(struct),
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--stdout", action="store_true")
    args = ap.parse_args(argv)

    ids = sorted(f[:-5] for f in os.listdir(CASE_DIR) if f.endswith(".yaml"))
    results = []
    for cid in ids:
        with open(os.path.join(CASE_DIR, "%s.yaml" % cid), encoding="utf-8") as fh:
            results.append(audit_case(yaml.safe_load(fh)))

    lines = ["# 信息等价性审计表（自动生成 · %s）" % rp.PROMPT_VERSION, "",
             "> 由 `python3 tools/audit_equivalence.py` 生成；判据见 `docs/06-提示设计.md` §4。",
             "> 命题单元（含示例块）必须 100% 出现在两个变体中；共享块必须逐字相同；",
             "> 允许的差异只有：分节标签、轮次序号、列表符号、断句。", "",
             "## 1. 单元覆盖与长度", "",
             "| 案例 | 命题单元 | 缺失 | 共享块一致 | flat 字符 | struct 字符 | 字符差 | flat token | struct token | token 差 |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    fail = 0
    for r in results:
        dch = 100.0 * (r["struct_chars"] - r["flat_chars"]) / r["flat_chars"]
        ok_shared = all(r["shared_ok"].values())
        if r["missing"] or r["leak"] or not ok_shared:
            fail += 1
        if r["flat_tok"] is None:
            tcell = "| [待实测] | [待实测] | [待实测] |"
        else:
            dtok = 100.0 * (r["struct_tok"] - r["flat_tok"]) / r["flat_tok"]
            tcell = "| %d | %d | %+.1f%% |" % (r["flat_tok"], r["struct_tok"], dtok)
        lines.append("| %s | %d | %d | %s | %d | %d | %+.1f%% " % (
            r["case_id"], r["units"], r["missing"], "是" if ok_shared else "**否**",
            r["flat_chars"], r["struct_chars"], dch) + tcell)

    lines += ["", "## 2. 逐单元核验", ""]
    for r in results:
        bad = [lb for lb, a, b in r["rows"] if not (a and b)]
        lines.append("- **%s**：%d 个单元 %s%s%s" % (
            r["case_id"], r["units"],
            "全部命中" if not bad else "缺失 %d 个（%s）" % (len(bad), "、".join(bad[:5])),
            "" if all(r["shared_ok"].values()) else "；共享块不一致",
            "" if not r["leak"] else "；**泄漏标记 %s**" % "、".join(r["leak"])))

    lines += ["", "## 3. 结论", ""]
    lines.append("全部案例：命题单元集合等价，共享块逐字一致，无评分真值泄漏。"
                 if fail == 0 else
                 "**存在不通过项：%d 个案例需要修正，不得进入 D 阶段。**" % fail)
    if ENC is None:
        lines += ["", "> 字符数为精确值。token 差 **[待实测]**：当前解释器无 tiktoken，",
                  "> 需在装有 tiktoken 的环境（`conda activate deeplearning`）重跑本脚本后补入。"]
    else:
        lines += ["", "> token 数由 tiktoken `%s` 编码器计数（`TOKENIZER_ENCODING` 可覆盖）。"
                  % os.environ.get("TOKENIZER_ENCODING", "o200k_base"),
                  "> 该编码器是对目标 API 分词的**代理**，不是目标模型的分词器；论文中须写明代理口径。"]

    report = "\n".join(lines) + "\n"
    if args.stdout:
        print(report)
    else:
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        with open(OUT, "w", encoding="utf-8") as fh:
            fh.write(report)
        print("已写入 %s" % OUT)

    print("\n== 摘要 ==")
    for r in results:
        tok = "" if r["flat_tok"] is None else "  flat %d tok / struct %d tok (%+.1f%%)" % (
            r["flat_tok"], r["struct_tok"],
            100.0 * (r["struct_tok"] - r["flat_tok"]) / r["flat_tok"])
        print("%s 单元 %d 缺失 %d 泄漏 %d 共享块 %s  flat %d 字 / struct %d 字 (%+.1f%%)%s" % (
            r["case_id"], r["units"], r["missing"], len(r["leak"]),
            "一致" if all(r["shared_ok"].values()) else "**不一致**",
            r["flat_chars"], r["struct_chars"],
            100.0 * (r["struct_chars"] - r["flat_chars"]) / r["flat_chars"], tok))
    print("合计 %d 个案例，不通过 %d 个" % (len(results), fail))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
