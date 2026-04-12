from pathlib import Path

from bs4 import BeautifulSoup

SUPPORTED_SUFFIXES = {".pdf", ".md", ".markdown", ".html", ".htm", ".txt"}


def load_document(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _load_pdf(path)
    if suffix in {".md", ".markdown", ".txt"}:
        return path.read_text(encoding="utf-8")
    if suffix in {".html", ".htm"}:
        soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
        return soup.get_text(separator="\n")
    raise ValueError(f"Unsupported file type: {suffix}. Supported: {sorted(SUPPORTED_SUFFIXES)}")


def _load_pdf(path: Path) -> str:
    from unstructured.partition.pdf import partition_pdf

    elements = partition_pdf(filename=str(path))
    return "\n\n".join(str(el) for el in elements if str(el).strip())
