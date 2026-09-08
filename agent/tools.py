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


def detect_project(path="."):
    base = Path(path).resolve()

    if not base.exists():
        return f"ERROR: path does not exist: {path}"

    if not base.is_dir():
        return f"ERROR: not a directory: {path}"

    files = {item.name for item in base.iterdir() if item.is_file()}

    project_type = "unknown"
    build_system = "unknown"
    test_command = ""

    if "gradlew" in files or "build.gradle" in files or "build.gradle.kts" in files:
        project_type = "java_or_android"
        build_system = "gradle"
        test_command = "./gradlew test"

    elif "pom.xml" in files:
        project_type = "java"
        build_system = "maven"
        test_command = "mvn test"

    elif "package.json" in files:
        project_type = "node"
        build_system = "npm"
        test_command = "npm test"

    elif "pyproject.toml" in files:
        project_type = "python"
        build_system = "python"
        test_command = "pytest"

    elif "pytest.ini" in files or "tox.ini" in files:
        project_type = "python"
        build_system = "pytest"
        test_command = "pytest"

    elif "requirements.txt" in files:
        project_type = "python"
        build_system = "pip"
        test_command = "pytest"

    elif "Cargo.toml" in files:
        project_type = "rust"
        build_system = "cargo"
        test_command = "cargo test"

    elif "go.mod" in files:
        project_type = "go"
        build_system = "go"
        test_command = "go test ./..."

    return (
        f"PROJECT_PATH: {base}\n"
        f"PROJECT_TYPE: {project_type}\n"
        f"BUILD_SYSTEM: {build_system}\n"
        f"TEST_COMMAND: {test_command or '(unknown)'}"
    )



def project_strategy(path="."):
    """
    Convert project detection into an execution strategy.

    Returns machine-readable JSON describing lightweight local validation,
    CI build/test commands, artifact expectations, and repair guidance.
    """
    import json
    from pathlib import Path

    detected_raw = detect_project(path)

    if isinstance(detected_raw, str) and detected_raw.startswith("ERROR:"):
        return detected_raw

    data = {}

    for line in str(detected_raw).splitlines():
        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        data[key.strip()] = value.strip()

    project_type = data.get("PROJECT_TYPE", "unknown")
    build_system = data.get("BUILD_SYSTEM", "unknown")

    strategy = {
        "path": path,
        "project_type": project_type,
        "build_system": build_system,
        "local_validation": [],
        "ci_commands": [],
        "artifacts": [],
        "repair_notes": [],
    }

    if build_system == "gradle":
        root = Path(path)

        android_markers = [
            root / "AndroidManifest.xml",
            root / "app" / "src" / "main" / "AndroidManifest.xml",
        ]

        android_plugin_markers = (
            "com.android.application",
            "com.android.library",
        )

        gradle_text = ""

        for candidate in [
            root / "build.gradle",
            root / "build.gradle.kts",
            root / "app" / "build.gradle",
            root / "app" / "build.gradle.kts",
        ]:
            if candidate.exists():
                try:
                    gradle_text += "\n" + candidate.read_text(
                        errors="ignore"
                    )
                except OSError:
                    pass

        is_android = (
            any(x.exists() for x in android_markers)
            or any(x in gradle_text for x in android_plugin_markers)
        )

        strategy["framework"] = (
            "android" if is_android else "gradle"
        )

        # Per project policy, Gradle/Android builds belong on
        # GitHub Actions rather than this orchestration machine.
        strategy["local_validation"] = []

        strategy["ci_commands"] = [
            "./gradlew test",
        ]

        if is_android:
            strategy["project_type"] = "android"

            strategy["ci_commands"].append(
                "./gradlew assembleDebug"
            )

            strategy["artifacts"] = [
                "**/build/outputs/apk/**/*.apk",
            ]

            strategy["repair_notes"] = [
                "This is an Android Gradle project.",
                "Run Gradle build/test on GitHub Actions.",
                "Use assembleDebug for APK validation.",
                "Inspect Gradle failure logs before modifying source.",
            ]

        else:
            strategy["repair_notes"] = [
                "This is a non-Android Gradle project.",
                "Run Gradle tests on GitHub Actions.",
                "Do not invoke assembleDebug.",
            ]

    elif build_system == "maven":
        strategy["local_validation"] = [
            "mvn -q -DskipTests validate",
        ]

        strategy["ci_commands"] = [
            "mvn test",
        ]

        strategy["repair_notes"] = [
            "Use Maven lifecycle output to identify compile or test failures.",
        ]

    elif build_system == "npm":
        strategy["local_validation"] = [
            "npm test -- --help",
        ]

        strategy["ci_commands"] = [
            "npm ci",
            "npm test",
        ]

        strategy["repair_notes"] = [
            "Use npm ci in CI for reproducible dependency installation.",
            "Inspect package.json scripts before assuming custom build commands.",
        ]

    elif build_system in {"python", "pip", "pytest"} or project_type == "python":
        strategy["local_validation"] = [
            "python -m py_compile agent/loop.py agent/tools.py cli.py",
        ]

        strategy["ci_commands"] = [
            "pytest",
        ]

        strategy["repair_notes"] = [
            "Prefer targeted py_compile or targeted test execution before full pytest.",
            "If pytest is unavailable, inspect project metadata before installing dependencies.",
        ]

    elif build_system == "cargo":
        strategy["local_validation"] = [
            "cargo check",
        ]

        strategy["ci_commands"] = [
            "cargo test",
        ]

        strategy["repair_notes"] = [
            "Use cargo check for fast compile validation before full tests.",
        ]

    elif build_system == "go":
        strategy["local_validation"] = [
            "go test ./...",
        ]

        strategy["ci_commands"] = [
            "go test ./...",
        ]

        strategy["repair_notes"] = [
            "Use package-level failures to narrow repair scope.",
        ]

    else:
        strategy["repair_notes"] = [
            "Project type is unknown.",
            "Inspect repository files before selecting build or test commands.",
            "Do not invent a build command.",
        ]

    return json.dumps(
        strategy,
        indent=2,
        ensure_ascii=False,
    )


