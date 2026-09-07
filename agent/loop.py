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
"""


TOOL_PLANNER = """Convert the user's request into the NEXT required tool call.

The following tools are available and executable:

list_files(path)
read_file(path)
search_files(pattern, path)
write_file(path, content)
run_command(command)
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

        return "ERROR: maximum iterations reached."
