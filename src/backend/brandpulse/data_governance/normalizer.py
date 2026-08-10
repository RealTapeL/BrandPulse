"""主数据匹配使用的保守文本标准化工具。

标准化只消除大小写、空白和标点差异，不做模糊匹配，不凭相似度强行把记录归属到品牌或门店。
"""
import hashlib
import re
import unicodedata


def normalize_text(value: object) -> str:
    """统一全半角、大小写、空白和标点，保留中文、字母和数字。"""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).casefold().strip()
    return re.sub(r"[^\w\u3400-\u9fff]+", "", text, flags=re.UNICODE)


def normalize_address(value: object) -> str:
    """地址标准化；暂不做道路、楼层或门牌号的语义猜测。"""
    return normalize_text(value)


def stable_key(*parts: object) -> str:
    """为治理记录生成稳定、不泄露原文的键。"""
    raw = "|".join(normalize_text(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

