#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""预注册文件内容哈希（B4）。

对 JSON 做规范化（sort_keys + 紧凑分隔符 + 保留中文）后取 sha256，写入：
  prereg/<name>.sha256   —— 第一行为内容哈希，第二行为文件字节哈希

用法：
    python3 tools/compute_prereg_hash.py prereg/prereg_v1.json
    python3 tools/compute_prereg_hash.py prereg/prereg_v1.json --check
"""

import argparse
import hashlib
import json
import os
import sys

try:
    from datetime import datetime, timezone, timedelta
    TZ = timezone(timedelta(hours=8))
except ImportError:  # pragma: no cover
    TZ = None


def canonical_hash(obj):
    """对内容取哈希；hash.value / hash.computed_at 两个自指字段先置空。"""
    import copy
    tmp = copy.deepcopy(obj)
    if isinstance(tmp.get("hash"), dict):
        tmp["hash"]["value"] = None
        tmp["hash"]["computed_at"] = None
    raw = json.dumps(tmp, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--stamp", action="store_true",
                    help="把哈希与时间写回预注册文件的 hash 字段（会改变文件哈希）")
    args = ap.parse_args(argv)

    with open(args.path, encoding="utf-8") as fh:
        obj = json.load(fh)

    content = canonical_hash(obj)
    fh_hash = file_hash(args.path)
    sha_path = os.path.splitext(args.path)[0] + ".sha256"

    if args.check:
        if not os.path.exists(sha_path):
            print("FAIL 尚未生成 %s" % sha_path)
            return 1
        with open(sha_path, encoding="utf-8") as fh:
            lines = [ln.strip() for ln in fh if ln.strip()]
        recorded = lines[0].split()[0] if lines else ""
        ok = recorded == content
        print("%s 记录 %s…  当前 %s…" % ("PASS" if ok else "FAIL", recorded[:16], content[:16]))
        return 0 if ok else 1

    if args.stamp:
        now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S%z") if TZ else "unknown"
        obj["hash"]["value"] = content
        obj["hash"]["computed_at"] = now
        with open(args.path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        # 写回后内容变了，记录"被哈希的内容"而非写回后的文件
        fh_hash = file_hash(args.path)
        print("已写入 hash 字段：%s" % content)

    with open(sha_path, "w", encoding="utf-8") as fh:
        fh.write("%s  canonical-json\n" % content)
        fh.write("%s  file-bytes\n" % fh_hash)

    print("内容哈希 %s" % content)
    print("文件哈希 %s" % fh_hash)
    print("已写入 %s" % sha_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
