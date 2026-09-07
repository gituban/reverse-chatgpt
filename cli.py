from agent.loop import Agent


def main():
    print("===================================")
    print(" Reverse ChatGPT Coding Agent MVP")
    print("===================================")
    print("Multiline mode: tekan Ctrl+D untuk mengirim prompt")
    print("Ketik 'exit' atau 'quit' pada baris pertama untuk keluar.")
    print()

    agent = Agent()

    while True:
        try:
            first_line = input("Agent> ")

            if first_line.lower().strip() in {"exit", "quit"}:
                break

            if not first_line.strip():
                continue

            lines = [first_line]

            while True:
                try:
                    line = input("... ")
                    lines.append(line)
                except EOFError:
                    break

            prompt = "\n".join(lines)

            print()
            agent.run(prompt)
            print()

        except KeyboardInterrupt:
            print("\nExiting...")
            break

        except EOFError:
            print("\nExiting...")
            break

        except Exception as e:
            print(f"\nERROR: {e}")


if __name__ == "__main__":
    main()
