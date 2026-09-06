from agent.loop import Agent


def main():
    print("===================================")
    print(" Reverse ChatGPT Coding Agent MVP")
    print("===================================")
    print("Type 'exit' or 'quit' to exit.")
    print()

    agent = Agent()

    while True:
        try:
            prompt = input("Agent> ")

            if prompt.lower().strip() in {"exit", "quit"}:
                break

            if not prompt.strip():
                continue

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
