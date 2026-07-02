"""
feishu_config.py — 飞书推送配置（混淆存储，不暴露 webhook 明文）

环境变量（推荐）:
  LARK_PUSH_CFG  — XOR+Base64 混淆后的 hook token（不含 URL 前缀）

兼容（不推荐，仅迁移用）:
  FEISHU_WEBHOOK_URL — 明文 webhook（GitHub Secrets 可用混淆版替代）

飞书安全关键词（自定义）: DOG / 蔬菜 / score / 市场
  → 所有推送卡片自动嵌入「市场 score」以满足校验
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Optional

# 固定前缀（公开无害）；hook UUID 仅存于混淆 token 中
_LARK_HOST = "open.feishu.cn"
_LARK_PATH = "/open-apis/bot/v2/hook/"
_XOR_KEY = b"ecoh.v36"

# 飞书自定义关键词（消息中须至少命中其一）
KEYWORD_TAG = "市场 score"


def _load_dotenv() -> None:
    """轻量 .env 加载（不引入额外依赖）。"""
    root = Path(__file__).resolve().parent.parent
    env_file = root / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


def _xor(data: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def encode_hook_token(hook_uuid: str) -> str:
    """
    将 hook UUID 编码为 LARK_PUSH_CFG 值（本地一次性工具用）。

    示例:
      encode_hook_token("0be90529-8200-4fff-bdf6-1e8e7e671cab")
    """
    clean = hook_uuid.strip().replace("-", "")
    if len(clean) != 32:
        raise ValueError("hook UUID 格式无效")
    xored = _xor(clean.encode(), _XOR_KEY)
    return base64.urlsafe_b64encode(xored).decode().rstrip("=")


def decode_hook_token(cfg: str) -> str:
    """解码 LARK_PUSH_CFG → 完整 webhook URL。"""
    cfg = cfg.strip()
    if not cfg:
        raise ValueError("empty config")
    pad = "=" * (-len(cfg) % 4)
    xored = base64.urlsafe_b64decode(cfg + pad)
    raw = _xor(xored, _XOR_KEY).decode()
    if len(raw) != 32:
        raise ValueError("invalid token length")
    uuid = f"{raw[:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:]}"
    return f"https://{_LARK_HOST}{_LARK_PATH}{uuid}"


def get_webhook_url() -> str:
    """
    解析推送 endpoint。优先级:
      1. LARK_PUSH_CFG（混淆，推荐）
      2. FEISHU_WEBHOOK_URL（明文，兼容）
    """
    _load_dotenv()

    obf = os.environ.get("LARK_PUSH_CFG", "").strip()
    if obf:
        try:
            return decode_hook_token(obf)
        except Exception:
            pass

    return os.environ.get("FEISHU_WEBHOOK_URL", "").strip()


def is_configured() -> bool:
    return bool(get_webhook_url())


def ensure_keyword(text: str) -> str:
    """确保文本含飞书安全关键词。"""
    keywords = ("DOG", "蔬菜", "score", "市场")
    if any(k in text for k in keywords):
        return text
    return f"{text}\n{KEYWORD_TAG}"


def keyword_footer() -> str:
    return f"⚠️ {KEYWORD_TAG} · 仅供参考，不构成投资建议"


def parse_feishu_response(status_code: int, text: str) -> tuple[bool, str]:
    """
    飞书 webhook 常返回 HTTP 200 但 body 里 code != 0（如关键词校验失败）。
    只有 code/StatusCode 为 0 才算真正成功。
    """
    if status_code != 200:
        return False, f"HTTP {status_code}: {text[:200]}"
    try:
        body = __import__("json").loads(text)
        code = body.get("code", body.get("StatusCode"))
        if code == 0:
            return True, body.get("msg") or body.get("StatusMessage") or "ok"
        msg = body.get("msg") or body.get("StatusMessage") or text[:200]
        return False, f"feishu code={code}: {msg}"
    except Exception:
        return True, text[:100]


def build_text_payload(text: str) -> dict:
    """文本消息（关键词校验最可靠）。"""
    return {
        "msg_type": "text",
        "content": {"text": ensure_keyword(text)},
    }
