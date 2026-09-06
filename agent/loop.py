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

    for line in text.splitlines():
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        args[key.strip()] = value

    return args


PROMPT = """You are a coding agent.

You have ONE tool.

Tool name:
read_file

Tool call format:

<tool_call>
TOOL: read_file
ARGS:
path=FILE
</tool_call>

IMPORTANT:
If the user asks you to read a file, you MUST output the tool call.
Do not say you cannot access the file.
Do not explain before calling the tool.

After a tool result is provided, continue the task.

USER REQUEST:
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
            PROMPT + user_prompt
        ]

        for iteration in range(10):

            print()
            print(f"[agent iteration {iteration + 1}]")
            print()

            prompt = "\n\n".join(self.history)

            response = self.ask(prompt)

            match = TOOL_PATTERN.search(response)

            if not match:
                print()
                print("[agent] Final answer reached.")
                return response

            tool_name = match.group("tool").strip()
            args = parse_args(match.group("args"))

            print()
            print("========================================")
            print("TOOL CALL")
            print("========================================")
            print("TOOL:", tool_name)
            print("ARGS:", args)

            result = execute_tool(tool_name, args)

            print()
            print("========================================")
            print("TOOL RESULT")
            print("========================================")
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

Continue the task.
"""
            )

        return "ERROR: maximum iterations reached."
