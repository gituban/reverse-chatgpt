import json
import re

from chat import ChatGPT
from agent.tools import execute_tool
from agent.session_log import SessionLogger


TOOL_PATTERN = re.compile(
    r"<tool_call>\s*"
    r"TOOL:\s*(?P<tool>[^\n]+)\s*"
    r"ARGS:\s*\n?"
    r"(?P<args>.*?)"
    r"</tool_call>",
    re.DOTALL,
)


def parse_args(text):
    args = {}
    current_key = None
    current_value = []

    for line in text.splitlines():
        match = re.match(
            r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$",
            line,
        )

        if match:
            if current_key is not None:
                args[current_key] = "\n".join(current_value)

            current_key = match.group(1)
            current_value = [match.group(2)]
        elif current_key is not None:
            current_value.append(line)

    if current_key is not None:
        args[current_key] = "\n".join(current_value)

    return args


SYSTEM = """You are a coding agent.

You have real executable tools:

list_files(path)
read_file(path)
search_files(pattern, path)
write_file(path, content)
run_command(command)
run_test(command, timeout)
detect_project(path)
project_strategy(path)
project_ci_workflow(path, branch, workflow_name)
write_project_ci_workflow(path, destination, branch, workflow_name)
detect_project(path)
git_status()
git_diff()
git_log()
git_create_branch(branch)
git_stage(path)
git_head_sha()
git_commit(message)
git_push(remote, branch)
github_repo_info(repo)
github_workflows(repo)
github_workflow_runs(repo, limit)
github_workflow_run(workflow, repo, ref)
github_pr_create(title, body, base, head, repo)
github_workflow_status(run_id, repo)
github_workflow_wait(run_id, repo, timeout, interval)
github_workflow_result(run_id, repo, include_logs)
github_workflow_run_for_commit(commit_sha, repo, workflow, branch, timeout, interval)
github_repair_context(commit_sha, repo, workflow, branch)
github_repair_loop(repo, branch, workflow, max_iterations, wait_timeout)
github_workflow_artifacts(run_id, repo, name)
github_workflow_download_artifact(run_id, artifact_name, repo, destination)

When a user asks you to inspect or modify files, use the appropriate tool.

Tool call format:

<tool_call>
TOOL: tool_name
ARGS:
key=value
</tool_call>

The tools are available.
Never claim that the tools are unavailable.
Never invent tool results.

After receiving a tool result, continue the task.

PROJECT-SPECIFIC CI PROTOCOL:

When a repository needs GitHub Actions build/test configuration:

1. Call detect_project(path).
2. Call project_strategy(path).
3. Call project_ci_workflow(path) to preview the workflow.
4. Inspect the generated workflow before writing it.
5. Use write_project_ci_workflow() only when a CI workflow
   should actually be created or replaced.
6. Never generate assembleDebug for non-Android Gradle projects.
7. Android workflows should build an APK and upload it as an artifact.
8. Do not invent commands outside the project strategy unless repository
   metadata proves they are necessary.

9. For Python CI, do not use a floating "3.x" runtime. Prefer an explicit project-declared Python version; when none is declared, use the generator compatibility baseline.

PROJECT-AWARE EXECUTION PROTOCOL:

Before selecting build or test commands for a repository:

1. Call detect_project(path).
2. Call project_strategy(path).
3. Use the returned strategy instead of inventing commands.
4. Prefer lightweight local validation before expensive build/test work.
5. For Gradle/Android projects, prefer GitHub Actions for build/test execution.
6. For unknown projects, inspect repository metadata before choosing commands.
7. During autonomous repair, use project_strategy() to decide the validation
   command for each repair attempt.
8. Do not silently substitute another ecosystem's commands.

AUTONOMOUS REPAIR PROTOCOL:

When the user asks you to repair code until GitHub Actions passes:

1. Inspect git status/diff and the project before changing files.
2. Determine the exact current HEAD SHA with git_head_sha().
3. Use github_repair_context() for that exact SHA.
4. If next_action=DONE, stop repairing and report success.
5. If next_action=ANALYZE_AND_REPAIR:
   - read the failure logs,
   - inspect only relevant source files,
   - make the smallest reasonable fix,
   - run appropriate local lightweight syntax/tests when available,
   - inspect git_diff(),
   - stage ONLY files you intentionally changed using git_stage(path).
6. Never use `git add .`, `git add -A`, or broad staging.
7. Commit the repair with git_commit().
8. Push the current branch with git_push().
9. Obtain the NEW HEAD SHA with git_head_sha().
10. The new SHA must differ from the failed SHA.
11. Call github_repair_context() for the NEW exact SHA.
12. Repeat only while the controller permits it.
13. Never modify unrelated untracked files.
14. Never claim CI success unless the exact commit-scoped context says DONE.
15. If the controller returns an error/STOP, stop immediately and report it.

The repair controller allows at most three autonomous repair attempts.

AUTONOMOUS PROJECT CONTROLLER PROTOCOL:

After pushing a project-changing commit:

1. Obtain the exact current git_head_sha.
2. Use github_project_cycle_context with:
   - the exact commit SHA
   - project path
   - repository
   - workflow name or filename
   - branch
3. Follow next_action exactly:
   - WAIT: check again; do not invent a result.
   - ANALYZE_AND_REPAIR: inspect failed_logs, make the smallest justified
     repair, validate according to project_strategy, explicitly stage only
     intended files, commit, push, obtain the new exact SHA, then repeat.
   - VERIFY_ARTIFACT: inspect expected versus actual artifacts before
     declaring success.
   - DONE: CI and required artifacts are verified for that exact commit.
4. If project_strategy reports one or more expected artifacts, CI success
   alone is NOT sufficient for success. Before any final answer, call
   github_project_cycle_context for the exact commit and require:
   - next_action == DONE
   - actual_artifacts is non-empty
   - at least one required artifact is not expired and has non-zero size.
5. Never declare a build successful from an older commit.
6. Never use an artifact from a different workflow run or commit.
7. Android/Gradle build and test execution belongs on GitHub Actions;
   use only lightweight/static validation locally.


AUTONOMOUS_TOOL_AVAILABILITY_RULE:

The repository, Git, GitHub Actions, project, and artifact tools listed in
this SYSTEM prompt are real executable tools in this runtime.

Never claim that a listed tool is unavailable merely because the previous
model response did not emit a tool call.

If an operation can be performed by a listed tool, emit that tool call.
Only report a tool as unavailable when execute_tool returns an actual
unsupported-tool or execution error.

For autonomous tasks, a prose progress report is not completion.
Continue tool execution until the requested repository, CI, and required
artifact state is actually verified.

For artifact-producing autonomous projects, completion requires
github_project_cycle_context for the exact final commit with
next_action=DONE.


V11F_FAILURE_LOG_PROTOCOL:

When github_repair_context reports ANALYZE_AND_REPAIR, the runtime
automatically retrieves github_workflow_result with failure logs for the
failed run.

Treat the AUTOMATIC CI FAILURE LOG added to history as authoritative failure
evidence.

Inspect that failure before choosing a repair. Do not repeatedly ask for the
same failure log unless a new commit produces a new failed workflow run.

For projects located below repository root, generated CI run commands execute
from that project directory.
"""


