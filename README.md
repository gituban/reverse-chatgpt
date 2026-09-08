# reverse-chatgpt — Autonomous Coding Agent Fork

An experimental autonomous coding agent built on top of the original [`s5treak/reverse-chatgpt`](https://github.com/s5treak/reverse-chatgpt) project.

This fork adds a CLI-based coding agent capable of inspecting repositories, editing files, working with Git, interacting with GitHub Actions, analyzing CI failures, performing bounded repair cycles, and verifying build artifacts.

The current milestone is:

> **v1.0 — Autonomous Coding Agent**

The v1.0 acceptance test demonstrated an autonomous Android workflow from a single high-level goal:

```text
Goal
  ↓
Inspect project
  ↓
Detect project type
  ↓
Select project strategy
  ↓
Edit source
  ↓
Inspect diff
  ↓
Stage intended files only
  ↓
Commit
  ↓
Push
  ↓
Locate exact-SHA GitHub Actions run
  ↓
Wait for CI
  ↓
Analyze and repair if necessary
  ↓
Verify required artifacts
  ↓
Final report
```

---

## Original Project / Attribution

This repository is forked from:

**s5treak/reverse-chatgpt**

Original repository:

https://github.com/s5treak/reverse-chatgpt

The original `reverse-chatgpt` implementation and its underlying functionality are attributed to the original project and its author.

This fork, maintained under:

**gituban/reverse-chatgpt**

adds an experimental autonomous coding-agent layer on top of the original project.

The coding-agent functionality described in this README is additional development in this fork and does not claim authorship of the original `reverse-chatgpt` implementation.

---

# Autonomous Coding Agent

The main addition in this fork is the coding agent under:

```text
agent/
├── loop.py
└── tools.py
```

The agent combines an LLM-driven planning loop with executable repository, Git, GitHub Actions, project-detection, repair, and artifact-management tools.

The goal is not only to generate code, but to carry a software-engineering task through its complete lifecycle.

---

## v1.0 Capabilities

### Repository inspection

The agent can inspect a repository before making changes.

Supported operations include:

* list files
* read files
* search files
* inspect Git status
* inspect Git diff
* inspect commit history
* detect project type
* determine project-specific execution strategy

---

### File editing

The agent can write and modify source files directly.

Before committing a change, it can inspect the resulting diff and explicitly stage only the files required for the task.

Broad staging such as:

```bash
git add .
```

is intentionally avoided by the coding-agent Git tools.

This reduces the risk of accidentally committing unrelated local files.

---

### Git automation

The agent includes Git operations for:

* status inspection
* diff inspection
* log inspection
* branch creation
* explicit file staging
* commit creation
* current HEAD SHA lookup
* push

A typical autonomous sequence is:

```text
edit
→ git_diff
→ git_stage
→ git_commit
→ git_push
→ git_head_sha
```

---

## Exact-Commit CI Verification

A core design requirement is that the agent must never claim success using CI results from an older commit.

GitHub Actions runs are matched against the exact commit SHA produced by the agent.

Example lifecycle:

```text
commit A
   ↓
push
   ↓
find workflow run where headSha == commit A
   ↓
wait for completion
```

If a repair creates:

```text
commit B
```

then the previous CI result is no longer sufficient.

The agent must verify the workflow associated with **commit B**.

---

## Feature-Branch Workflow Support

GitHub workflows created only on a feature branch can be difficult to resolve through filename-based GitHub CLI lookup because workflow metadata may be resolved through the repository's default branch.

The v1.0 agent therefore supports commit-first workflow discovery.

Workflow runs can be identified using:

```text
exact commit SHA
+ branch
+ workflow display name
```

instead of relying only on:

```text
--workflow some-workflow.yml
```

This allows newly-created workflows on development branches to be verified before they exist on the default branch.

---

# Project-Aware Execution

The agent does not use the same build strategy for every repository.

It first detects the project and generates a strategy.

Example:

```text
detect_project
      ↓
project_strategy
```

The strategy can define:

* project type
* build system
* framework
* local validation commands
* CI commands
* expected artifacts
* repair guidance

---

## Python

For Python repositories, the agent avoids assuming that every project uses `pytest`.

Pytest is used only when there is repository evidence such as:

* tracked `test_*.py` files
* `pytest.ini`
* `conftest.py`
* pytest configuration or references in project metadata

Otherwise the fallback validation is:

```bash
python -m compileall -q .
```

Generated Python CI currently uses an explicit Python compatibility baseline rather than a floating `3.x` version.

Example:

```yaml
python-version: "3.12"
```

This prevents a CI workflow from unexpectedly switching to a newly released Python version that may not yet be compatible with pinned dependencies.

---

## Untracked Files Do Not Affect Strategy

Inside a Git repository, project strategy is based on tracked repository files.

For example, an unrelated local file such as:

```text
test_firefox.py
```

must not cause the agent to conclude that the project uses pytest if that file is not tracked by Git.

This keeps local experiments from changing CI behavior.

---

## Node.js

Detected Node.js projects can use a strategy based around:

```bash
npm ci
npm test
```

---

## Rust

Detected Cargo projects can use:

```bash
cargo test
```

---

## Go

Detected Go projects can use:

```bash
go test ./...
```

---

## Gradle

Generic Gradle projects use:

```bash
./gradlew test
```

The agent does **not** automatically run:

```bash
./gradlew assembleDebug
```

for every Gradle project.

That command is reserved for projects detected as Android.

---

# Android Support

Android projects are detected separately from generic Gradle projects.

Android detection can use repository evidence such as:

```text
AndroidManifest.xml
app/src/main/AndroidManifest.xml
com.android.application
com.android.library
```

A typical Android strategy is:

```text
framework: android
build system: gradle

CI:
./gradlew test
./gradlew assembleDebug

expected artifact:
**/build/outputs/apk/**/*.apk
```

---

## GitHub-Only Android Builds

The agent is designed to avoid heavy Android/Gradle execution on constrained local environments.

For Android projects:

```text
local environment
    ↓
source inspection
static validation
Git operations

GitHub Actions
    ↓
Gradle
Android SDK
tests
assembleDebug
APK generation
```

The Android build itself can therefore happen entirely on GitHub Actions.

---

## APK Artifact Verification

A successful Android workflow is not sufficient by itself.

If the project strategy expects an artifact, the agent must verify that the artifact actually exists.

For APK builds, success requires:

```text
CI conclusion == success

AND

APK artifact exists

AND

artifact is not expired

AND

artifact size > 0
```

The agent can list and download GitHub Actions artifacts using its GitHub tools.

---

# Unified Autonomous Project Controller

v1.0 introduces:

```text
github_project_cycle_context
```

This combines:

* project strategy
* exact-SHA GitHub workflow state
* CI conclusion
* failure information
* expected artifacts
* actual artifacts

into a single project-cycle context.

It produces a next action such as:

```text
WAIT
ANALYZE_AND_REPAIR
VERIFY_ARTIFACT
DONE
```

Conceptually:

```text
                   ┌────────────────────┐
                   │  exact commit SHA  │
                   └─────────┬──────────┘
                             ↓
                   project strategy
                             ↓
                    GitHub Actions run
                             ↓
               ┌─────────────┴─────────────┐
               │                           │
             failure                     success
               │                           │
               ↓                           ↓
     ANALYZE_AND_REPAIR            artifacts expected?
               │                     │           │
               │                    yes          no
               │                     │           │
               │                     ↓           ↓
               │              verify artifact   DONE
               │                     │
               └──── new commit ─────┘
```

---

# Autonomous Repair

The agent includes a bounded autonomous repair cycle.

When CI fails, the agent can:

1. identify the exact failed commit
2. retrieve failure context
3. inspect failure logs
4. inspect affected source
5. make a targeted repair
6. run appropriate lightweight validation
7. inspect the diff
8. stage only intended files
9. commit
10. push
11. obtain the new SHA
12. wait for CI on that new SHA
13. repeat when necessary

The repair loop is intentionally bounded to avoid uncontrolled repeated changes.

---

## Repair Safety Rules

The repair controller follows several important rules:

* never reuse a successful run from an older commit
* never repeatedly repair the same failed SHA
* use project-specific strategy before deciding validation
* avoid heavy local Android builds
* inspect failure logs before changing source
* use the smallest justified repair
* explicitly stage changed files
* stop after the configured repair limit

---

# v1.0 Acceptance Test

The v1.0 release was validated using the included minimal Android fixture:

```text
fixtures/android-minimal/
```

The autonomous agent received one high-level task:

```text
Change the visible Android application text

Autonomous Agent v1.0

to

Autonomous Agent v1.0 READY
```

The agent autonomously:

1. detected the Android project
2. inspected its project strategy
3. read the target Java file
4. modified the visible text
5. inspected the diff
6. staged only the target file
7. created a commit
8. pushed the branch
9. obtained the exact new commit SHA
10. located the matching Android GitHub Actions run
11. waited for CI completion
12. verified CI success
13. found the APK artifact
14. verified that the artifact was non-expired and non-empty
15. reported the commit, workflow, artifact name, and artifact size

The final acceptance commit was:

```text
2da0503daed16970527a9bb5c5c341be29439757
```

GitHub Actions run:

```text
34188210260
```

Artifact:

```text
android-fixture-debug-apk
```

The successful acceptance commit was tagged:

```text
v1.0
```

---

# Coding Agent Tools

The toolset includes operations in several groups.

## Files

```text
list_files
read_file
search_files
write_file
```

## Repository detection

```text
detect_project
project_strategy
```

## Git

```text
git_status
git_diff
git_log
git_create_branch
git_stage
git_commit
git_head_sha
git_push
```

## Tests and commands

```text
run_command
run_test
```

## GitHub repository / workflows

```text
github_repo_info
github_workflows
github_workflow_runs
github_workflow_run
github_workflow_status
github_workflow_wait
github_workflow_result
```

## GitHub exact-commit CI

```text
github_workflow_run_for_commit
github_repair_context
github_repair_loop
github_project_cycle_context
```

## GitHub artifacts

```text
github_workflow_artifacts
github_workflow_download_artifact
```

## Pull requests

```text
github_pr_create
```

## CI generation

```text
project_ci_workflow
write_project_ci_workflow
```

---

# Project-Specific CI Generation

The agent can generate GitHub Actions workflows according to detected project type.

Examples include:

### Python

```text
setup-python
dependency installation
compile/test
```

### Node.js

```text
setup-node
npm ci
npm test
```

### Rust

```text
cargo test
```

### Go

```text
setup-go
go test ./...
```

### Generic Gradle

```text
setup-java
./gradlew test
```

### Android

```text
setup-java
Android SDK
./gradlew test
./gradlew assembleDebug
upload APK artifact
```

The generator supports previewing a workflow before it is written to:

```text
.github/workflows/
```

---

# Project Structure

The fork currently contains both the original reverse-chatgpt implementation and the additional coding-agent layer.

```text
reverse-chatgpt/
├── agent/
│   ├── loop.py
│   └── tools.py
│
├── fixtures/
│   └── android-minimal/
│       ├── app/
│       ├── gradle/
│       ├── gradlew
│       ├── build.gradle
│       └── settings.gradle
│
├── .github/
│   └── workflows/
│       ├── agent-test.yml
│       ├── agent-build-test.yml
│       ├── agent-failure-test.yml
│       ├── generated-project-ci.yml
│       └── android-fixture-ci.yml
│
├── app.py
├── chat.py
├── gpt_session.py
├── build.py
├── tunsile.py
├── utils.py
├── cli.py
├── config.json
├── requirements.txt
└── README.md
```

---

# Running the Coding Agent

Create and activate a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Start the coding agent:

```bash
python cli.py
```

The CLI supports multiline prompts.

Enter the task and finish input with:

```text
Ctrl+D
```

Example task:

```text
Inspect this repository, find the requested source file,
make the required change, inspect the diff, stage only
the intended files, commit and push the result, then
verify the exact commit with GitHub Actions.
```

For Android tasks, the agent can additionally be instructed to continue until the expected APK artifact is verified.

---

# GitHub CLI

Several coding-agent features require the GitHub CLI.

Verify authentication:

```bash
gh auth status
```

If necessary:

```bash
gh auth login
```

The repository remote should also be configured correctly:

```bash
git remote -v
```

---

# Original reverse-chatgpt Functionality

The underlying project is a reverse-engineered ChatGPT client that streams responses in real time.

The original implementation includes functionality related to:

* anonymous ChatGPT sessions
* streaming responses
* browser-like request behavior
* session bootstrapping
* challenge handling
* FastAPI endpoint exposure
* direct Python class usage

These capabilities originate from the upstream `reverse-chatgpt` project unless otherwise stated.

---

## Proof of Concept

The repository includes:

```text
poc.mp4
```

If desired, it can be attached to a GitHub release or uploaded through GitHub so it can be referenced from this README.

---

# Original API Setup

## Clone

For this fork:

```bash
git clone https://github.com/gituban/reverse-chatgpt.git
cd reverse-chatgpt
```

---

## Create a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

---

## Install dependencies

```bash
pip install -r requirements.txt
```

Some Python dependencies may require platform-specific system packages depending on the Python version and operating system.

---

## Run the original test script

```bash
python test.py
```

---

## Start the FastAPI server

```bash
uvicorn app:app --host 0.0.0.0 --port 5000
```

The server will be available at:

```text
http://localhost:5000
```

---

# API Usage

## `POST /conversation`

Example request:

```http
POST /conversation
Content-Type: application/json

{
  "text": "Write a brief Vue.js tutorial"
}
```

Example using `curl`:

```bash
curl -X POST http://localhost:5000/conversation \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"text": "Explain async/await in JavaScript"}' \
  --no-buffer
```

---

## Python example

```python
import requests

response = requests.post(
    "http://localhost:5000/conversation",
    json={"text": "Write a brief Vue.js tutorial"},
    stream=True,
)

for line in response.iter_lines(decode_unicode=True):
    if line:
        print(line)
```

---

# Direct Python Usage

```python
from chat import ChatGPT

gpt = ChatGPT()

for chunk in gpt.reply_chat("What is the capital of France?"):
    print(chunk, end="", flush=True)
```

---

# Development Status

Current milestone:

```text
v1.0 Autonomous Coding Agent
```

Completed milestones include:

```text
v0.8a Structured test execution
v0.8b Project detection
v0.8c GitHub Actions build/test
v0.8d Failure log extraction
v0.8e Artifact handling
v0.8f Autonomous repair

v0.9a Project strategy selection
v0.9b Strategy-driven repair
v0.9c Project-specific CI generation
v0.9d CI installation and real execution
v0.9e Android APK end-to-end verification

v1.0a Feature-branch exact-SHA workflow lookup
v1.0b Unified autonomous project controller
v1.0c Autonomous Android change → APK
v1.0  Final autonomous acceptance test
```

---

# Experimental Status

The coding agent should still be considered experimental.

It can perform real repository operations including:

* modifying files
* creating commits
* pushing branches
* triggering CI
* interacting with GitHub

Use it on repositories and branches where automated changes are acceptable.

Review important changes before merging them into production branches.

---

# Roadmap

Potential future work includes:

* more reliable tool-selection behavior
* reduced redundant tool calls
* richer CI failure classification
* improved artifact matching
* multi-workflow project support
* better dependency/runtime detection
* automatic pull-request workflows
* repository policy awareness
* improved multi-project / monorepo handling
* stronger regression test coverage
* structured execution summaries
* v1.1 reliability and efficiency improvements

---

# Version

Current release:

```text
v1.0
```

Release milestone:

**Autonomous Coding Agent**

Acceptance tag:

```bash
git checkout v1.0
```

---

## License and Upstream Terms

The original project remains subject to its upstream license and terms.

Users of this fork should review the original repository's license as well as any additional changes introduced by this fork.

Original project:

https://github.com/s5treak/reverse-chatgpt

Fork:

https://github.com/gituban/reverse-chatgpt
