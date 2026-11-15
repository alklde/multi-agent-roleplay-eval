# 面向角色扮演的多智能体实验评测系统

> 一个可复现的实验工具链：在**多角色、带预设历史**的对话里，测量"提示的呈现结构（`flat` 段落式 vs `struct` 字段式）"是否影响模型的**事实符合**与**角色符合**。
>
> 课题：合肥工业大学 · 国家自然科学基金项目 62672165 支持 · 2026
>
> **当前状态：阶段 A（需求基线）与阶段 B（实验材料）已完成；0 次模型调用、0 条评分。** 仓库中只有可复现的材料与校验脚本，没有任何实验结果。

## 这是什么

给定一段多角色历史对话与一个目标角色，让模型以该角色身份回复最后一条消息，然后由人工按两维量表打分：

| 维度 | 含义 | 取值 |
|---|---|---|
| 事实符合（fact） | 回复中的事实陈述与案例事实卡是否一致；有无采信诱导性错误信息 | 1–5 或 null |
| 角色符合（role） | 是否守住该角色的立场、职责边界与说话风格 | 1–5 或 null |

唯一自变量是**提示的呈现结构**，其余信息（角色设定、历史、问题、说明、示例）两版逐字节相同：

- `flat`：角色设定为连续段落，历史为 `名字：内容`，无轮次编号；
- `struct`：角色设定分节为 `【角色】【身份】【立场】【说话风格】【掌握的信息】`，历史带 `第N轮｜` 前缀。

信息等价性由脚本机械审计（命题单元 100% 对应、共享块逐字节相同、无评分真值泄漏），见 `tools/audit_equivalence.py`。

## 目录

```
data/cases/C01–C20.yaml   20 个虚构案例（draft）：三种事实可得性 × 三类目标角色
prereg/prereg_v1.0–1.3.json  预注册的四个版本（含 M1–M3 变更记录与内容哈希）
prereg/*.sha256           内容哈希，用于证明"先注册、后看数据"
tools/validate_cases.py   案例规范的机械校验（622 项）
tools/render_prompt.py    把案例渲染成 flat / struct 两版提示
tools/audit_equivalence.py 信息等价性审计（含 tiktoken 计数的 token 差）
tools/compute_prereg_hash.py 预注册哈希的规范化计算与校验
tools/check_gate_a.py / check_gate_b.py 两阶段门禁的自检脚本
```

论文与设计文档（需求基线、文献、需求规格、效度与风险、案例规范、提示设计、评分量表、预注册分析方案、运行协议）**不在本仓库**，另行提交。

## 快速开始

```bash
# 1. 校验 20 个案例（纯标准库，无需第三方依赖）
python3 tools/validate_cases.py

# 2. 渲染两版提示到 data/prompts/
python3 tools/render_prompt.py --all

# 3. 信息等价性审计（需要 tiktoken 才能报告 token 差，字符差总是可算）
python3 tools/audit_equivalence.py

# 4. 预注册哈希校验
python3 tools/compute_prereg_hash.py prereg/prereg_v1.3.json --check
```

`tiktoken` 装在 conda 环境里：

```bash
source /opt/miniconda3/etc/profile.d/conda.sh
conda activate deeplearning
python tools/audit_equivalence.py
```

没有 tiktoken 时脚本仍能跑完，token 列显示 `[待实测]`——不会用字符数冒充 token 数。

## 实验设计（摘要）

| 项 | 取值 |
|---|---|
| 案例 | 20 个（平台管理员 7 / 信息发布者 7 / 事实核查者 6；explicit 7 / partial 7 / conflicting 6） |
| 自变量 | 提示结构：`flat` / `struct` |
| 重复 | 每案例每变体 3 次 ⇒ 120 次运行 |
| 评分 | 全量两遍独立盲评 ⇒ 240 条评分（每遍 120 条） |
| 主指标 | `d_i = t_struct,i − t_flat,i`（案例级配对差，案例均值口径） |
| 区间 | 按**案例**重采样 bootstrap，B=1000，seed=20261017，`n_paired < 2` 不报区间 |
| 预注册 | `prereg/prereg_v1.3.json`，内容哈希见同名 `.sha256`；变更以 M1–M3 记录，`post_hoc: false` |

评分换算：`x=(s−1)/4`，`t=Σw·x/Σw`（默认等权）；单维缺失时按可用维度收缩分母，两维皆缺失 `t=null`。**不做任何缺失填补**。

## 可复现性约定

- 预注册先封存、后看数据；任何参数或模型的变更都必须新建版本并记 amendment，旧版本保留。
- 模型标识不写死在预注册里，而由 experiment config 在首次成功调用前冻结，并逐条记入 `runs.model_id`。
- 案例为**虚构**：机构名使用"本市""邻聚社区""城西"等等位表述，不指向任何真实主体。
- 所有"通过/达标"表述都必须附可运行命令的输出；未执行的检查一律写"待执行"。

## 已知局限（提前写明）

- 评分者只有课题作者一人（分两遍，间隔 ≥7 天），报告的一致性系数是**评分者内 retest**，不是评分者间信度。
- 两版提示存在约 3% 的字符差、3.3%–4.4% 的 token 差（`o200k_base` 代理计数），长度效应未完全排除。
- 结论不外推到并发多用户、自动提示词搜索、自动评分等本课题明确不做的范围。

## 许可

学术研究用途。案例文本为虚构，可自由用于复现；引用请注明本仓库与课题名称。