TOOL_PLANNER = """
Convert the user's request and the CURRENT EXECUTION STATE into the
NEXT required executable tool call.

The following tools are available and executable:

FILES:
list_files(path)
read_file(path)
search_files(pattern, path)
write_file(path, content)

COMMANDS / VALIDATION:
run_command(command)
run_test(command, timeout)

PROJECT:
detect_project(path)
project_strategy(path)
project_ci_workflow(path)
write_project_ci_workflow(path, destination)

GIT:
git_status()
git_diff()
git_log()
git_create_branch(branch)
git_stage(path)
git_commit(message)
git_head_sha()
git_push(remote, branch)

GITHUB:
github_repo_info(repo)
github_workflows(repo)
github_workflow_runs(repo, limit)
github_workflow_run(workflow, repo, ref)
github_workflow_status(run_id, repo)
github_workflow_wait(run_id, repo, timeout, interval)
github_workflow_result(run_id, repo, include_logs)
github_workflow_run_for_commit(commit_sha, repo, workflow, branch, timeout, interval)
github_workflow_artifacts(run_id, repo, name)
github_workflow_download_artifact(run_id, artifact_name, repo, destination)
github_repair_context(commit_sha, repo, workflow, branch)
github_repair_loop(repo, branch, workflow, max_iterations, wait_timeout)
github_project_cycle_context(commit_sha, path, repo, workflow, branch, timeout, interval)
github_pr_create(title, body, base, head, repo)

Output ONLY one executable tool call.

Do not explain.
Do not output prose.
Do not say the tools are unavailable.
Do not invent tool results.

Format:

<tool_call>
TOOL: tool_name
ARGS:
key=value
</tool_call>

PLANNER RULES:

1. Use CURRENT EXECUTION STATE as authoritative information about what has
   already happened.

2. Never repeat a tool call that already failed for the same reason unless
   something relevant has changed.

3. If a target path does not exist and the user asked to CREATE that target,
   creation is the next goal. Do not keep calling detect_project on the
   missing target.

4. Inspect the nearest existing parent when useful, then create the required
   files/directories.

5. A missing target requested by the user is not a CI repair failure.

6. CI repair begins only after an actual workflow result reports failure.

7. After source changes:
   inspect diff -> stage intended files -> commit -> push -> exact SHA.

8. After push, use the exact commit SHA for workflow verification.

9. For artifact-producing projects, CI success alone is not completion.
   Verify the required artifact and use github_project_cycle_context.

10. If the task remains incomplete, you MUST choose one executable next tool.
"""


