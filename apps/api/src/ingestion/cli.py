import argparse
import asyncio
import logging
import sys
from pathlib import Path

from src.ingestion.loaders import SUPPORTED_SUFFIXES
from src.ingestion.pipeline import ingest_document

log = logging.getLogger("danny_rag.ingest")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="Ingest a document into the configured Qdrant collection"
    )
    parser.add_argument("path", type=Path, help="Path to a PDF / MD / HTML / TXT file")
    args = parser.parse_args()

    if not args.path.exists():
        log.error("file not found: %s", args.path)
        sys.exit(1)
    if args.path.suffix.lower() not in SUPPORTED_SUFFIXES:
        log.error(
            "unsupported file type: %s. supported: %s",
            args.path.suffix,
            sorted(SUPPORTED_SUFFIXES),
        )
        sys.exit(1)

    result = asyncio.run(ingest_document(args.path))
    log.info(
        "ingest done: doc_id=%s total_chunks=%d upserted=%d skipped_unchanged=%d",
        result.doc_id,
        result.total_chunks,
        result.upserted,
        result.skipped_unchanged,
    )


if __name__ == "__main__":
    main()
