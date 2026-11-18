#!/usr/bin/env bash
# docs/diagrams/src/*.dot을 라이트·다크 SVG와 PNG로 렌더한다.
#
# 필요한 도구: Graphviz(`dot`), librsvg(`rsvg-convert`), Pretendard 폰트(OFL, 로컬 설치. 저장소에는 넣지 않는다).
# 원본은 라이트 팔레트로 쓰고, 다크 버전은 색을 하나씩 대응하는 다크 색으로 바꿔 만든다.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/docs/diagrams/src"
OUT="$ROOT/docs/diagrams"
FONT_STACK="Pretendard, 'Noto Sans KR', 'Apple SD Gothic Neo', sans-serif"

for tool in dot rsvg-convert; do
  command -v "$tool" >/dev/null 2>&1 || { echo "필요한 도구가 없습니다: $tool" >&2; exit 1; }
done

# 라이트 색 -> 다크 색 (배경, 글자·선, 서비스 채움, 서비스 테두리, 오류 경로)
to_dark() {
  sed -e 's/#ffffff/#0d1117/g' \
      -e 's/#1f2328/#e6edf3/g' \
      -e 's/#eef2ff/#1e1b4b/g' \
      -e 's/#4f46e5/#818cf8/g' \
      -e 's/#b91c1c/#f87171/g'
}

# Graphviz가 쓴 폰트 이름을 문서에 정한 폰트 목록으로 바꿔 브라우저에서도 같은 글꼴을 고르게 한다.
set_font_stack() {
  sed -e "s/font-family=\"Pretendard,[^\"]*\"/font-family=\"$FONT_STACK\"/g" \
      -e "s/font-family=\"Pretendard\"/font-family=\"$FONT_STACK\"/g"
}

shopt -s nullglob
sources=("$SRC"/*.dot)
if [ ${#sources[@]} -eq 0 ]; then
  echo "다이어그램 원본이 없습니다: $SRC" >&2
  exit 1
fi

for source in "${sources[@]}"; do
  name="$(basename "$source" .dot)"
  dot -Tsvg "$source" | set_font_stack > "$OUT/$name.svg"
  to_dark < "$source" | dot -Tsvg | set_font_stack > "$OUT/$name-dark.svg"
  rsvg-convert -w 1600 "$OUT/$name.svg" -o "$OUT/$name.png"
  rsvg-convert -w 1600 "$OUT/$name-dark.svg" -o "$OUT/$name-dark.png"
  echo "렌더 완료: $name (.svg, -dark.svg, .png, -dark.png)"
done
