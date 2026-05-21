"""Tests unitarios del servicio de almacenamiento de imágenes — sin Firebase real."""

from __future__ import annotations

import io

import pytest

from app.services.image_storage_service import compute_storage_path, compress_image


# ─── compute_storage_path ─────────────────────────────────────────────────────

def test_storage_path_has_correct_structure():
    path = compute_storage_path("user-123", "Rosa canina", "image/jpeg")
    parts = path.split("/")
    assert parts[0] == "plant_identifications"
    assert parts[1] == "user-123"
    assert parts[2].endswith(".jpeg")


def test_storage_path_uses_content_type_extension():
    path = compute_storage_path("user-1", "Monstera deliciosa", "image/png")
    assert path.endswith(".png")


def test_storage_path_replaces_spaces_with_underscore():
    path = compute_storage_path("user-1", "Monstera deliciosa", "image/jpeg")
    assert " " not in path
    assert "Monstera_deliciosa" in path


def test_storage_path_none_scientific_name():
    path = compute_storage_path("user-1", None, "image/jpeg")
    assert "unknown" in path


def test_storage_path_unique_per_call():
    path1 = compute_storage_path("user-1", "Rosa canina", "image/jpeg")
    path2 = compute_storage_path("user-1", "Rosa canina", "image/jpeg")
    # uuid4 hace que cada path sea único
    assert path1 != path2


def test_storage_path_contains_timestamp():
    import re
    path = compute_storage_path("user-1", "Rosa canina", "image/jpeg")
    # Timestamp en formato YYYYMMDDTHHmmss
    assert re.search(r"\d{8}T\d{6}", path), f"No se encontró timestamp en: {path}"


# ─── compress_image ───────────────────────────────────────────────────────────

def _make_png_bytes(width: int = 100, height: int = 100) -> bytes:
    """Crea una imagen PNG mínima en memoria."""
    from PIL import Image
    img = Image.new("RGB", (width, height), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_rgba_png_bytes(width: int = 100, height: int = 100) -> bytes:
    from PIL import Image
    img = Image.new("RGBA", (width, height), color=(100, 150, 200, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_compress_image_returns_bytes():
    result = compress_image(_make_png_bytes())
    assert isinstance(result, bytes)
    assert len(result) > 0


def test_compress_image_output_is_jpeg():
    """El resultado siempre debe ser JPEG (magic bytes FF D8)."""
    result = compress_image(_make_png_bytes())
    assert result[:2] == b"\xff\xd8", "El resultado no es un JPEG válido"


def test_compress_image_rgba_converts_to_rgb():
    """Imágenes RGBA se convierten a RGB antes de guardar como JPEG."""
    result = compress_image(_make_rgba_png_bytes())
    # Si no convirtiera RGB, Pillow lanzaría un error al guardar JPEG
    assert result[:2] == b"\xff\xd8"


def test_compress_image_small_image_no_resize():
    """Imágenes menores de 1920px no se redimensionan."""
    from PIL import Image
    original = _make_png_bytes(100, 100)
    result = compress_image(original)
    img = Image.open(io.BytesIO(result))
    assert img.width == 100
    assert img.height == 100


def test_compress_image_large_image_is_downscaled():
    """Imágenes mayores de 1920px se reducen."""
    from PIL import Image
    large = _make_png_bytes(3000, 2000)
    result = compress_image(large)
    img = Image.open(io.BytesIO(result))
    assert img.width <= 1920
    assert img.height <= 1920


def test_compress_image_maintains_aspect_ratio():
    """El redimensionado mantiene la proporción."""
    from PIL import Image
    # 4:3 → 3000x2250, debe quedar 1920x1440
    large = _make_png_bytes(3000, 2250)
    result = compress_image(large)
    img = Image.open(io.BytesIO(result))
    ratio = img.width / img.height
    assert abs(ratio - (4 / 3)) < 0.01, f"Proporción alterada: {ratio}"


def test_compress_image_square_large_downscaled_to_1920():
    from PIL import Image
    large = _make_png_bytes(2500, 2500)
    result = compress_image(large)
    img = Image.open(io.BytesIO(result))
    assert img.width == 1920
    assert img.height == 1920
