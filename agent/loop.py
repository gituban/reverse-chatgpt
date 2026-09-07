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

You can use these tools:

list_files(path)
read_file(path)
search_files(pattern, path)

When you need one of these tools, output a tool call.

Example:

<tool_call>
TOOL: list_files
ARGS:
path=.
</tool_call>

After receiving a tool result, continue the task.

Never say that you cannot access the tools.
Never invent tool results.
"""


class Agent:

    def __init__(self):
        self.gpt = ChatGPT()
        self.history = []

    def ask(self, prompt):
        output = []

        for chunk in self.gpt.reply_chat(prompt):
            if chunk:
                print(chunk, end="", flush=True)
                output.append(chunk)

        print()

        return "".join(output)

    def run(self, user_prompt):

        self.history = [
            SYSTEM,
            "USER REQUEST:\n" + user_prompt
        ]

        for iteration in range(20):

            print()
            print(f"[agent iteration {iteration + 1}]")
            print()

            response = self.ask("\n\n".join(self.history))

            match = TOOL_PATTERN.search(response)

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
