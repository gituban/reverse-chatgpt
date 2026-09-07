from pathlib import Path
import subprocess


def list_files(path="."):
    base = Path(path).resolve()

    if not base.exists():
        return f"ERROR: path does not exist: {path}"

    if not base.is_dir():
        return f"ERROR: not a directory: {path}"

    lines = []

    for item in sorted(base.iterdir()):
        prefix = "[DIR] " if item.is_dir() else "[FILE]"
        lines.append(f"{prefix} {item.name}")

    return "\n".join(lines) if lines else "(empty directory)"


def read_file(path):
    file_path = Path(path).resolve()

    if not file_path.exists():
        return f"ERROR: file does not exist: {path}"

    if not file_path.is_file():
        return f"ERROR: not a file: {path}"

    try:
        return file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"ERROR: cannot read binary file: {path}"
    except Exception as e:
        return f"ERROR: {e}"


def search_files(pattern, path="."):
    base = Path(path).resolve()

    if not base.exists():
        return f"ERROR: path does not exist: {path}"

    results = []

    for file_path in base.rglob("*"):
        if not file_path.is_file():
            continue

        # Skip common generated/heavy directories
        if any(part in {".git", ".venv", "venv", "__pycache__"} for part in file_path.parts):
            continue

        try:
            text = file_path.read_text(encoding="utf-8")
        except Exception:
            continue

        for line_number, line in enumerate(text.splitlines(), 1):
            if pattern.lower() in line.lower():
                results.append(
                    f"{file_path.relative_to(base)}:{line_number}: {line}"
                )

                if len(results) >= 100:
                    return "\n".join(results)

    return "\n".join(results) if results else "(no matches)"


def write_file(path, content):
    file_path = Path(path).resolve()

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return f"OK: wrote {file_path}"
    except Exception as e:
        return f"ERROR: {e}"


def run_command(command):
    try:
        result = subprocess.run(
            command,
            shell=True,
            text=True,
            capture_output=True,
            timeout=120,
        )

        output = result.stdout

        if result.stderr:
            output += "\n" + result.stderr

        if not output.strip():
            output = "(no output)"

        return (
            f"EXIT_CODE: {result.returncode}\n"
            f"{output[-12000:]}"
        )

    except subprocess.TimeoutExpired:
        return "ERROR: command timed out after 120 seconds"
    except Exception as e:
        return f"ERROR: {e}"


def git_status():
    return run_command("git status --short --branch")


def git_diff():
    return run_command("git diff")


def git_log():
    return run_command("git log --oneline -10")


def git_push(remote="", branch=""):
    remote = remote.strip()
    branch = branch.strip()

    try:
        if not branch:
            current = subprocess.run(
                ["git", "branch", "--show-current"],
                text=True,
                capture_output=True,
            )

            if current.returncode != 0:
                return (
                    f"EXIT_CODE: {current.returncode}\n"
                    f"{current.stderr.strip() or '(no output)'}"
                )

            branch = current.stdout.strip()

        if not branch:
            return "ERROR: unable to determine current branch"

        if not remote:
            remote = "origin"

        result = subprocess.run(
            ["git", "push", remote, branch],
            text=True,
            capture_output=True,
        )

        output = result.stdout

        if result.stderr:
            output += "\n" + result.stderr

        return (
            f"EXIT_CODE: {result.returncode}\n"
            f"{output.strip() or '(no output)'}"
        )

    except Exception as e:
        return f"ERROR: {e}"


def git_commit(message):
    message = message.strip()

    if not message:
        return "ERROR: commit message cannot be empty"

    try:
        staged = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            text=True,
            capture_output=True,
        )

        if staged.returncode == 0:
            return "ERROR: no staged changes to commit"

        if staged.returncode != 1:
            return (
                "ERROR: unable to determine staged changes\n"
                + staged.stderr.strip()
            )

        result = subprocess.run(
            ["git", "commit", "-m", message],
            text=True,
            capture_output=True,
        )

        output = result.stdout

        if result.stderr:
            output += "\n" + result.stderr

        return (
            f"EXIT_CODE: {result.returncode}\n"
            f"{output.strip() or '(no output)'}"
        )

    except Exception as e:
        return f"ERROR: {e}"


def git_create_branch(branch):
    branch = branch.strip()

    if not branch:
        return "ERROR: branch name cannot be empty"

    if any(char in branch for char in [" ", "~", "^", ":", "?", "*", "[", "\\"]):
        return f"ERROR: invalid branch name: {branch}"

    try:
        check = subprocess.run(
            ["git", "check-ref-format", "--branch", branch],
            text=True,
            capture_output=True,
        )

        if check.returncode != 0:
            return f"ERROR: invalid branch name: {branch}"

        existing = subprocess.run(
            ["git", "rev-parse", "--verify", f"refs/heads/{branch}"],
            text=True,
            capture_output=True,
        )

        if existing.returncode == 0:
            return f"ERROR: branch already exists: {branch}"

        result = subprocess.run(
            ["git", "switch", "-c", branch],
            text=True,
            capture_output=True,
        )

        output = result.stdout

        if result.stderr:
            output += "\n" + result.stderr

        return (
            f"EXIT_CODE: {result.returncode}\n"
            f"{output.strip() or '(no output)'}"
        )

    except Exception as e:
        return f"ERROR: {e}"


