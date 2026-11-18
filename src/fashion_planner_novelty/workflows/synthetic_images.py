"""오프라인 합성 이미지 제공자(``NOVELTY_DRAFT_IMAGE_PROVIDER=synthetic``).

외부 호출 없이 표준 라이브러리(zlib, struct, hashlib)만으로 상품·착장 PNG를 만든다. 그림은 상품 사진이
아니라 'SYNTHETIC' 글자가 크게 들어간 자리표시 그림이다. e2e와 데모에서 이미지 경로 전체(저장, 원장,
응답 계약)를 유료 호출 없이 돌리려고 둔다.

- 결정적이다. 같은 입력이면 어느 환경에서나 같은 바이트가 나온다. 압축 구현에 따라 결과가 달라지지 않도록
  deflate를 무압축(stored) 블록으로 직접 쓰고, zlib은 체크섬(adler32, crc32)에만 쓴다.
- 색은 입력 해시에서 정한다. 상품 색은 상품 사양 JSON에서, 착장의 테두리 색은 상품 이미지 바이트에서,
  재고 상품 색은 재고 상품 사양에서 나온다. 그래서 착장 이미지는 상품 이미지에 따라 달라진다.
- 제3자 이미지나 글꼴은 쓰지 않는다. 글자는 아래 5×7 비트맵으로 직접 그린다.
"""
from __future__ import annotations

import hashlib
import json
import struct
import zlib

from .image_generation import ImageProviderError

SYNTHETIC_IMAGE_MODEL = "synthetic"
IMAGE_SIZE = 512
PNG_DESCRIPTION = ("SYNTHETIC placeholder generated offline by fashion-planner-novelty. "
                   "Not a product photograph or a generated design concept.")

# 5×7 비트맵 글꼴(이 프로젝트에서 직접 그림). 필요한 글자만 둔다.
_GLYPHS = {
    "C": (".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."),
    "D": ("###..", "#..#.", "#...#", "#...#", "#...#", "#..#.", "###.."),
    "E": ("#####", "#....", "#....", "####.", "#....", "#....", "#####"),
    "F": ("#####", "#....", "#....", "####.", "#....", "#....", "#...."),
    "H": ("#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "I": (".###.", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "N": ("#...#", "#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#"),
    "O": (".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "P": ("####.", "#...#", "#...#", "####.", "#....", "#....", "#...."),
    "R": ("####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"),
    "S": (".####", "#....", "#....", ".###.", "....#", "....#", "####."),
    "T": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    "U": ("#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "Y": ("#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."),
}

# 팔레트 색인
_BACKGROUND, _INK, _GARMENT, _STOCK, _ACCENT, _PANEL = range(6)


def _canonical_sha256(value: object) -> bytes:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).digest()


def _mid_tone(digest: bytes) -> tuple[int, int, int]:
    """해시 앞 3바이트를 너무 어둡거나 밝지 않은 색(64–223)으로 바꾼다. 검은 글자가 늘 보이게 한다."""
    return tuple(64 + digest[i] % 160 for i in range(3))


def text_mask(text: str) -> list[str]:
    """글자 사이 한 칸을 띄운 7줄 비트맵. 테스트도 이 함수로 그려진 글자를 확인한다."""
    rows = []
    for row in range(7):
        rows.append(".".join(_GLYPHS[char][row] for char in text))
    return rows


class _Canvas:
    def __init__(self, size: int) -> None:
        self.size = size
        self.pixels = bytearray([_BACKGROUND]) * (size * size)

    def fill(self, x0: int, y0: int, x1: int, y1: int, index: int) -> None:
        run = bytes([index]) * (x1 - x0)
        for y in range(y0, y1):
            start = y * self.size + x0
            self.pixels[start:start + len(run)] = run

    def frame(self, x0: int, y0: int, x1: int, y1: int, width: int, index: int) -> None:
        self.fill(x0, y0, x1, y0 + width, index)
        self.fill(x0, y1 - width, x1, y1, index)
        self.fill(x0, y0, x0 + width, y1, index)
        self.fill(x1 - width, y0, x1, y1, index)

    def text(self, text: str, top: int, scale: int, index: int = _INK) -> None:
        mask = text_mask(text)
        left = (self.size - len(mask[0]) * scale) // 2
        for row, line in enumerate(mask):
            for column, cell in enumerate(line):
                if cell == "#":
                    x, y = left + column * scale, top + row * scale
                    self.fill(x, y, x + scale, y + scale, index)


def text_origin(text: str, scale: int, size: int = IMAGE_SIZE) -> int:
    """``_Canvas.text``가 글자를 놓는 왼쪽 x 좌표."""
    return (size - len(text_mask(text)[0]) * scale) // 2


def _stored_zlib(data: bytes) -> bytes:
    """압축하지 않은 deflate 블록으로 만든 zlib 스트림. 압축 라이브러리 판에 상관없이 같은 바이트가 나온다."""
    out = bytearray(b"\x78\x01")
    block = 65_535
    for start in range(0, len(data), block):
        chunk = data[start:start + block]
        final = 1 if start + block >= len(data) else 0
        out += bytes([final]) + struct.pack("<HH", len(chunk), len(chunk) ^ 0xFFFF) + chunk
    out += struct.pack(">I", zlib.adler32(data))
    return bytes(out)


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def encode_png(canvas: _Canvas, palette: list[tuple[int, int, int]]) -> bytes:
    size = canvas.size
    raw = bytearray()
    for y in range(size):
        raw.append(0)  # 필터 없음
        raw += canvas.pixels[y * size:(y + 1) * size]
    return b"".join((
        b"\x89PNG\r\n\x1a\n",
        _png_chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 3, 0, 0, 0)),
        _png_chunk(b"PLTE", bytes(channel for color in palette for channel in color)),
        _png_chunk(b"tEXt", b"Description\x00" + PNG_DESCRIPTION.encode("ascii")),
        _png_chunk(b"IDAT", _stored_zlib(bytes(raw))),
        _png_chunk(b"IEND", b""),
    ))


