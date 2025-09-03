import os
from typing import Dict, List
from datetime import datetime
import zipfile
import tempfile
import re
import shutil

def remove_temp_dir(path: str):
    if os.path.exists(path) and os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)

def safe_filename(s: str, fallback: str = "document") -> str:
    s = (s or "").strip()
    if not s:
        s = fallback
    s = re.sub(r'[<>:"/\\|?*\x00-\x1F]', '_', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s[:150] or fallback

def guess_ext_from_content(content: bytes) -> str:
    if not content:
        return ".bin"
    if content.startswith(b"%PDF"):
        return ".pdf"
    if content.startswith(b"{\\rtf"):
        return ".rtf"
    return ".txt"


def build_judgments_zip(successful_downloads: List[Dict]):
    """
    Buduje ZIP:
    - nazwy plików w ZIP: <sygnatura><.rtf/.pdf/.txt>
    - unikalność nazw przez sufiks _2, _3, ...
    - nazwa ZIP: cbosa_large_download_YYYYmmdd_HHMMSS.zip
    Zwraca: (bytes_zip, zip_filename)
    """
    if not successful_downloads:
        return None, None

    tmpdir = tempfile.mkdtemp()
    zip_filename = f"cbosa_large_download_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.zip"
    zip_path = os.path.join(tmpdir, zip_filename)

    written_paths = []
    seen_names = set()

    for i, r in enumerate(successful_downloads, 1):
        content = r.get("content")
        if not content:
            continue
        ci = r.get("case_info", {}) or {}
        signature = ci.get("signature") or f"case_{i}"

        base = safe_filename(signature, fallback=f"case_{i}")
        ext = guess_ext_from_content(content)
        name = f"{base}{ext}"

        if name in seen_names:
            suffix = 2
            while f"{base}_{suffix}{ext}" in seen_names:
                suffix += 1
            name = f"{base}_{suffix}{ext}"
        seen_names.add(name)

        fullpath = os.path.join(tmpdir, name)
        with open(fullpath, "wb") as f:
            f.write(content)
        written_paths.append(fullpath)


    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in written_paths:
            zf.write(p, os.path.basename(p))

    with open(zip_path, "rb") as f:
        zip_bytes = f.read()

    return zip_bytes, zip_filename
