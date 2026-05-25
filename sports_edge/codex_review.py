from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any


def codex_disabled(message: str = "Local Codex analysis disabled; deterministic fallback analysis used.") -> dict[str, Any]:
    return {
        "enabled": False,
        "status": "skipped",
        "message": message,
    }


def codex_ready_state() -> dict[str, Any]:
    if os.environ.get("VERCEL"):
        return {
            "ready": False,
            "enabled": False,
            "status": "blocked",
            "message": "Vercel runtime must not use local Codex auth; deterministic output is queued for local review.",
        }
    if os.environ.get("ENABLE_LOCAL_CODEX_ANALYSIS") != "true":
        return {
            "ready": False,
            "enabled": False,
            "status": "skipped",
            "message": "ENABLE_LOCAL_CODEX_ANALYSIS is not true.",
        }
    if os.environ.get("CODEX_ANALYSIS_MODE") != "local-cli":
        return {
            "ready": False,
            "enabled": True,
            "status": "failed",
            "message": "CODEX_ANALYSIS_MODE must be local-cli.",
        }
    codex_path = shutil.which("codex")
    if not codex_path:
        return {
            "ready": False,
            "enabled": True,
            "status": "failed",
            "message": "Codex CLI not found.",
        }
    return {
        "ready": True,
        "enabled": True,
        "status": "ready",
        "message": "Local Codex CLI is available.",
        "codexPath": codex_path,
    }


def run_local_codex_review(
    analyses: list[dict[str, Any]],
    cycle_started_at: str,
    *,
    timeout_seconds: int = 90,
) -> dict[str, Any]:
    readiness = codex_ready_state()
    if not readiness["ready"]:
        if not readiness["enabled"]:
            return codex_disabled(readiness["message"])
        return {"enabled": True, "status": "failed", "message": readiness["message"]}

    prompt = {
        "task": "Return strict JSON with cycleSummary and risks. Do not invent sources or claims.",
        "cycleStartedAt": cycle_started_at,
        "markets": [
            {
                "marketTitle": row["marketTitle"],
                "snapshot": row["marketSnapshot"],
                "modelInterpretation": row["modelInterpretation"],
                "newsContext": {
                    "tier1Count": row["newsContext"]["tier1Count"],
                    "tier2Count": row["newsContext"]["tier2Count"],
                    "tier3Count": row["newsContext"]["tier3Count"],
                },
                "decisionCommentary": row["decisionCommentary"],
                "reliability": row["reliability"],
            }
            for row in analyses
        ],
    }
    model = os.environ.get("CODEX_ANALYSIS_MODEL", "gpt-5-codex")
    command = [
        str(readiness["codexPath"]),
        "exec",
        "--model",
        model,
        json.dumps(prompt, separators=(",", ":")),
    ]
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout_seconds)
    except (OSError, subprocess.SubprocessError, TimeoutError) as exc:
        return {"enabled": True, "status": "failed", "message": f"Codex CLI failed safely: {exc}"}
    if completed.returncode != 0:
        return {"enabled": True, "status": "failed", "message": f"Codex CLI exited {completed.returncode}; deterministic fallback used."}
    try:
        parsed = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {"enabled": True, "status": "failed", "message": "Codex output was not valid JSON; deterministic fallback used."}
    return {"enabled": True, "status": "success", "message": "Local Codex review completed.", "review": parsed}