def run_test(command, timeout="120"):
    command = command.strip()

    if not command:
        return "ERROR: test command cannot be empty"

    try:
        timeout_seconds = int(timeout)
    except ValueError:
        return "ERROR: timeout must be an integer"

    if timeout_seconds <= 0:
        return "ERROR: timeout must be greater than 0"

    try:
        result = subprocess.run(
            command,
            shell=True,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )

        status = "PASS" if result.returncode == 0 else "FAIL"

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        return (
            f"TEST_RESULT: {status}\n"
            f"EXIT_CODE: {result.returncode}\n"
            f"COMMAND: {command}\n"
            f"STDOUT:\n{stdout or '(empty)'}\n"
            f"STDERR:\n{stderr or '(empty)'}"
        )

    except subprocess.TimeoutExpired as e:
        stdout = e.stdout or ""
        stderr = e.stderr or ""

        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")

        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")

        return (
            "TEST_RESULT: TIMEOUT\n"
            f"EXIT_CODE: -1\n"
            f"COMMAND: {command}\n"
            f"TIMEOUT: {timeout_seconds}\n"
            f"STDOUT:\n{stdout or '(empty)'}\n"
            f"STDERR:\n{stderr or '(empty)'}"
        )

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



def git_stage(path):
    """
    Stage one explicit path.

    Deliberately accepts only one path per call so the agent does not
    accidentally stage unrelated/untracked files with `git add .`.
    """
    import subprocess

    path = str(path).strip()

    if not path:
        return "ERROR: path is required"

    if path in {".", "./", "*", "-A", "--all"}:
        return "ERROR: broad staging is not allowed; stage explicit files only"

    result = subprocess.run(
        ["git", "add", "--", path],
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        return (
            "ERROR: git stage failed\n"
            + result.stderr.strip()
        )

    return f"GIT_STAGE: SUCCESS\nPATH: {path}"


def git_head_sha():
    """Return the exact current Git HEAD SHA."""
    import subprocess

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        return (
            "ERROR: unable to determine Git HEAD\n"
            + result.stderr.strip()
        )

    return result.stdout.strip()


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







def github_repair_context(
    commit_sha,
    repo="",
    workflow="agent-build-test.yml",
    branch="",
):
    """
    Produce a compact, machine-readable repair context for the Agent.

    The context contains the exact commit, workflow run and failure logs.
    It does not edit files or commit anything.
    """
    import json

    lookup = github_workflow_run_for_commit(
        commit_sha=commit_sha,
        repo=repo,
        workflow=workflow,
        branch=branch,
    )

    try:
        data = json.loads(lookup)
    except json.JSONDecodeError:
        return lookup

    if data.get("status") != "FOUND":
        return json.dumps(data, indent=2)

    run = data["run"]
    run_id = run["databaseId"]

    # Never diagnose a queued/in-progress run as a failure.
    # Wait for the exact run to finish first.
    if run.get("status") != "completed":
        wait_result = github_workflow_wait(
            str(run_id),
            repo=data["repo"],
            timeout="300",
            interval="5",
        )

        if isinstance(wait_result, str) and wait_result.startswith("ERROR:"):
            return json.dumps({
                "repair_context": True,
                "repository": data["repo"],
                "workflow": data["workflow"],
                "commit_sha": commit_sha,
                "run_id": run_id,
                "status": "WAIT_ERROR",
                "error": wait_result,
                "next_action": "STOP",
            }, indent=2, ensure_ascii=False)

    result = github_workflow_result(
        str(run_id),
        repo=data["repo"],
        include_logs="true",
    )

    try:
        result_data = json.loads(result)
    except json.JSONDecodeError:
        result_data = {
            "failed_logs": result,
        }

    conclusion = result_data.get(
        "conclusion",
        run.get("conclusion"),
    )

    run_status = result_data.get(
        "status",
        run.get("status"),
    )

    context = {
        "repair_context": True,
        "repository": data["repo"],
        "workflow": data["workflow"],
        "commit_sha": commit_sha,
        "run_id": run_id,
        "run_url": run.get("url", ""),
        "head_branch": run.get("headBranch", ""),
        "status": run_status,
        "conclusion": conclusion,
        "failed_logs": result_data.get("failed_logs", ""),
    }

    if conclusion == "success":
        context["next_action"] = "DONE"
    else:
        context["next_action"] = "ANALYZE_AND_REPAIR"

    return json.dumps(
        context,
        indent=2,
        ensure_ascii=False,
    )

def github_workflow_run_for_commit(
    commit_sha,
    repo="",
    workflow="agent-build-test.yml",
    branch="",
    timeout="180",
    interval="5",
):
    """
    Find the GitHub Actions run for an exact commit SHA.

    The commit SHA is the primary identity. A newer run from another
    commit must never be returned.
    """
    import json
    import subprocess
    import time

    if not commit_sha or len(commit_sha) < 7:
        return "ERROR: valid commit SHA is required"

    try:
        timeout_i = int(timeout)
        interval_i = int(interval)
    except ValueError:
        return "ERROR: timeout and interval must be numeric"

    if timeout_i < 10 or timeout_i > 1800:
        return "ERROR: timeout must be between 10 and 1800 seconds"

    if interval_i < 1 or interval_i > 60:
        return "ERROR: interval must be between 1 and 60 seconds"

    if not repo:
        r = subprocess.run(
            ["gh", "repo", "view", "--json", "nameWithOwner"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if r.returncode != 0:
            return "ERROR: unable to determine repository"

        try:
            repo = json.loads(r.stdout)["nameWithOwner"]
        except Exception as exc:
            return f"ERROR: invalid repository metadata: {exc}"

    deadline = time.time() + timeout_i

    while time.time() < deadline:
        cmd = [
            "gh", "run", "list",
            "--repo", repo,
            "--workflow", workflow,
            "--commit", commit_sha,
            "--limit", "20",
            "--json",
            "databaseId,status,conclusion,url,name,headBranch,headSha",
        ]

        if branch:
            cmd.extend(["--branch", branch])

        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if r.returncode != 0:
            return (
                "ERROR: unable to query workflow runs\n"
                + r.stderr.strip()
            )

        try:
            runs = json.loads(r.stdout)
        except json.JSONDecodeError:
            return "ERROR: invalid workflow-run JSON"

        exact = [
            run for run in runs
            if run.get("headSha") == commit_sha
        ]

        if exact:
            return json.dumps({
                "status": "FOUND",
                "repo": repo,
                "workflow": workflow,
                "commit_sha": commit_sha,
                "run": exact[0],
            }, indent=2)

        time.sleep(interval_i)

    return json.dumps({
        "status": "NOT_FOUND",
        "repo": repo,
        "workflow": workflow,
        "commit_sha": commit_sha,
    }, indent=2)

def github_repair_loop(
    repo="",
    branch="",
    workflow="agent-build-test.yml",
    max_iterations="3",
    wait_timeout="300",
):
    """
    Bounded GitHub Actions repair-loop coordinator.

    This coordinator observes workflow results and returns structured
    repair context. It deliberately does not modify source code itself.
    """
    import json
    import subprocess
    import time

    try:
        max_iter = int(max_iterations)
    except ValueError:
        return "ERROR: max_iterations must be numeric"

    try:
        timeout = int(wait_timeout)
    except ValueError:
        return "ERROR: wait_timeout must be numeric"

    if max_iter < 1 or max_iter > 10:
        return "ERROR: max_iterations must be between 1 and 10"

    if timeout < 30 or timeout > 1800:
        return "ERROR: wait_timeout must be between 30 and 1800 seconds"

    if not repo:
        repo_result = subprocess.run(
            ["gh", "repo", "view", "--json", "nameWithOwner"],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if repo_result.returncode != 0:
            return (
                "ERROR: unable to determine repository\n"
                + repo_result.stderr.strip()
            )

        try:
            repo = json.loads(repo_result.stdout)["nameWithOwner"]
        except Exception as exc:
            return f"ERROR: invalid repository metadata: {exc}"

    if not branch:
        branch_result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if branch_result.returncode != 0:
            return "ERROR: unable to determine current branch"

        branch = branch_result.stdout.strip()

    if not branch:
        return "ERROR: branch is required"

    # Find the latest workflow run belonging to this exact branch.
    result = subprocess.run(
        [
            "gh", "run", "list",
            "--repo", repo,
            "--workflow", workflow,
            "--branch", branch,
            "--limit", "1",
            "--json",
            "databaseId,status,conclusion,url,name,headBranch,headSha",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        return (
            "ERROR: unable to list workflow runs\n"
            + result.stderr.strip()
        )

    try:
        runs = json.loads(result.stdout)
    except json.JSONDecodeError:
        return f"ERROR: invalid workflow JSON\n{result.stdout}"

    if not runs:
        return json.dumps({
            "status": "NO_RUN",
            "repo": repo,
            "branch": branch,
            "workflow": workflow,
            "max_iterations": max_iter,
        }, indent=2)

    run = runs[0]

    run_id = run.get("databaseId")

    if not run_id:
        return "ERROR: workflow run has no databaseId"

    # Wait for an active run to finish.
    deadline = time.time() + timeout

    while run.get("status") not in ("completed", "cancelled"):
        if time.time() >= deadline:
            return json.dumps({
                "status": "TIMEOUT",
                "repo": repo,
                "branch": branch,
                "workflow": workflow,
                "run": run,
            }, indent=2)

        time.sleep(5)

        poll = subprocess.run(
            [
                "gh", "run", "view", str(run_id),
                "--repo", repo,
                "--json",
                "databaseId,status,conclusion,url,name,headBranch,headSha",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if poll.returncode != 0:
            return (
                "ERROR: workflow polling failed\n"
                + poll.stderr.strip()
            )

        try:
            run = json.loads(poll.stdout)
        except json.JSONDecodeError:
            return f"ERROR: invalid workflow status JSON\n{poll.stdout}"

    conclusion = run.get("conclusion")

    result_data = {
        "status": "PASS" if conclusion == "success" else "FAIL",
        "repo": repo,
        "branch": branch,
        "workflow": workflow,
        "run": run,
        "repair_iteration": 1,
        "max_iterations": max_iter,
    }

    if conclusion != "success":
        failure_result = github_workflow_result(
            str(run_id),
            repo=repo,
            include_logs="true",
        )

        try:
            failure_data = json.loads(failure_result)
        except json.JSONDecodeError:
            failure_data = {
                "failed_logs": failure_result,
            }

        result_data["failure"] = {
            "conclusion": conclusion,
            "failed_logs": failure_data.get("failed_logs", ""),
        }

        result_data["next_action"] = (
            "READ_FAILURE_LOG_AND_REPAIR"
        )
    else:
        result_data["next_action"] = "DONE"

    return json.dumps(result_data, indent=2, ensure_ascii=False)

def github_workflow_artifacts(run_id, repo="", name=""):
    """List artifacts belonging to a GitHub Actions workflow run."""
    import json
    import subprocess

    if not str(run_id).strip().isdigit():
        return "ERROR: run_id must be numeric"

    if repo:
        repo_name = repo
    else:
        repo_cmd = subprocess.run(
            ["gh", "repo", "view", "--json", "nameWithOwner"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if repo_cmd.returncode != 0:
            return (
                "ERROR: unable to determine repository\n"
                + repo_cmd.stderr.strip()
            )
        try:
            repo_name = json.loads(repo_cmd.stdout)["nameWithOwner"]
        except Exception as exc:
            return f"ERROR: invalid repository metadata: {exc}"

    endpoint = f"repos/{repo_name}/actions/runs/{run_id}/artifacts"

    if name:
        endpoint += "?name=" + str(name)

    result = subprocess.run(
        ["gh", "api", endpoint],
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        return (
            f"ERROR: artifact lookup failed\n"
            f"exit_code={result.returncode}\n"
            f"{result.stderr.strip()}"
        )

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return f"ERROR: invalid artifact JSON\n{result.stdout}"

    artifacts = []

    for artifact in data.get("artifacts", []):
        artifacts.append({
            "id": artifact.get("id"),
            "name": artifact.get("name"),
            "size_in_bytes": artifact.get("size_in_bytes"),
            "expired": artifact.get("expired"),
            "created_at": artifact.get("created_at"),
            "expires_at": artifact.get("expires_at"),
            "updated_at": artifact.get("updated_at"),
            "digest": artifact.get("digest"),
        })

    return json.dumps({
        "run_id": int(run_id),
        "repository": repo_name,
        "total_count": len(artifacts),
        "artifacts": artifacts,
    }, indent=2, ensure_ascii=False)


def github_workflow_download_artifact(
    run_id,
    artifact_name="",
    repo="",
    destination=".",
):
    """Download a GitHub Actions artifact from a workflow run."""
    import os
    import subprocess

    if not str(run_id).strip().isdigit():
        return "ERROR: run_id must be numeric"

    if not str(artifact_name).strip():
        return "ERROR: artifact_name is required"

    destination = os.path.abspath(os.path.expanduser(str(destination)))
    os.makedirs(destination, exist_ok=True)

    cmd = [
        "gh", "run", "download", str(run_id),
        "--name", str(artifact_name),
        "--dir", destination,
    ]

    if repo:
        cmd.extend(["--repo", repo])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return "ERROR: artifact download timed out"

    if result.returncode != 0:
        return (
            f"ERROR: artifact download failed\n"
            f"exit_code={result.returncode}\n"
            f"{result.stderr.strip()}"
        )

    return (
        "ARTIFACT_DOWNLOAD: SUCCESS\n"
        f"run_id={run_id}\n"
        f"artifact={artifact_name}\n"
        f"destination={destination}\n"
        f"{result.stdout.strip()}"
    )

def github_workflow_result(run_id, repo="", include_logs="true"):
    """Return structured result and failed logs for a GitHub Actions run."""
    import json
    import subprocess

    if not str(run_id).strip().isdigit():
        return "ERROR: run_id must be numeric"

    cmd = [
        "gh", "run", "view", str(run_id),
        "--json", "databaseId,name,status,conclusion,url,headBranch,headSha",
    ]

    if repo:
        cmd.extend(["--repo", repo])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return "ERROR: GitHub CLI timed out"

    if result.returncode != 0:
        return (
            f"ERROR: gh run view failed\n"
            f"HTTP/exit: {result.returncode}\n"
            f"{result.stderr.strip()}"
        )

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return f"ERROR: invalid JSON from gh run view\n{result.stdout}"

    conclusion = data.get("conclusion")

    if str(include_logs).lower() in ("true", "1", "yes") and conclusion not in (
        None, "", "success"
    ):
        log_cmd = [
            "gh", "run", "view", str(run_id),
            "--log-failed",
        ]

        if repo:
            log_cmd.extend(["--repo", repo])

        try:
            logs = subprocess.run(
                log_cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            data["failed_logs"] = "ERROR: failed-log retrieval timed out"
        else:
            data["failed_logs"] = (
                logs.stdout
                if logs.stdout.strip()
                else logs.stderr.strip()
            )

    return json.dumps(data, indent=2, ensure_ascii=False)

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
    "detect_project": detect_project,
    "run_test": run_test,
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
    "github_workflow_result": github_workflow_result,
    "github_workflow_artifacts": github_workflow_artifacts,
    "github_repair_loop": github_repair_loop,
    "github_workflow_run_for_commit": github_workflow_run_for_commit,
    "github_repair_context": github_repair_context,
    "github_workflow_download_artifact": github_workflow_download_artifact,
    "git_stage": git_stage,
    "git_head_sha": git_head_sha,
    "project_strategy": project_strategy,
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