def github_repo_info(repo=""):
    if repo:
        command = f"gh repo view {repo} --json nameWithOwner,description,defaultBranchRef,isPrivate,url"
    else:
        command = "gh repo view --json nameWithOwner,description,defaultBranchRef,isPrivate,url"
    return run_command(command)


def github_workflows(repo=""):
    command = "gh workflow list"
    if repo:
        command += f" --repo {repo}"
    return run_command(command)


def github_workflow_runs(repo="", limit="10"):
    command = f"gh run list --limit {limit}"
    if repo:
        command += f" --repo {repo}"
    return run_command(command)


def github_pr_create(title, body="", base="", head="", repo=""):
    title = title.strip()
    body = body.strip()
    base = base.strip()
    head = head.strip()
    repo = repo.strip()

    if not title:
        return "ERROR: PR title cannot be empty"

    try:
        if not head:
            current = subprocess.run(
                ["git", "branch", "--show-current"],
                text=True,
                capture_output=True,
            )

            if current.returncode != 0:
                return (
                    f"EXIT_CODE: {current.returncode}\n"
                    f"{current.stderr.strip() or '(no output)'}"
                )

            head = current.stdout.strip()

        if not head:
            return "ERROR: unable to determine current branch"

        command = ["gh", "pr", "create", "--title", title]

        if body:
            command.extend(["--body", body])

        if base:
            command.extend(["--base", base])

        command.extend(["--head", head])

        if repo:
            command.extend(["--repo", repo])

        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
        )

        output = result.stdout

        if result.stderr:
            output += "\n" + result.stderr

        return (
            f"EXIT_CODE: {result.returncode}\n"
            f"{output.strip() or '(no output)'}"
        )

    except Exception as e:
        return f"ERROR: {e}"


def github_workflow_run(workflow, repo="", ref=""):
    command = f"gh workflow run {workflow}"

    if repo:
        command += f" --repo {repo}"

    if ref:
        command += f" --ref {ref}"

    return run_command(command)


def github_workflow_status(run_id, repo=""):
    command = f"gh run view {run_id}"

    if repo:
        command += f" --repo {repo}"

    return run_command(command)


def github_workflow_wait(run_id, repo="", timeout="300", interval="5"):
    try:
        timeout_seconds = int(timeout)
        interval_seconds = int(interval)
    except ValueError:
        return "ERROR: timeout and interval must be integers"

    if timeout_seconds <= 0:
        return "ERROR: timeout must be greater than 0"

    if interval_seconds <= 0:
        return "ERROR: interval must be greater than 0"

    import json
    import time

    command = f"gh run view {run_id} --json status,conclusion,name,url"

    if repo:
        command += f" --repo {repo}"

    started = time.time()

    while True:
        result = subprocess.run(
            command,
            shell=True,
            text=True,
            capture_output=True,
        )

        if result.returncode != 0:
            output = result.stdout

            if result.stderr:
                output += "\n" + result.stderr

            return (
                f"EXIT_CODE: {result.returncode}\n"
                f"{output[-12000:]}"
            )

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return (
                "ERROR: invalid JSON returned by gh run view\n"
                + result.stdout[-12000:]
            )

        status = data.get("status", "")
        conclusion = data.get("conclusion")

        print(
            f"[github_workflow_wait] "
            f"status={status} conclusion={conclusion}",
            flush=True,
        )

        if status == "completed":
            return (
                "STATUS: completed\n"
                f"CONCLUSION: {conclusion}\n"
                f"NAME: {data.get('name', '')}\n"
                f"URL: {data.get('url', '')}"
            )

        if time.time() - started >= timeout_seconds:
            return (
                "ERROR: timeout waiting for workflow run\n"
                f"RUN_ID: {run_id}\n"
                f"LAST_STATUS: {status}\n"
                f"LAST_CONCLUSION: {conclusion}"
            )

        time.sleep(interval_seconds)


TOOLS = {
    "list_files": list_files,
    "read_file": read_file,
    "search_files": search_files,
    "write_file": write_file,
    "run_command": run_command,
    "git_status": git_status,
    "git_diff": git_diff,
    "git_log": git_log,
    "git_create_branch": git_create_branch,
    "git_commit": git_commit,
    "git_push": git_push,
    "github_repo_info": github_repo_info,
    "github_workflows": github_workflows,
    "github_workflow_runs": github_workflow_runs,
    "github_workflow_run": github_workflow_run,
    "github_pr_create": github_pr_create,
    "github_workflow_status": github_workflow_status,
    "github_workflow_wait": github_workflow_wait,
}


def execute_tool(name, args):
    if name not in TOOLS:
        return f"ERROR: unknown tool: {name}"

    try:
        return TOOLS[name](**args)
    except TypeError as e:
        return f"ERROR: invalid arguments: {e}"
    except Exception as e:
        return f"ERROR: {e}"
