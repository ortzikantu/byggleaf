"""规范化 BCP 47 语言标签，并按精确文件名加载界面翻译。

任意写法都会规范化成 BCP 47（``zh-hk`` → ``zh-HK``），然后只加载
``locales/<规范化标签>.toml``。这里不做地区回退：``zh-SG`` 只有在
``locales/zh-SG.toml`` 存在时才可用，缺文件会报出可用列表和贡献提示，
而不是悄悄显示另一种语言。
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

LOCALES_DIR = Path(__file__).resolve().parent.parent / "locales"

_LANGUAGE_RE = re.compile(r"^[A-Za-z]{2,3}$")
_SCRIPT_RE = re.compile(r"^[A-Za-z]{4}$")
_REGION_RE = re.compile(r"^(?:[A-Za-z]{2}|[0-9]{3})$")
_VARIANT_RE = re.compile(r"^(?:[0-9][A-Za-z0-9]{3}|[A-Za-z0-9]{5,8})$")


class LocaleError(RuntimeError):
    """语言标签或翻译目录无效或缺失。"""


@dataclass(frozen=True, slots=True)
class Locale:
    """某一语言标签下经过校验的翻译目录。"""

    language: str
    strings: dict[str, str]

    def text(self, key: str, **values: object) -> str:
        template = self.strings.get(key)
        if not template or not template.strip():
            # 允许部分翻译：缺 key 时直接显示 key 名，而不是中断构建。
            return key
        try:
            return template.format(**values)
        except (KeyError, IndexError, ValueError) as exc:
            raise LocaleError(
                f"translation {key!r} cannot be formatted with {values!r}"
            ) from exc


def canonicalize_language(tag: str) -> str:
    """校验 BCP 47 标签子集，返回约定的大小写形式。"""

    if not isinstance(tag, str):
        raise LocaleError("language must be a string")
    value = tag.strip()
    if not value:
        raise LocaleError("language must not be empty")
    if "_" in value:
        raise LocaleError(
            f"invalid language tag {value!r}; use a BCP 47 tag such as zh-CN"
        )

    parts = value.split("-")
    if any(not part for part in parts):
        raise LocaleError(f"invalid language tag {value!r}")

    language = parts[0]
    if not _LANGUAGE_RE.fullmatch(language):
        raise LocaleError(
            f"invalid language tag {value!r}; expected an ISO 639 language code"
        )
    language = language.lower()

    index = 1
    script: str | None = None
    region: str | None = None
    variants: list[str] = []

    if index < len(parts) and _SCRIPT_RE.fullmatch(parts[index]):
        script = parts[index].title()
        index += 1

    if index < len(parts) and _REGION_RE.fullmatch(parts[index]):
        region = parts[index].upper()
        index += 1

    while index < len(parts):
        if not _VARIANT_RE.fullmatch(parts[index]):
            raise LocaleError(
                f"invalid or unsupported language subtag {parts[index]!r} "
                f"in {value!r}"
            )
        variants.append(parts[index].lower())
        index += 1

    pieces = [language]
    if script is not None:
        pieces.append(script)
    if region is not None:
        pieces.append(region)
    pieces.extend(variants)
    return "-".join(pieces)


def _available_languages() -> str:
    return ", ".join(sorted(path.stem for path in LOCALES_DIR.glob("*.toml")))


def _read_locale(path: Path) -> dict[str, str]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise LocaleError(f"cannot read locale {path}: {exc}") from exc

    ui = data.get("ui")
    if not isinstance(ui, dict):
        raise LocaleError(f"{path}: [ui] table is required")

    strings: dict[str, str] = {}
    for key, value in ui.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise LocaleError(f"{path}: ui.{key} must be a string")
        strings[key] = value
    return strings


def load_locale(language: str) -> Locale:
    """按精确文件名加载 ``locales/<规范化标签>.toml``。"""

    canonical = canonicalize_language(language)
    path = LOCALES_DIR / f"{canonical}.toml"
    if not path.is_file():
        available = _available_languages()
        raise LocaleError(
            f"no translation file for {canonical!r}; available: {available}. "
            f"Add locales/{canonical}.toml or contribute a translation."
        )

    return Locale(language=canonical, strings=_read_locale(path))


__all__ = [
    "Locale",
    "LocaleError",
    "canonicalize_language",
    "load_locale",
]