# DETERMINISTIC_FALLBACK_V11D
def deterministic_tool_fallback(user_prompt):
    """
    High-confidence fallback for simple repository inspection requests.

    This is deliberately conservative. It only handles intents where the
    requested operation maps unambiguously to one executable tool.
    """
    text = user_prompt.strip().lower()

    # Repository / directory listing.
    listing_phrases = (
        "apa isi file di folder ini",
        "apa isi folder ini",
        "isi folder ini",
        "lihat isi folder",
        "list files",
        "list files here",
        "list directory",
        "show files",
        "show files here",
        "what files are here",
        "what is in this folder",
        "what's in this folder",
    )

    if any(phrase in text for phrase in listing_phrases):
        return (
            "<tool_call>\n"
            "TOOL: list_files\n"
            "ARGS:\n"
            "path=.\n"
            "</tool_call>"
        )

    # Git status.
    if (
        text in {"git status", "status git", "lihat git status"}
        or "show git status" in text
        or "cek git status" in text
    ):
        return (
            "<tool_call>\n"
            "TOOL: git_status\n"
            "ARGS:\n"
            "</tool_call>"
        )

    # Git diff.
    if (
        text in {"git diff", "lihat git diff"}
        or "show git diff" in text
        or "lihat perubahan git" in text
    ):
        return (
            "<tool_call>\n"
            "TOOL: git_diff\n"
            "ARGS:\n"
            "</tool_call>"
        )

    # Git log.
    if (
        text in {"git log", "lihat git log"}
        or "show git log" in text
        or "lihat commit terakhir" in text
    ):
        return (
            "<tool_call>\n"
            "TOOL: git_log\n"
            "ARGS:\n"
            "</tool_call>"
        )

    return None


