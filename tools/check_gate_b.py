#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 B 门禁自检（B1–B4 产物）。

检查对象：docs/05–09、prereg/prereg_v1.2.json、data/cases/*.yaml、data/prompts/AUDIT.md。
判据来自 design/P0-总设计提示词.md §8 门禁要求：每条判据必须可机械验证或给出可复核证据。

用法：
    python3 tools/check_gate_b.py            # 打印明细
    python3 tools/check_gate_b.py --quiet    # 只打印汇总与失败项
退出码：有 FAIL 时为 1。
"""

import argparse
import json
import os
import re
import subprocess
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASE_DIR = os.path.join(ROOT, "data", "cases")
CHECKS = []


def check(cid, desc, ok, detail=""):
    CHECKS.append((cid, desc, bool(ok), detail))


def read(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
        return fh.read()


def grep_count(text, pattern):
    return len(re.findall(pattern, text))


def load_cases():
    out = {}
    for fn in sorted(os.listdir(CASE_DIR)):
        if fn.endswith(".yaml"):
            with open(os.path.join(CASE_DIR, fn), encoding="utf-8") as fh:
                out[fn[:-5]] = yaml.safe_load(fh)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    # ---------- B1：案例规范与案例集 ----------
    d05 = read("docs/05-案例规范.md")
    check("B1.1", "docs/05 存在且含四条硬约束", all(
        k in d05 for k in ("四条硬约", "诱导", "单目标角色", "可证伪")))
    check("B1.2", "docs/05 含三种事实可得性定义", all(
        k in d05 for k in ("explicit", "partial", "conflicting")))
    check("B1.3", "docs/05 含覆盖矩阵且总数为 20", "20" in d05 and "覆盖矩阵" in d05)

    cases = load_cases()
    check("B1.4", "案例文件恰为 20 个", len(cases) == 20, "实际 %d" % len(cases))

    roles, avail, diff, inj = {}, {}, {}, {}
    speakers_ok = turns_ok = target_ok = 0
    for cid, c in cases.items():
        tg = [r for r in c["roles"] if r.get("is_target")]
        rt = tg[0]["role_type"] if tg else "?"
        roles[rt] = roles.get(rt, 0) + 1
        avail[c["fact_availability"]] = avail.get(c["fact_availability"], 0) + 1
        diff[c["difficulty"]] = diff.get(c["difficulty"], 0) + 1
        n_inj = len(c.get("injection") or [])
        inj[n_inj] = inj.get(n_inj, 0) + 1
        spk = {t["speaker"] for t in c["history"]}
        if len(spk) >= 2:
            speakers_ok += 1
        if 4 <= len(c["history"]) <= 6:
            turns_ok += 1
        tg = [r for r in c["roles"] if r.get("is_target")]
        if len(tg) == 1:
            target_ok += 1
    check("B1.5", "每案例 ≥2 名发言者", speakers_ok == len(cases), "%d/%d" % (speakers_ok, len(cases)))
    check("B1.6", "每案例历史 4–6 轮", turns_ok == len(cases), "%d/%d" % (turns_ok, len(cases)))
    check("B1.7", "每案例恰 1 个目标角色", target_ok == len(cases), "%d/%d" % (target_ok, len(cases)))
    check("B1.8", "角色分布 7/7/6", roles == {"admin": 7, "publisher": 7, "fact_checker": 6}, str(roles))
    check("B1.9", "可得性分布 7/7/6",
          avail == {"explicit": 7, "partial": 7, "conflicting": 6}, str(avail))
    check("B1.10", "难度分布 5/10/5", diff == {1: 5, 2: 10, 3: 5}, str(diff))
    check("B1.11", "注入条数分布 10/10", inj == {1: 10, 2: 10}, str(inj))
    check("B1.12", "所有案例 status 均为 draft 或 published",
          all(c.get("status") in ("draft", "published") for c in cases.values()))

    # ---------- B2：提示与等价性 ----------
    d06 = read("docs/06-提示设计.md")
    check("B2.1", "docs/06 声明 p2 版本", "p2" in d06 and "v2.0" in d06)
    check("B2.2", "docs/06 含七块结构", "七个块" in d06)
    check("B2.3", "docs/06 说明共享块逐字相同", "逐字相同" in d06 and "共享" in d06)
    check("B2.4", "docs/06 说明 few-shot 两版同内容", "示例" in d06 and "命题" in d06)
    has_measured_tok = ("tiktoken" in d06 and "o200k_base" in d06 and "代理" in d06)
    has_pending_tok = ("[待实测]" in d06 and "tokenizer" in d06)
    check("B2.5", "docs/06 的 token 口径可核查（实算且声明代理，或标待实测）",
          has_measured_tok or has_pending_tok)
    check("B2.6", "docs/06 无『token 差 < 15%』式未测断言",
          "token 长度差 < 15%" not in d06 and "token 差 < 15%" not in d06)

    audit = read("data/prompts/AUDIT.md")
    check("B2.7", "审计表覆盖全部案例", all(cid in audit for cid in cases))
    check("B2.8", "审计表无缺失单元", "缺失 0" in audit or "| 0 |" in audit)
    check("B2.9", "审计表共享块一致列全为『是』", "**否**" not in audit)

    # ---------- B3：评分量表 ----------
    d07 = read("docs/07-评分量表.md")
    check("B3.1", "量表为两维五级 + null", all(k in d07 for k in ("1–5", "null", "两维")))
    check("B3.2", "含公式 x=(s−1)/4 与等权 t", "(s − 1) / 4" in d07 or "(s−1)/4" in d07)
    check("B3.3", "两遍评分流程完整（校准/裁定/聚合）",
          all(k in d07 for k in ("校准", "裁定", "聚合", "两遍")))
    check("B3.4", "一致性指标为 κ 与 ICC(2,1)",
          "二次加权 κ" in d07 and "ICC(2,1)" in d07 or ("κ" in d07 and "ICC" in d07))
    check("B3.5", "含正反例校准集", "正反例" in d07 and "C01" in d07)
    check("B3.6", "声明未对任何模型回复评分", "尚未对任何模型回复评分" in d07)
    check("B3.7", "禁 scipy", "scipy" in d07)

    # ---------- B4：预注册与运行协议 ----------
    import glob as _glob
    _vers = sorted(_glob.glob(os.path.join(ROOT, "prereg", "prereg_v*.json")),
                   key=lambda p: [int(x) for x in re.findall(r"\d+", os.path.basename(p))])
    prereg_path = os.path.relpath(_vers[-1], ROOT) if _vers else "prereg/prereg_v1.2.json"
    check("B4.1", "预注册存在且取最新版", os.path.exists(os.path.join(ROOT, prereg_path)), prereg_path)
    pre = json.load(open(os.path.join(ROOT, prereg_path), encoding="utf-8"))
    d = pre["scope"]["design"]
    check("B4.2", "设计为 20×2×3=120", d["cases"] == 20 and d["repeats"] == 3
          and pre["scope"]["planned_runs"] == 120)
    check("B4.3", "两遍独立评分写入预注册（raters=1, passes=2）",
          pre["rating"].get("raters") == 1 and pre["rating"].get("rater_passes") == 2
          and pre["rating"].get("inter_rater", {}).get("planned") is False)
    check("B4.4", "提示版本 p2 + 1 个 few-shot", d["prompt_version"] == "p2"
          and d["few_shot_examples"] == 1)
    check("B4.5", "amendments 含 M1 且 post_hoc=false",
          any(a.get("id") == "M1" and a.get("post_hoc") is False for a in pre["amendments"]))
    check("B4.6", "分析规则：案例重采样 + B=1000 + seed 20261017",
          pre["analysis"]["primary"]["interval"]["resample_unit"] == "case"
          and pre["analysis"]["primary"]["interval"]["B"] == 1000
          and pre["analysis"]["primary"]["interval"]["seed"] == 20261017)
    check("B4.7", "禁止项写入预注册",
          all(x in pre["analysis"]["primary"]["forbidden"]
              for x in ("按 run 重采样", "scipy 依赖", "对缺失值做任何填补")))
    r = subprocess.run([sys.executable, "tools/compute_prereg_hash.py", prereg_path, "--check"],
                       cwd=ROOT, capture_output=True, text=True)
    check("B4.8", "预注册最新版哈希校验 PASS", r.returncode == 0, r.stdout.strip())

    d09 = read("docs/09-运行协议.md")
    check("B4.9", "协议写 120 条 run / 240 条评分",
          "120 条 `run`" in d09 and "240 条" in d09)
    check("B4.10", "协议含幂等键与重试策略",
          all(k in d09 for k in ("幂等键", "timeout=60s", "max_retries", "auth_error")))
    check("B4.11", "协议 DoD 含 prompt_sha256 与评分 active 行约束",
          "prompt_sha256" in d09 and "active" in d09)
    check("B4.12", "协议未声称已执行", "尚未执行任何运行" in d09)

    # ---------- 一致性：文档数字不打架 ----------
    d08 = read("docs/08-预注册分析方案.md")
    check("B4.13", "docs/08 与预注册一致（30×? → 120/3/双评）",
          "120" in d08 and "3 次" in d08 and "两遍" in d08)
    stale = []
    for p in ("docs/03-需求规格.md", "docs/04-效度与风险.md", "docs/07-评分量表.md",
              "docs/08-预注册分析方案.md", "docs/09-运行协议.md"):
        t = read(p)
        # 去掉版本记录行后，不允许再出现"单评分者设计/单评分者（L3）"等现行结论
        t = "\n".join(ln for ln in t.splitlines() if "版本记录" not in ln and "~~" not in ln)
        if "单评分者（L3 已声明）" in t or "单评分者设计" in t:
            stale.append(p)
    check("B4.14", "无残留『单评分者』现行结论", not stale, "、".join(stale))

    # ---------- 汇总 ----------
    fails = [c for c in CHECKS if not c[2]]
    if not args.quiet:
        for cid, desc, ok, detail in CHECKS:
            print("%-6s %s  %s%s" % (cid, "PASS" if ok else "FAIL", desc,
                                     ("  [%s]" % detail) if detail else ""))
    print("\n合计 %d 项，PASS %d，FAIL %d" % (len(CHECKS), len(CHECKS) - len(fails), len(fails)))
    for cid, desc, ok, detail in fails:
        print("  FAIL %-6s %s  %s" % (cid, desc, detail))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
