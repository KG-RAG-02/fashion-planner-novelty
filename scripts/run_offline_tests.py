"""루프백이 아닌 네트워크 연결을 모두 막고 단위 테스트를 실행한다.

사용법: python scripts/run_offline_tests.py

테스트 모듈을 import하기 전에 소켓 연결과 urllib의 urlopen을 가드로 바꾼다.
테스트는 보통 HTTP 호출을 mock한다. mock을 빠뜨린 테스트가 있으면 실제(유료일 수 있는) API에
닿지 않고 여기서 실패하며, 그 테스트가 통과하더라도 실행기는 0이 아닌 코드로 끝난다.
종료 코드: 0 통과, 1 테스트 실패, 2 외부 연결 시도 있음.
"""

from __future__ import annotations

import os
import socket
import sys
import unittest
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
LOOPBACK = {"127.0.0.1", "::1", "localhost", ""}
attempts: list[str] = []


def _host(address: object) -> str:
    return str(address[0]) if isinstance(address, tuple) and address else str(address)


_real_create_connection = socket.create_connection
_real_connect = socket.socket.connect
_real_urlopen = urllib.request.urlopen


def _guarded_create_connection(address, *args, **kwargs):
    if _host(address) not in LOOPBACK:
        attempts.append(f"create_connection {address!r}")
        raise OSError(f"오프라인 테스트: 외부 연결 차단 {address!r}")
    return _real_create_connection(address, *args, **kwargs)


def _guarded_connect(self, address):
    if isinstance(address, tuple) and _host(address) not in LOOPBACK:
        attempts.append(f"socket.connect {address!r}")
        raise OSError(f"오프라인 테스트: 외부 연결 차단 {address!r}")
    return _real_connect(self, address)


def _guarded_urlopen(url, *args, **kwargs):
    target = str(getattr(url, "full_url", url))
    if (urlparse(target).hostname or "") not in LOOPBACK:
        attempts.append(f"urlopen {target}")
        raise OSError(f"오프라인 테스트: urlopen 차단 {target!r}")
    return _real_urlopen(url, *args, **kwargs)


def main() -> int:
    # 개발자 셸의 인증 정보가 테스트 프로세스에 들어오지 않게 한다.
    for name in ("LLM_API_KEY", "OPENAI_API_KEY"):
        os.environ.pop(name, None)
    socket.create_connection = _guarded_create_connection
    socket.socket.connect = _guarded_connect
    urllib.request.urlopen = _guarded_urlopen
    sys.path.insert(0, str(ROOT / "src"))

    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT / "tests"))
    result = unittest.TextTestRunner(verbosity=int(os.environ.get("TEST_VERBOSITY", "1"))).run(suite)
    if attempts:
        print(f"\n외부 네트워크 연결 시도 {len(attempts)}건을 차단했다:", file=sys.stderr)
        for item in attempts:
            print(f"  {item}", file=sys.stderr)
        return 2
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
