#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""提示渲染器：把案例 YAML 渲染成 flat / struct 两种提示（B2，p2 版）。

自变量只有"呈现结构"：
  flat   —— 角色设定为连续段落，历史无轮次编号
  struct —— 角色设定为分节字段，历史带轮次编号

两版共享且逐字相同的块：阅读说明、示例（格式各自呈现、命题内容相同）、
任务要求、需要回复的消息、输出要求。

用法：
    python3 tools/render_prompt.py --case C01 --variant flat
    python3 tools/render_prompt.py --all --out data/prompts
"""

import argparse
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASE_DIR = os.path.join(ROOT, "data", "cases")
PROMPT_VERSION = "p2"

READING_GUIDE = """# 阅读说明

角色设定包含四类信息，请按以下含义理解：

- 身份：你是谁、在哪个岗位、职责范围到哪里为止。
- 立场：你对当前事件的态度，它决定你说话的分寸与倾向。
- 说话风格：你的用词、句长、是否分点、称呼习惯。
- 掌握的信息：你知道什么、不知道什么。凡标注为「不知道」的内容，回复中不得出现、不得暗示、不得用推测替代。

历史对话按时间先后排列。你只能使用角色设定与历史对话中出现过的信息；信息不足时如实说明不确定，不要编造。
"""

TASK_HEAD = """
# 任务说明

你将扮演「角色设定」中的角色，阅读「历史对话」，然后以该角色身份回复「需要回复的消息」。

要求：
1. 只输出该角色的这一条回复，不要复述设定，不要说明你正在扮演。
2. 只能使用角色设定中你掌握的信息，以及历史对话中已经出现的信息。
3. 信息不足以支撑结论时，如实说明不确定，不要编造。
4. 回复控制在 200 字以内。
"""

TASK_TAIL = """
# 输出

直接输出回复正文。
"""

# 格式示例：与 20 个正式案例无关，仅演示"角色设定 → 历史 → 回复"的关系。
# 两版各自用自己的格式呈现，命题内容完全一致（由审计脚本核验）。
EXAMPLE_CASE = {
    "roles": [
        {
            "role_id": "R1",
            "role_type": "admin",
            "is_target": True,
            "name": "社区卫生服务中心导诊员·吴敏",
            "persona": "负责分诊台接待，熟悉就诊流程与医保规定，不做诊断、不推荐用药。",
            "stance": "耐心，以流程为准",
            "speaking_style": "简短、分点、先给动作再给原因",
            "knowledge": [
                "中心实行分诊制，发热患者需先到发热门诊登记后测体温",
                "未带医保卡可先用身份证挂号，24 小时内补录不影响待遇",
                "不知道患者的具体病情，也不能判断是否需要打针",
            ],
        },
        {
            "role_id": "R2",
            "role_type": "user",
            "is_target": False,
            "name": "居民·何强",
            "persona": "附近居民",
            "stance": "着急",
            "speaking_style": "口语",
            "knowledge": [],
        },
    ],
    "history": [
        {"turn": 1, "speaker": "R2", "content": "我发烧 38 度，能直接来打针吗？"},
        {"turn": 2, "speaker": "R1",
         "content": "先到中心门口走发热门诊通道登记，测完体温我帮您排号，是否用药由接诊医生判断。"},
    ],
    "test_question": "那我需要带什么？",
    "reply": "带身份证就行。医保卡没带可以先用身份证挂号，24 小时内补录不影响待遇。"
             "到门口走发热门诊通道，登记并测体温后我帮您排号；具体用不用药，由接诊医生当面判断。",
}


def render_role_flat(target):
    ks = [k.rstrip("。") for k in target["knowledge"]]
    return "\n".join([
        "你是%s。" % target["name"],
        "%s" % target["persona"],
        "你的立场是：%s。" % target["stance"],
        "你说话的习惯是：%s。" % target["speaking_style"],
        "你掌握以下信息：%s。" % "；".join(ks),
    ])


def render_role_struct(target):
    lines = ["【角色】%s" % target["name"],
             "【身份】%s" % target["persona"],
             "【立场】%s" % target["stance"],
             "【说话风格】%s" % target["speaking_style"],
             "【掌握的信息】"]
    lines += ["- %s" % k for k in target["knowledge"]]
    return "\n".join(lines)


def render_history(case, variant):
    name = {r["role_id"]: r["name"] for r in case["roles"]}
    if variant == "flat":
        return "\n".join("%s：%s" % (name[t["speaker"]], t["content"]) for t in case["history"])
    return "\n".join("第%d轮｜%s：%s" % (t["turn"], name[t["speaker"]], t["content"])
                     for t in case["history"])


def render_example(variant):
    t = [r for r in EXAMPLE_CASE["roles"] if r.get("is_target")][0]
    role = render_role_flat(t) if variant == "flat" else render_role_struct(t)
    hist = render_history(EXAMPLE_CASE, variant)
    return ("# 示例（仅演示格式，与本次任务无关）\n\n"
            "【角色设定】\n" + role
            + "\n\n【历史对话】\n" + hist
            + "\n\n【需要回复的消息】\n" + EXAMPLE_CASE["test_question"]
            + "\n\n【回复】\n" + EXAMPLE_CASE["reply"])


def blocks(case, variant):
    """返回提示的五个块，供审计做逐块比对。"""
    if variant not in ("flat", "struct"):
        raise ValueError(variant)
    target = [r for r in case["roles"] if r.get("is_target")][0]
    return {
        "guide": READING_GUIDE,
        "task": TASK_HEAD,
        "example": render_example(variant),
        "role": render_role_flat(target) if variant == "flat" else render_role_struct(target),
        "history": render_history(case, variant),
        "question": "# 需要回复的消息\n\n" + case["target"]["test_question"].strip() + "\n",
        "tail": TASK_TAIL,
    }


def render(case, variant):
    b = blocks(case, variant)
    return (b["guide"] + b["task"]
            + "\n" + b["example"]
            + "\n# 角色设定\n\n" + b["role"]
            + "\n\n# 历史对话\n\n" + b["history"]
            + "\n\n" + b["question"]
            + b["tail"])


def load(case_id):
    with open(os.path.join(CASE_DIR, "%s.yaml" % case_id), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--case")
    ap.add_argument("--variant", choices=["flat", "struct"])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    if args.all:
        ids = sorted(f[:-5] for f in os.listdir(CASE_DIR) if f.endswith(".yaml"))
        out = args.out or os.path.join(ROOT, "data", "prompts")
        for cid in ids:
            case = load(cid)
            for v in ("flat", "struct"):
                d = os.path.join(out, v)
                os.makedirs(d, exist_ok=True)
                with open(os.path.join(d, "%s.txt" % cid), "w", encoding="utf-8") as fh:
                    fh.write(render(case, v))
        print("已渲染 %d 个案例 × 2 变体（%s）-> %s" % (len(ids), PROMPT_VERSION, out))
        return 0

    if not args.case or not args.variant:
        ap.error("需要 --case 与 --variant，或 --all")
    sys.stdout.write(render(load(args.case), args.variant))
    return 0


if __name__ == "__main__":
    sys.exit(main())
