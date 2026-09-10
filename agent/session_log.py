import atexit
import json
import os
import re
import subprocess
import uuid
from datetime import datetime
from pathlib import Path


class SessionLogger:
    """
    Persistent per-run Agent logger.

    Files:
      prompt.txt
      transcript.log
      events.jsonl
      summary.json

    Every important write is flushed immediately so an interrupted run
    still leaves useful recovery/audit information on disk.
    """

    def __init__(self, user_prompt, base_dir="logs"):
        now = datetime.now().astimezone()
        session_id = (
            now.strftime("%Y%m%d_%H%M%S")
            + "_"
            + uuid.uuid4().hex[:6]
        )

        self.started_at = now.isoformat()
        self.session_id = session_id
        self.base = Path(base_dir) / session_id
        self.base.mkdir(parents=True, exist_ok=True)

        self.prompt_path = self.base / "prompt.txt"
        self.transcript_path = self.base / "transcript.log"
        self.events_path = self.base / "events.jsonl"
        self.summary_path = self.base / "summary.json"

        self.counts = {
            "model_response": 0,
            "planner_response": 0,
            "tool_call": 0,
            "tool_result": 0,
            "commit": 0,
            "ci": 0,
            "artifact": 0,
        }

        self.status = "running"
        self.last_event = None
        self._response_kind = None
        self._response_buffer = []

        self.metadata = {
            "session_id": session_id,
            "started_at": self.started_at,
            "pid": os.getpid(),
            "cwd": os.getcwd(),
            "branch": self._git(["rev-parse", "--abbrev-ref", "HEAD"]),
            "head_start": self._git(["rev-parse", "HEAD"]),
        }

        self.prompt_path.write_text(
            user_prompt + "\n",
            encoding="utf-8",
        )

        self._append_transcript(
            "==================================================\n"
            f"SESSION: {session_id}\n"
            f"STARTED: {self.started_at}\n"
            f"BRANCH: {self.metadata['branch']}\n"
            f"HEAD: {self.metadata['head_start']}\n"
            "==================================================\n\n"
            "USER PROMPT\n"
            "-----------\n"
            f"{user_prompt}\n\n"
        )

        self.log_event(
            "session_start",
            {
                **self.metadata,
                "prompt": user_prompt,
            },
        )

        self._write_summary()
        atexit.register(self._atexit_finalize)

    def _git(self, args):
        try:
            return subprocess.check_output(
                ["git", *args],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        except Exception:
            return None

    def _now(self):
        return datetime.now().astimezone().isoformat()

    def _redact(self, value):
        """
        Conservative redaction for obvious credentials/tokens.
        Normal source code, commit SHAs, run IDs and artifact data remain.
        """
        if not isinstance(value, str):
            return value

        patterns = [
            (
                r"(?i)(authorization\s*:\s*bearer\s+)"
                r"[A-Za-z0-9._~+/=-]+",
                r"\1<REDACTED>",
            ),
            (
                r"\bgh[pousr]_[A-Za-z0-9]{20,}\b",
                "<REDACTED_GITHUB_TOKEN>",
            ),
            (
                r"\bsk-[A-Za-z0-9_-]{16,}\b",
                "<REDACTED_API_KEY>",
            ),
        ]

        out = value
        for pattern, repl in patterns:
            out = re.sub(pattern, repl, out)

        return out

    def _append_transcript(self, text):
        text = self._redact(str(text))

        with self.transcript_path.open(
            "a",
            encoding="utf-8",
        ) as f:
            f.write(text)
            f.flush()

    def log_event(self, event_type, data=None, category=None):
        data = data or {}

        record = {
            "timestamp": self._now(),
            "session_id": self.session_id,
            "event": event_type,
            "category": category,
            "data": data,
        }

        raw = json.dumps(
            record,
            ensure_ascii=False,
            default=str,
        )

        raw = self._redact(raw)

        with self.events_path.open(
            "a",
            encoding="utf-8",
        ) as f:
            f.write(raw + "\n")
            f.flush()

        if event_type in self.counts:
            self.counts[event_type] += 1

        if category in self.counts:
            self.counts[category] += 1

        self.last_event = event_type
        self._write_summary()

    def begin_response(self, kind):
        self._response_kind = kind
        self._response_buffer = []

        title = (
            "PLANNER RESPONSE"
            if kind == "planner_response"
            else "MODEL RESPONSE"
        )

        self._append_transcript(
            f"\n[{self._now()}] {title}\n"
            + "-" * len(title)
            + "\n"
        )

    def write_response_chunk(self, chunk):
        if not isinstance(chunk, str):
            return

        self._response_buffer.append(chunk)

        # Persist partial output immediately.
        self._append_transcript(chunk)

    def end_response(self):
        kind = self._response_kind or "model_response"
        response = "".join(self._response_buffer)

        self._append_transcript("\n")

        self.log_event(
            kind,
            {
                "response": response,
                "length": len(response),
            },
        )

        self._response_kind = None
        self._response_buffer = []

    def log_tool_call(self, tool_name, args):
        self._append_transcript(
            f"\n[{self._now()}] TOOL CALL\n"
            "---------\n"
            f"TOOL: {tool_name}\n"
            f"ARGS: {json.dumps(args, ensure_ascii=False, default=str)}\n"
        )

        self.log_event(
            "tool_call",
            {
                "tool": tool_name,
                "args": args,
            },
            category=self._tool_category(tool_name),
        )

    def log_tool_result(self, tool_name, args, result):
        category = self._tool_category(tool_name)

        self._append_transcript(
            f"\n[{self._now()}] TOOL RESULT\n"
            "-----------\n"
            f"TOOL: {tool_name}\n"
            f"{result}\n"
        )

        self.log_event(
            "tool_result",
            {
                "tool": tool_name,
                "args": args,
                "result": result,
            },
        )

        # Add explicit high-level event so commit/CI/artifact can be
        # searched without parsing generic tool_result records.
        if category:
            self.log_event(
                category,
                {
                    "tool": tool_name,
                    "args": args,
                    "result": result,
                },
            )

    def _tool_category(self, tool_name):
        if tool_name == "git_commit":
            return "commit"

        if "artifact" in tool_name:
            return "artifact"

        if (
            tool_name.startswith("github_workflow")
            or tool_name in {
                "github_repair_context",
                "github_repair_loop",
                "github_project_cycle_context",
            }
        ):
            return "ci"

        return None

    def mark_status(self, status):
        self.status = status
        self._write_summary()

    def _write_summary(self):
        summary = {
            **self.metadata,
            "status": self.status,
            "last_updated": self._now(),
            "last_event": self.last_event,
            "counts": self.counts,
            "head_current": self._git(["rev-parse", "HEAD"]),
            "paths": {
                "prompt": str(self.prompt_path),
                "transcript": str(self.transcript_path),
                "events": str(self.events_path),
                "summary": str(self.summary_path),
            },
        }

        tmp = self.summary_path.with_suffix(".json.tmp")

        tmp.write_text(
            json.dumps(
                summary,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        tmp.replace(self.summary_path)

    def _atexit_finalize(self):
        if self.status == "running":
            self.status = "process_exited"

        try:
            self.log_event(
                "session_end",
                {
                    "status": self.status,
                    "head_end": self._git(
                        ["rev-parse", "HEAD"]
                    ),
                },
            )
        except Exception:
            pass