# 상품·착장 그림의 배치. 테스트가 같은 값을 쓴다.
TITLE_TOP, TITLE_SCALE = 28, 8
LABEL_TOP, LABEL_SCALE = 440, 6
BODY = (96, 120, 416, 420)


class SyntheticDraftImageProvider:
    """OpenAIDraftImageProvider와 같은 호출 방식으로 합성 PNG를 돌려준다. 네트워크를 쓰지 않는다.

    착장은 OpenAI 경로처럼 상품 이미지가 있어야 만든다. 상품 이미지가 없으면 같은 오류 코드로 실패한다.
    """
    model = SYNTHETIC_IMAGE_MODEL

    def __init__(self) -> None:
        from .draft_artifacts import OpenAIDraftImageProvider
        # 응답 계약을 OpenAI 경로와 같게 두려고 프롬프트 식별값을 그대로 쓴다. 합성 그림은 프롬프트를 쓰지 않는다.
        self.prompt_version = OpenAIDraftImageProvider.prompt_version

    def generate(self, kind: str, product: dict, request_id: str, reference_image: bytes | None = None,
                 companion: dict | None = None) -> bytes:
        if kind not in {"product", "outfit"}:
            raise ValueError("unsupported draft visual kind")
        if kind == "outfit" and not reference_image:
            raise ImageProviderError("OUTFIT_REFERENCE_UNAVAILABLE")
        garment = _mid_tone(_canonical_sha256(product))
        accent = _mid_tone(hashlib.sha256(reference_image).digest()) if kind == "outfit" else (40, 40, 40)
        stock = (_mid_tone(_canonical_sha256(companion.get("specification")))
                 if kind == "outfit" and companion else (200, 200, 196))
        palette = [(236, 236, 232), (20, 20, 20), garment, stock, accent, (250, 250, 248)]

        canvas = _Canvas(IMAGE_SIZE)
        canvas.frame(0, 0, IMAGE_SIZE, IMAGE_SIZE, 8, _ACCENT if kind == "outfit" else _INK)
        canvas.fill(16, 16, IMAGE_SIZE - 16, TITLE_TOP + 7 * TITLE_SCALE + 12, _PANEL)
        canvas.text("SYNTHETIC", TITLE_TOP, TITLE_SCALE)
        x0, y0, x1, y1 = BODY
        if kind == "product" or not companion:
            canvas.fill(x0, y0, x1, y1, _GARMENT)
        else:
            # 재고 상품의 역할에 따라 새 상품을 위(상의) 또는 아래(하의)에 놓는다.
            middle = (y0 + y1) // 2
            stock_on_top = companion.get("role") == "upper_body"
            canvas.fill(x0, y0, x1, middle, _STOCK if stock_on_top else _GARMENT)
            canvas.fill(x0, middle, x1, y1, _GARMENT if stock_on_top else _STOCK)
        canvas.frame(x0, y0, x1, y1, 4, _INK)
        canvas.text("PRODUCT" if kind == "product" else "OUTFIT", LABEL_TOP, LABEL_SCALE)
        return encode_png(canvas, palette)
