from __future__ import annotations

import os
import json
import shutil
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


def _subprocess_env() -> dict:
    env = os.environ.copy()
    existing = [p for p in env.get("PATH", "").split(os.pathsep) if p]
    preferred = ["/opt/homebrew/bin", "/usr/local/bin"]
    merged: List[str] = []
    for item in preferred + existing:
        if item and item not in merged:
            merged.append(item)
    env["PATH"] = os.pathsep.join(merged)
    return env


def resolve_openclaw_bin(openclaw_bin: str) -> str:
    if os.path.sep in openclaw_bin:
        return openclaw_bin
    found = shutil.which(openclaw_bin)
    if found:
        return found
    for candidate in ("/opt/homebrew/bin/openclaw", "/usr/local/bin/openclaw"):
        if os.path.exists(candidate):
            return candidate
    return openclaw_bin


def gateway_healthy(openclaw_bin: str) -> bool:
    bin_path = resolve_openclaw_bin(openclaw_bin)
    env = _subprocess_env()
    try:
        proc = subprocess.run(
            [bin_path, "gateway", "health"],
            capture_output=True,
            text=True,
            timeout=15,
            env=env,
        )
    except (FileNotFoundError, PermissionError):
        return False
    return proc.returncode == 0


def send_report(
    text: str,
    cfg: AppConfig,
    dry_run: bool = False,
    max_chunk_len: int = DEFAULT_TELEGRAM_CHUNK,
) -> List[SendResult]:
    chunks = split_markdown_chunks(text, max_len=max_chunk_len)
    results: List[SendResult] = []
    bin_path = resolve_openclaw_bin(cfg.openclaw_bin)
    env = _subprocess_env()

    for idx, chunk in enumerate(chunks, start=1):
        cmd = [
            bin_path,
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
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=env)
            output = (proc.stdout or "").strip() or (proc.stderr or "").strip()
            payload = parse_json_maybe(output)
            if proc.returncode == 0:
                results.append(SendResult(idx, "ok", payload, None))
            else:
                results.append(SendResult(idx, "failed", payload, output[:500]))
        except Exception as exc:  # noqa: BLE001
            results.append(SendResult(idx, "failed", None, str(exc)))

    return results