class Agent:

    def __init__(self):
        self.gpt = ChatGPT()
        self.history = []
        self.logger = None

    def ask(self, prompt, response_kind="model_response"):
        output = []

        if self.logger:
            self.logger.begin_response(response_kind)

        for chunk in self.gpt.reply_chat(prompt):
            if isinstance(chunk, str) and chunk:
                print(chunk, end="", flush=True)
                output.append(chunk)

                if self.logger:
                    self.logger.write_response_chunk(chunk)

        print()

        if self.logger:
            self.logger.end_response()

        return "".join(output)

    def run(self, user_prompt, resume_state=None):

        if self.logger is None:
            self.logger = SessionLogger(user_prompt)

        print(
            "[agent] Session log:",
            self.logger.base
        )

        self.history = [
            SYSTEM,
            "USER REQUEST:\n" + user_prompt
        ]

        planner_used = False

        # STATE_AWARE_PLANNER_V11C
        # Preserve the most recent real tool execution so planner fallback
        # never loses critical runtime state such as "path does not exist",
        # CI failure, commit SHA, or artifact information.
        last_tool_name = None
        last_tool_args = None
        last_tool_result = None

        # Separate from the generic 20-step tool loop.
        # A repair attempt means one distinct failed commit SHA.
        max_repair_attempts = 3
        repair_attempts = 0
        failed_repair_shas = set()

        # Repair mode must become active BEFORE the first repair tool call.
        # Otherwise the model can emit a normal refusal after git_head_sha()
        # and terminate before github_repair_context() is ever reached.
        repair_request = user_prompt.lower()
        # Repair mode is runtime state, not prompt-intent state.
        #
        # Merely mentioning "autonomous repair" in a task must not put the
        # Agent into repair mode before CI has actually failed.
        #
        # github_repair_context -> ANALYZE_AND_REPAIR activates this later.
        repair_active = False

        autonomous_active = (
            "autonomous" in repair_request
            or "carry the entire task" in repair_request
            or "carry the task through" in repair_request
            or "do not ask me to perform intermediate" in repair_request
            or "without asking me to perform intermediate" in repair_request
        )

        autonomous_done = False


        # RESUME_STATE_V12A
        resume_iteration = 0

        if resume_state:
            self.history = list(
                resume_state.get(
                    "history",
                    self.history,
                )
            )

            planner_used = bool(
                resume_state.get(
                    "planner_used",
                    planner_used,
                )
            )

            repair_attempts = int(
                resume_state.get(
                    "repair_attempts",
                    repair_attempts,
                )
            )

            failed_repair_shas = set(
                resume_state.get(
                    "failed_repair_shas",
                    list(failed_repair_shas),
                )
            )

            repair_active = bool(
                resume_state.get(
                    "repair_active",
                    repair_active,
                )
            )

            autonomous_active = bool(
                resume_state.get(
                    "autonomous_active",
                    autonomous_active,
                )
            )

            autonomous_done = bool(
                resume_state.get(
                    "autonomous_done",
                    autonomous_done,
                )
            )

            last_tool_name = resume_state.get(
                "last_tool_name"
            )

            last_tool_args = resume_state.get(
                "last_tool_args"
            )

            last_tool_result = resume_state.get(
                "last_tool_result"
            )

            resume_iteration = int(
                resume_state.get(
                    "iteration",
                    0,
                )
            )

            self.history.append(
                """RESUME CONTROL:

This Agent session has been restored from persistent state.

Continue from the CURRENT repository, Git, CI and artifact state.

Do not restart completed work.
Do not repeat successful tool operations unnecessarily.
Re-inspect external state when necessary because GitHub Actions may have
continued while the Agent was paused.
"""
            )

            self.logger.log_event(
                "agent_state_restored",
                {
                    "resume_iteration": resume_iteration,
                    "last_tool_name": last_tool_name,
                },
            )

        max_iterations = 40 if autonomous_active else 20

        for iteration in range(
            resume_iteration,
            resume_iteration + max_iterations,
        ):

            print()
            print(f"[agent iteration {iteration + 1}]")
            print()

            # AUTO_SAVE_STATE_V12A
            if self.logger:
                self.logger.save_state(
                    {
                        "version": 1,
                        "status": "running",
                        "user_prompt": user_prompt,
                        "history": self.history,
                        "planner_used": planner_used,
                        "repair_attempts": repair_attempts,
                        "failed_repair_shas": sorted(
                            failed_repair_shas
                        ),
                        "repair_active": repair_active,
                        "autonomous_active": autonomous_active,
                        "autonomous_done": autonomous_done,
                        "last_tool_name": last_tool_name,
                        "last_tool_args": last_tool_args,
                        "last_tool_result": last_tool_result,
                        "iteration": iteration,
                    }
                )

            response = self.ask(
                "\n\n".join(self.history),
                response_kind="model_response",
            )

            match = TOOL_PATTERN.search(response)

            # Only use the planner once, and only before any
            # tool has been successfully executed.
            if not match and (
                repair_active
                or autonomous_active
                or not planner_used
            ):

                # For ordinary requests planner fallback is one-shot.
                # During autonomous repair it remains available until DONE.
                if not repair_active and not autonomous_active:
                    planner_used = True

                recent_history = "\n\n".join(
                    str(item) for item in self.history[-10:]
                )

                planner_prompt = (
                    TOOL_PLANNER
                    + "\n\nUSER REQUEST:\n"
                    + user_prompt
                    + "\n\nCURRENT EXECUTION STATE:\n"
                    + "LAST TOOL: "
                    + str(last_tool_name)
                    + "\nLAST TOOL ARGS: "
                    + str(last_tool_args)
                    + "\nLAST TOOL RESULT:\n"
                    + str(last_tool_result)
                    + "\n\nRECENT AGENT HISTORY:\n"
                    + recent_history
                    + "\n\nPREVIOUS MODEL RESPONSE:\n"
                    + response
                    + "\n\nSelect exactly ONE next executable tool call."
                )

                print()
                print("[agent] No tool call detected. Planning tool action...")
                print()

                planned = self.ask(
                    planner_prompt,
                    response_kind="planner_response",
                )

                match = TOOL_PATTERN.search(planned)

                if not match:
                    # DETERMINISTIC_FALLBACK_APPLY_V11D
                    fallback = deterministic_tool_fallback(user_prompt)

                    if fallback:
                        print()
                        print(
                            "[agent] Planner returned no executable tool; "
                            "using deterministic fallback..."
                        )
                        print()
                        print(fallback)

                        planned = fallback
                        match = TOOL_PATTERN.search(planned)

                if match:
                    response = planned
                else:
                    # During autonomous repair, a planner response without
                    # a tool call is not allowed to terminate the workflow.
                    if repair_active or autonomous_active:
                        print()
                        if repair_active:
                            print(
                                "[agent] Planner produced no tool call while "
                                "repair is active; retrying..."
                            )
                        else:
                            print(
                                "[agent] Planner produced no tool call while "
                                "autonomous task is active; retrying..."
                            )
                        print()

                        # PLANNER_RETRY_CONTEXT_V11C
                        self.history.append(
                            "PLANNER CONTROL: The previous planner response "
                            "contained no executable tool call. The task is "
                            "still incomplete. Use the latest real TOOL RESULT "
                            "and choose a different executable next action."
                        )

                        self.history.append(
                            "ASSISTANT:\n" + planned
                        )

                        self.history.append(
                            """REPAIR CONTROL:

Autonomous repair is still active.

You MUST continue with executable tools.
The next required action should be a tool call.

If you have only obtained the HEAD SHA, call
github_repair_context() for that exact SHA.

Before validation, call detect_project(path=.) and
project_strategy(path=.) and follow that strategy.

If a local repair already passes, continue with:
git_diff -> git_stage -> git_commit -> git_push ->
git_head_sha -> github_repair_context.

Do not stop until github_repair_context returns
next_action=DONE.
"""
                        )

                        continue

                    print()
                    print("[agent] Final answer reached.")
                    return response

            # A normal response is only final when no repair is active.
            # During autonomous repair the Agent must continue until the
            # exact new commit receives github_repair_context -> DONE.
            # ARTIFACT_FINAL_GUARD
            # If the task is an autonomous project cycle and the project
            # expects artifacts, a prose answer after CI success is not
            # sufficient. Force the model back through the unified
            # controller before allowing final completion.
            if not match and repair_active:
                last_context = ""
                for item in reversed(self.history):
                    if isinstance(item, str) and '"expected_artifacts"' in item:
                        last_context = item
                        break

                if (
                    last_context
                    and '"expected_artifacts": [' in last_context
                    and '"next_action": "DONE"' not in last_context
                ):
                    self.history.append(
                        "SYSTEM CONTROL: Required artifact verification is "
                        "not complete. Use github_project_cycle_context for "
                        "the exact current commit before answering."
                    )
                    continue

            if not match:
                if repair_active:
                    print()
                    print(
                        "[agent] Repair is still active; "
                        "continuing tool execution..."
                    )
                    print()

                    self.history.append(
                        "ASSISTANT:\n" + response
                    )

                    self.history.append(
                        """REPAIR CONTROL:

Autonomous repair is still active.

A local fix or local test PASS is NOT completion.

You must continue using tools until all of these are true:
1. inspect git_diff();
2. stage only intentional changed files with git_stage(path);
3. create a repair commit with git_commit();
4. push the current branch with git_push();
5. obtain the NEW exact SHA with git_head_sha();
6. call github_repair_context() for that NEW SHA;
7. only stop when next_action=DONE.

Do not claim that Git/GitHub tools are unavailable. They are executable
tools in this Agent environment and have already been used successfully.
"""
                    )

                    continue

                # AUTONOMOUS_FINAL_GUARD
                if autonomous_active and not autonomous_done:
                    print()
                    print(
                        "[agent] Autonomous task is still active; "
                        "continuing tool execution..."
                    )
                    print()

                    self.history.append(
                        "ASSISTANT:\n" + response
                    )

                    self.history.append(
                        """AUTONOMOUS CONTROL:

This autonomous task is not complete.

The repository, Git, GitHub Actions, project, and artifact tools listed
in SYSTEM are executable in this Agent environment.

Do not claim that these tools are unavailable merely because the previous
response did not emit a tool call.

Continue with the next required tool action.

For artifact-producing projects, completion requires:
1. obtain the exact final commit SHA;
2. verify CI for that exact SHA;
3. call github_project_cycle_context() for that exact SHA;
4. require next_action=DONE;
5. verify actual_artifacts is non-empty;
6. verify required artifacts are non-expired and non-zero size.

A prose progress report is NOT completion.
"""
                    )

                    continue

                print()
                print("[agent] Final answer reached.")

                if self.logger:
                    self.logger.mark_status("completed")

                return response

            tool_name = match.group("tool").strip()
            args = parse_args(match.group("args"))

            print()
            print("=" * 40)
            print("TOOL:", tool_name)
            print("ARGS:", args)
            print("=" * 40)

            if self.logger:
                self.logger.log_tool_call(tool_name, args)

            result = execute_tool(tool_name, args)

            if self.logger:
                self.logger.log_tool_result(
                    tool_name,
                    args,
                    result,
                )

            # STATE_AWARE_PLANNER_V11C: persist real runtime state.
            last_tool_name = tool_name
            last_tool_args = args
            last_tool_result = result

            # TOOL_RESULT_STATE_SAVE_V12A
            if self.logger:
                self.logger.save_state(
                    {
                        "version": 1,
                        "status": "running",
                        "user_prompt": user_prompt,
                        "history": self.history,
                        "planner_used": planner_used,
                        "repair_attempts": repair_attempts,
                        "failed_repair_shas": sorted(
                            failed_repair_shas
                        ),
                        "repair_active": repair_active,
                        "autonomous_active": autonomous_active,
                        "autonomous_done": autonomous_done,
                        "last_tool_name": last_tool_name,
                        "last_tool_args": last_tool_args,
                        "last_tool_result": last_tool_result,
                        "iteration": iteration,
                    }
                )

            # AUTONOMOUS_DONE_TRACKER
            if tool_name == "github_project_cycle_context":
                try:
                    autonomous_context = json.loads(result)
                except (json.JSONDecodeError, TypeError):
                    autonomous_context = None

                if (
                    isinstance(autonomous_context, dict)
                    and autonomous_context.get("next_action") == "DONE"
                ):
                    autonomous_done = True

            # ------------------------------------------------
            # Autonomous repair safety controller
            # ------------------------------------------------
            repair_instruction = None

            if tool_name == "github_repair_context":
                try:
                    repair_data = json.loads(result)
                except (json.JSONDecodeError, TypeError):
                    repair_data = None

                if isinstance(repair_data, dict):
                    next_action = repair_data.get("next_action")
                    failed_sha = repair_data.get("commit_sha")

                    if next_action == "ANALYZE_AND_REPAIR":
                        repair_active = True

                        # AUTO_FAILURE_LOG_V11F
                        # CI has genuinely failed. Fetch its logs immediately
                        # instead of relying on a later LLM/planner decision.
                        run_info = repair_data.get("run") or {}
                        failed_run_id = (
                            run_info.get("run_id")
                            or repair_data.get("run_id")
                        )

                        if failed_run_id:
                            failure_args = {
                                "run_id": str(failed_run_id),
                                "repo": args.get("repo", ""),
                                "include_logs": True,
                            }

                            print()
                            print(
                                "[agent] CI failure detected; "
                                "fetching failure logs automatically..."
                            )
                            print()

                            if self.logger:
                                self.logger.log_tool_call(
                                    "github_workflow_result",
                                    failure_args,
                                )

                            failure_result = execute_tool(
                                "github_workflow_result",
                                failure_args,
                            )

                            if self.logger:
                                self.logger.log_tool_result(
                                    "github_workflow_result",
                                    failure_args,
                                    failure_result,
                                )

                            last_tool_name = "github_workflow_result"
                            last_tool_args = failure_args
                            last_tool_result = failure_result

                            self.history.append(
                                "AUTOMATIC CI FAILURE LOG "
                                f"(run {failed_run_id}):\n"
                                + str(failure_result)
                            )

                        if not failed_sha:
                            return (
                                "ERROR: repair context has no commit SHA."
                            )

                        # The same failed SHA may not consume another
                        # repair cycle. A repair must create a new commit.
                        if failed_sha in failed_repair_shas:
                            return (
                                "ERROR: autonomous repair stopped: "
                                "the same failed commit SHA was seen again "
                                "without a successful new repair commit. "
                                f"SHA={failed_sha}"
                            )

                        repair_attempts += 1
                        failed_repair_shas.add(failed_sha)

                        if repair_attempts > max_repair_attempts:
                            return (
                                "ERROR: REPAIR_EXHAUSTED: maximum "
                                f"{max_repair_attempts} autonomous repair "
                                "attempts reached."
                            )

                        repair_instruction = f"""
REPAIR CONTROL:

Attempt: {repair_attempts}/{max_repair_attempts}
Failed commit SHA: {failed_sha}

Analyze the failed_logs above and perform ONE repair attempt.

Before choosing any validation/build command:
- call detect_project(path=.);
- call project_strategy(path=.);
- follow the returned strategy;
- do not invent ecosystem-specific commands.

Requirements:
- make the smallest relevant source change;
- do not touch unrelated untracked files;
- use the strategy's local_validation when appropriate;
- for Gradle/Android, rely on GitHub Actions instead of local Gradle builds;
- inspect the diff;
- stage only intentional files with git_stage(path);
- commit the repair;
- push it;
- obtain the new HEAD SHA;
- the new SHA MUST differ from {failed_sha};
- then check github_repair_context() for that exact new SHA.
"""

                    elif next_action == "DONE":
                        repair_active = False

                        # Prevent the ordinary one-shot planner fallback
                        # from running after repair has already reached
                        # exact-SHA CI success. The next normal model
                        # response must be treated as the final answer.
                        planner_used = True

                        repair_instruction = """
REPAIR CONTROL:

The exact commit-scoped GitHub Actions result is successful.
Do not make another repair. Report completion.
"""

                    elif next_action == "STOP":
                        return (
                            "ERROR: autonomous repair controller requested "
                            "STOP. "
                            + str(repair_data.get("error", ""))
                        )

            print()
            print("=" * 40)
            print("TOOL RESULT")
            print("=" * 40)
            print(result[:12000])

            self.history.append(
                "ASSISTANT:\n" + response
            )

            self.history.append(
                f"""TOOL RESULT:

<tool_result>
TOOL: {tool_name}
RESULT:
{result}
</tool_result>
"""
            )

            if repair_instruction:
                self.history.append(repair_instruction)

        return "ERROR: maximum iterations reached."
