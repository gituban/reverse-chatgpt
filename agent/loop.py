import json
import re

from chat import ChatGPT
from agent.tools import execute_tool


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
        if "=" in line and not line.startswith(" "):
            if current_key is not None:
                args[current_key] = "\n".join(current_value)

            key, value = line.split("=", 1)
            current_key = key.strip()
            current_value = [value]
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
"""


TOOL_PLANNER = """Convert the user's request into the NEXT required tool call.

The following tools are available and executable:

list_files(path)
read_file(path)
search_files(pattern, path)
write_file(path, content)
run_command(command)
run_test(command, timeout)
detect_project(path)
detect_project(path)
git_status()
git_diff()
git_log()
git_create_branch(branch)
git_commit(message)
git_push(remote, branch)
github_repo_info(repo)
github_workflows(repo)
github_workflow_runs(repo, limit)
github_workflow_run(workflow, repo, ref)
github_pr_create(title, body, base, head, repo)
github_workflow_status(run_id, repo)
github_workflow_wait(run_id, repo, timeout, interval)

Output ONLY the tool call.
Do not explain.
Do not say the tools are unavailable.
Do not invent a tool result.

Format:

<tool_call>
TOOL: tool_name
ARGS:
key=value
</tool_call>

USER REQUEST:
"""


class Agent:

    def __init__(self):
        self.gpt = ChatGPT()
        self.history = []

    def ask(self, prompt):
        output = []

        for chunk in self.gpt.reply_chat(prompt):
            if isinstance(chunk, str) and chunk:
                print(chunk, end="", flush=True)
                output.append(chunk)

        print()

        return "".join(output)

    def run(self, user_prompt):

        self.history = [
            SYSTEM,
            "USER REQUEST:\n" + user_prompt
        ]

        planner_used = False

        # Separate from the generic 20-step tool loop.
        # A repair attempt means one distinct failed commit SHA.
        max_repair_attempts = 3
        repair_attempts = 0
        failed_repair_shas = set()

        for iteration in range(20):

            print()
            print(f"[agent iteration {iteration + 1}]")
            print()

            response = self.ask("\n\n".join(self.history))

            match = TOOL_PATTERN.search(response)

            # Only use the planner once, and only before any
            # tool has been successfully executed.
            if not match and not planner_used:

                planner_used = True

                planner_prompt = (
                    TOOL_PLANNER
                    + user_prompt
                    + "\n\nPREVIOUS RESPONSE:\n"
                    + response
                )

                print()
                print("[agent] No tool call detected. Planning tool action...")
                print()

                planned = self.ask(planner_prompt)

                match = TOOL_PATTERN.search(planned)

                if match:
                    response = planned
                else:
                    print()
                    print("[agent] Final answer reached.")
                    return response

            # If a tool was already executed and the model now
            # gives a normal response, that response is final.
            if not match:
                print()
                print("[agent] Final answer reached.")
                return response

            tool_name = match.group("tool").strip()
            args = parse_args(match.group("args"))

            print()
            print("=" * 40)
            print("TOOL:", tool_name)
            print("ARGS:", args)
            print("=" * 40)

            result = execute_tool(tool_name, args)

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

Requirements:
- make the smallest relevant source change;
- do not touch unrelated untracked files;
- run lightweight validation;
- inspect the diff;
- stage only intentional files with git_stage(path);
- commit the repair;
- push it;
- obtain the new HEAD SHA;
- the new SHA MUST differ from {failed_sha};
- then check github_repair_context() for that exact new SHA.
"""

                    elif next_action == "DONE":
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
