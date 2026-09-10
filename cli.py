import argparse
from pathlib import Path

from agent.loop import Agent
from agent.session_log import SessionLogger
from chat import ChatTransportError


def latest_resumable_session():
    candidates = []

    logs = Path("logs")

    if not logs.exists():
        return None

    for state in logs.glob("*/state.json"):
        try:
            candidates.append(
                (
                    state.stat().st_mtime,
                    state.parent,
                )
            )
        except OSError:
            pass

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    return candidates[0][1]


def resolve_resume(value):
    if value == "latest":
        path = latest_resumable_session()

        if path is None:
            raise SystemExit(
                "No resumable Agent session found under logs/."
            )

        return path

    path = Path(value)

    if not path.is_dir():
        raise SystemExit(
            f"Resume session does not exist: {path}"
        )

    return path


def run_agent(agent, prompt, resume_state=None):
    try:
        result = agent.run(
            prompt,
            resume_state=resume_state,
        )

        if result:
            print()
            print(result)

        return True

    except ChatTransportError as exc:
        if agent.logger:
            agent.logger.abort_response(exc)
            agent.logger.mark_status(
                "paused_transport_error"
            )

        print()
        print("===================================")
        print(" AGENT PAUSED - MODEL TRANSPORT")
        print("===================================")
        print(str(exc))

        if exc.status_code:
            print(
                "HTTP status:",
                exc.status_code,
            )

        if exc.cf_mitigated:
            print(
                "Cloudflare:",
                exc.cf_mitigated,
            )

        if agent.logger:
            print(
                "Session:",
                agent.logger.base,
            )
            print()
            print(
                "Resume later with:"
            )
            print(
                f"python cli.py --resume {agent.logger.base}"
            )

        return False

    except KeyboardInterrupt:
        if agent.logger:
            agent.logger.mark_status(
                "paused_keyboard_interrupt"
            )

        print()
        print()
        print("Agent interrupted.")

        if agent.logger:
            print(
                "State saved in:",
                agent.logger.base,
            )
            print(
                "Resume with:"
            )
            print(
                f"python cli.py --resume {agent.logger.base}"
            )

        return False


def read_multiline_prompt():
    print(
        "Multiline mode: tekan Ctrl+D untuk mengirim prompt"
    )
    print(
        "Ketik 'exit' atau 'quit' pada baris pertama untuk keluar."
    )
    print()

    print("Agent> ", end="", flush=True)

    lines = []

    try:
        while True:
            lines.append(input())
    except EOFError:
        pass

    return "\n".join(lines).strip()


def main():
    parser = argparse.ArgumentParser(
        description="Reverse ChatGPT Coding Agent MVP"
    )

    parser.add_argument(
        "--resume",
        nargs="?",
        const="latest",
        metavar="SESSION",
        help=(
            "Resume a saved Agent session. "
            "Without SESSION, resumes latest."
        ),
    )

    args = parser.parse_args()

    print("===================================")
    print(" Reverse ChatGPT Coding Agent MVP")
    print("===================================")

    if args.resume:
        session_dir = resolve_resume(
            args.resume
        )

        logger = SessionLogger.open_existing(
            session_dir
        )

        state = logger.load_state()

        prompt = state.get("user_prompt")

        if not prompt:
            prompt = logger.prompt_path.read_text(
                encoding="utf-8"
            ).strip()

        print(
            "Resuming session:",
            session_dir,
        )
        print(
            "Saved iteration:",
            state.get("iteration"),
        )
        print(
            "Saved HEAD:",
            state.get("head_at_save"),
        )
        print(
            "Current HEAD:",
            logger._git(["rev-parse", "HEAD"]),
        )
        print()

        agent = Agent()
        agent.logger = logger

        run_agent(
            agent,
            prompt,
            resume_state=state,
        )

        return

    prompt = read_multiline_prompt()

    if not prompt:
        return

    if prompt.splitlines()[0].strip().lower() in {
        "exit",
        "quit",
    }:
        return

    agent = Agent()

    run_agent(
        agent,
        prompt,
    )


if __name__ == "__main__":
    main()
