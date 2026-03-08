from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import List, Optional

from hk_trade.config import AppConfig
from hk_trade.utils import parse_json_maybe, split_markdown_chunks

DEFAULT_TELEGRAM_CHUNK = 1200


@dataclass
class SendResult:
    chunk_index: int
    status: str
    response: Optional[dict]
    error: Optional[str]


def gateway_healthy(openclaw_bin: str) -> bool:
    proc = subprocess.run(
        [openclaw_bin, "gateway", "health"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    return proc.returncode == 0


def send_report(
    text: str,
    cfg: AppConfig,
    dry_run: bool = False,
    max_chunk_len: int = DEFAULT_TELEGRAM_CHUNK,
) -> List[SendResult]:
    chunks = split_markdown_chunks(text, max_len=max_chunk_len)
    results: List[SendResult] = []

    for idx, chunk in enumerate(chunks, start=1):
        cmd = [
            cfg.openclaw_bin,
            "message",
            "send",
            "--channel",
            cfg.openclaw_channel,
            "--target",
            cfg.telegram_target,
            "--message",
            chunk,
            "--json",
        ]
        if dry_run:
            cmd.append("--dry-run")

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            output = (proc.stdout or "").strip() or (proc.stderr or "").strip()
            payload = parse_json_maybe(output)
            if proc.returncode == 0:
                results.append(SendResult(idx, "ok", payload, None))
            else:
                results.append(SendResult(idx, "failed", payload, output[:500]))
        except Exception as exc:  # noqa: BLE001
            results.append(SendResult(idx, "failed", None, str(exc)))

    return results
