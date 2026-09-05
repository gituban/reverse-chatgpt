from chat import ChatGPT
import sys

def chat():
    gpt = ChatGPT()
    
    print("ChatGPT Interactive CLI (type 'exit' to quit)")
    print("-" * 50)
    
    while True:
        try:
            prompt = input("\nYou: ")
            if prompt.lower() in ['exit', 'quit']:
                break
            
            if not prompt.strip():
                continue

            print("AI: ", end="", flush=True)
            for chunk in gpt.reply_chat(prompt):
                if chunk:
                    print(chunk, end="", flush=True)
            print()

        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"\nAn error occurred: {e}")

if __name__ == "__main__":
    chat()
