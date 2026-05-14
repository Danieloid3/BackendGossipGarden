"""Ingesta de fuentes botánicas a la tabla botanical_chunks.

Lee PDFs y archivos de texto de botanical_sources/, los chunkea y genera embeddings
para el RAG del pipeline de identificación de plantas.

Uso:
    cd backendGossipGarden
    python scripts/ingest_botanical_sources.py
    python scripts/ingest_botanical_sources.py --dry-run
    python scripts/ingest_botanical_sources.py --source "RHS Encyclopedia"

Convención de nombres para metadatos automáticos:
    <family>__<scientific_name>__<source_title>.pdf
    p.ej: Asparagaceae__Sansevieria_trifasciata__RHS_Encyclopedia.pdf

Alternativa: incluir frontmatter YAML al inicio de archivos .md:
    ---
    family: Asparagaceae
    scientific_name: Sansevieria trifasciata
    source: RHS Encyclopedia
    ---

Los archivos en botanical_sources/ NO se incluyen en el repo (ver .gitignore).
Aportar PDFs/TXTs manualmente para activar el valor del RAG.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Añadir raíz del proyecto al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings  # noqa: E402
from app.db.supabase import supabase  # noqa: E402
from app.services.openai_service import embed_texts  # noqa: E402

try:
    import tiktoken
    _tokenizer = tiktoken.get_encoding("cl100k_base")

    def count_tokens(text: str) -> int:
        return len(_tokenizer.encode(text))

except ImportError:
    logger.warning("tiktoken no disponible, usando conteo aproximado por palabras")

    def count_tokens(text: str) -> int:  # type: ignore[misc]
        return len(text.split()) * 4 // 3


CHUNK_TOKENS = 500
OVERLAP_TOKENS = 50
BATCH_SIZE = 100


def extract_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except ImportError:
            logger.error("pypdf no instalado. Instala con: pip install pypdf")
            return ""
        except Exception as e:
            logger.error("Error leyendo PDF %s: %s", path.name, e)
            return ""
    else:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.error("Error leyendo %s: %s", path.name, e)
            return ""


def parse_metadata(path: Path) -> dict:
    """Extrae metadatos del nombre del archivo o del frontmatter YAML."""
    meta = {"family": None, "scientific_name": None, "source": path.stem}

    # Intentar frontmatter YAML (solo para .md y .txt)
    if path.suffix.lower() in (".md", ".txt"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if text.startswith("---"):
            try:
                import re
                match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
                if match:
                    import yaml  # type: ignore[import]
                    fm = yaml.safe_load(match.group(1))
                    meta.update({k: v for k, v in fm.items() if k in meta})
            except Exception:
                pass

    # Intentar convención de nombre: family__scientific_name__source.ext
    parts = path.stem.replace("-", "_").split("__")
    if len(parts) >= 3:
        meta["family"] = parts[0].replace("_", " ").title()
        meta["scientific_name"] = parts[1].replace("_", " ")
        meta["source"] = parts[2].replace("_", " ")
    elif len(parts) == 2:
        meta["scientific_name"] = parts[0].replace("_", " ")
        meta["source"] = parts[1].replace("_", " ")

    return meta


def chunk_text(text: str, *, chunk_tokens: int = CHUNK_TOKENS, overlap: int = OVERLAP_TOKENS) -> list[str]:
    """Chunkea texto en segmentos de ~chunk_tokens con overlap."""
    sentences = text.replace("\n\n", " ¶ ").split(". ")
    chunks: list[str] = []
    current_parts: list[str] = []
    current_tokens = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        t = count_tokens(sentence)
        if current_tokens + t > chunk_tokens and current_parts:
            chunk = ". ".join(current_parts).replace(" ¶ ", "\n\n")
            chunks.append(chunk.strip())
            # Overlap: mantener últimas partes hasta overlap tokens
            overlap_parts: list[str] = []
            overlap_t = 0
            for part in reversed(current_parts):
                pt = count_tokens(part)
                if overlap_t + pt > overlap:
                    break
                overlap_parts.insert(0, part)
                overlap_t += pt
            current_parts = overlap_parts
            current_tokens = overlap_t
        current_parts.append(sentence)
        current_tokens += t

    if current_parts:
        chunks.append(". ".join(current_parts).replace(" ¶ ", "\n\n").strip())

    return [c for c in chunks if len(c) > 50]


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def already_ingested(content_hash: str) -> bool:
    try:
        res = (
            supabase.table("botanical_chunks")
            .select("id")
            .eq("metadata->>hash", content_hash)
            .limit(1)
            .execute()
        )
        return bool(res.data)
    except Exception:
        return False


async def ingest_file(path: Path, *, dry_run: bool = False, source_filter: str | None = None) -> int:
    meta = parse_metadata(path)

    if source_filter and source_filter.lower() not in meta["source"].lower():
        return 0

    logger.info("Procesando: %s (fuente: %s)", path.name, meta["source"])
    text = extract_text(path)
    if not text.strip():
        logger.warning("  Archivo vacío o ilegible: %s", path.name)
        return 0

    chunks = chunk_text(text)
    logger.info("  %d chunks generados", len(chunks))

    new_chunks = [(c, sha256(c)) for c in chunks if not already_ingested(sha256(c))]
    logger.info("  %d chunks nuevos (no duplicados)", len(new_chunks))

    if dry_run or not new_chunks:
        return len(new_chunks)

    # Embeddings en lotes
    ingested = 0
    for i in range(0, len(new_chunks), BATCH_SIZE):
        batch = new_chunks[i : i + BATCH_SIZE]
        texts = [c for c, _ in batch]
        hashes = [h for _, h in batch]

        embeddings = await embed_texts(texts)
        rows = [
            {
                "content": text,
                "embedding": embedding,
                "source": meta["source"],
                "scientific_name": meta["scientific_name"],
                "family": meta["family"],
                "metadata": json.dumps({"hash": h, "file": path.name}),
            }
            for text, embedding, h in zip(texts, embeddings, hashes)
        ]

        try:
            supabase.table("botanical_chunks").insert(rows).execute()
            ingested += len(rows)
            logger.info("  Insertados %d chunks (lote %d)", len(rows), i // BATCH_SIZE + 1)
        except Exception as e:
            logger.error("  Error insertando lote %d: %s", i // BATCH_SIZE + 1, e)

    return ingested


async def main() -> None:
    parser = argparse.ArgumentParser(description="Ingesta fuentes botánicas al RAG")
    parser.add_argument("--dry-run", action="store_true", help="Analiza sin insertar")
    parser.add_argument("--source", help="Filtrar por nombre de fuente")
    parser.add_argument("--dir", default=settings.BOTANICAL_SOURCES_DIR, help="Directorio de fuentes")
    args = parser.parse_args()

    sources_dir = Path(args.dir)
    if not sources_dir.exists():
        logger.error("Directorio no encontrado: %s", sources_dir)
        sys.exit(1)

    extensions = {".pdf", ".txt", ".md"}
    files = [f for f in sources_dir.rglob("*") if f.suffix.lower() in extensions and f.is_file()]

    if not files:
        logger.warning(
            "No se encontraron archivos en %s. "
            "Agrega PDFs/TXTs de fuentes botánicas (RHS Encyclopedia, Houseplant Survival Manual, etc.) "
            "para que el RAG aporte valor.", sources_dir
        )
        return

    logger.info("Encontrados %d archivos en %s", len(files), sources_dir)
    total = 0
    for f in sorted(files):
        count = await ingest_file(f, dry_run=args.dry_run, source_filter=args.source)
        total += count

    mode = "analizados (dry-run)" if args.dry_run else "insertados"
    logger.info("Total chunks %s: %d", mode, total)


if __name__ == "__main__":
    asyncio.run(main())
