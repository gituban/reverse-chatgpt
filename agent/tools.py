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


TOOLS = {
    "list_files": list_files,
    "read_file": read_file,
    "search_files": search_files,
    "write_file": write_file,
    "run_command": run_command,
    "git_status": git_status,
    "git_diff": git_diff,
    "git_log": git_log,
    "github_repo_info": github_repo_info,
    "github_workflows": github_workflows,
    "github_workflow_runs": github_workflow_runs,
    "github_workflow_run": github_workflow_run,
    "github_workflow_status": github_workflow_status,
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
