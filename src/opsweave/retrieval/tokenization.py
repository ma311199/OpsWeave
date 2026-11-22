"""Configurable tokenizer shared by chunking and embedding limits.

Uses a local HuggingFace tokenizer file (``tokenizer.json``) when
``embedding_tokenizer_path`` is configured, so chunk sizes and the
max-token guard are measured with the same tokenizer the embedding model
uses. Falls back to LlamaIndex's tiktoken ``cl100k_base`` otherwise.

Two views are exposed because the callers disagree on the return type:

* :func:`get_tokenizer` returns ``list`` of tokens (LlamaIndex node parsers
  call ``len(tokenizer(text))``);
* :func:`get_token_counter` returns ``int`` (langchain ``length_function``
  and embedding limit checks).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..config.settings import get_settings

logger = logging.getLogger(__name__)

FALLBACK_HINT = (
    "未配置可用分词器，已回退 tiktoken cl100k_base（对中文为近似值，"
    "真实 token 数通常更多）"
)


def _resolve_tokenizer_file(path_value: str) -> Path | None:
    """Return the tokenizer.json path for a file or directory input."""
    path = Path(path_value).expanduser()
    if path.is_file():
        return path
    if path.is_dir():
        candidate = path / "tokenizer.json"
        if candidate.is_file():
            return candidate
    return None


@lru_cache(maxsize=8)
def _load_tokenizer(path_str: str) -> Any | None:
    """Load and cache a ``tokenizers.Tokenizer`` from a local file."""
    tokenizer_file = _resolve_tokenizer_file(path_str)
    if tokenizer_file is None:
        logger.warning(
            "分词器路径无效（需为 tokenizer.json 或其所在目录）：%s", path_str
        )
        return None
    try:
        from tokenizers import Tokenizer
    except ImportError:
        logger.warning(
            "未安装 tokenizers，无法加载本地分词器 %s；请先安装 tokenizers 依赖",
            path_str,
        )
        return None
    try:
        tokenizer = Tokenizer.from_file(str(tokenizer_file))
    except Exception:
        logger.exception("加载分词器失败：%s", tokenizer_file)
        return None

    logger.info("已加载本地分词器：%s", tokenizer_file)
    return tokenizer


def validate_tokenizer_path(path_value: str) -> tuple[bool, str]:
    """Validate a configured tokenizer path; returns (ok, message)."""
    if not path_value.strip():
        return True, ""
    tokenizer_file = _resolve_tokenizer_file(path_value.strip())
    if tokenizer_file is None:
        return False, "分词器路径无效：需指向 tokenizer.json 文件或其所在目录"
    try:
        from tokenizers import Tokenizer
    except ImportError:
        return (
            False,
            "当前环境未安装 tokenizers 包，无法加载本地分词器；"
            "请先安装（uv pip install tokenizers）后再保存配置",
        )
    try:
        Tokenizer.from_file(str(tokenizer_file))
    except Exception as exc:  # noqa: BLE001
        return False, f"分词器文件无法解析：{exc}"
    return True, ""


def clear_tokenizer_cache() -> None:
    """Clear cached tokenizers (call after the path changes)."""
    _load_tokenizer.cache_clear()


def get_tokenizer() -> Callable[[str], list]:
    """Return a tokenizer callable that maps text to a list of tokens.

    Compatible with LlamaIndex node parsers' ``tokenizer`` parameter.
    """
    configured = get_settings().embedding_tokenizer_path.strip()
    if configured:
        tokenizer = _load_tokenizer(configured)
        if tokenizer is not None:
            return lambda text: tokenizer.encode(text, add_special_tokens=False).tokens

    from llama_index.core.utils import get_tokenizer as li_get_tokenizer

    fallback = li_get_tokenizer()
    return lambda text: list(fallback(text))


def get_token_counter() -> Callable[[str], int]:
    """Return a token counting function for the current configuration."""
    tokenizer = get_tokenizer()
    return lambda text: len(tokenizer(text))


def tokenizer_status() -> dict[str, Any]:
    """Describe which tokenizer is actually in effect, for UI display."""
    configured = get_settings().embedding_tokenizer_path.strip()
    if configured:
        tokenizer_file = _resolve_tokenizer_file(configured)
        if tokenizer_file is not None and _load_tokenizer(configured) is not None:
            return {
                "active": True,
                "source": "local",
                "file": str(tokenizer_file),
            }
    return {"active": False, "source": "fallback", "file": "tiktoken cl100k_base"}
