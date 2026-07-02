#!/usr/bin/env python3
"""一次性工具：将飞书 hook UUID 编码为 LARK_PUSH_CFG（勿提交明文 webhook）。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from feishu_config import encode_hook_token, decode_hook_token


def main() -> None:
    if len(sys.argv) != 2:
        print("用法: python3 scripts/encode_feishu_hook.py <hook-uuid-or-url>")
        print("示例: python3 scripts/encode_feishu_hook.py 0be90529-8200-4fff-bdf6-1e8e7e671cab")
        sys.exit(1)

    raw = sys.argv[1].strip()
    if "/hook/" in raw:
        raw = raw.rsplit("/hook/", 1)[-1]

    enc = encode_hook_token(raw)
    print("写入 .env（勿 commit）:")
    print(f"LARK_PUSH_CFG={enc}")
    decoded = decode_hook_token(enc)
    print("验证:", "OK" if raw.replace("-", "") in decoded.replace("-", "") else "FAIL")


if __name__ == "__main__":
    main()
