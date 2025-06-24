from datetime import datetime
import os
import json

LOG_DIR = "logs"

class GlobalChat:
    def __init__(self, log_file_name: str = "global_chat.log"):
        self.log: list[dict] = [] # List of message dictionaries
        self.log_file = None
        if log_file_name:
            if not os.path.exists(LOG_DIR):
                os.makedirs(LOG_DIR)
            self.log_file = os.path.join(LOG_DIR, log_file_name)
            # You could add a timestamp to the log_file_name for unique logs per game run
            # e.g., log_file_name = f"global_chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"


    def broadcast(self, sender_name: str, message: str):
        """
        Adds a message to the global chat log and writes to file.

        Args:
            sender_name: The name of the player sending the message.
            message: The content of the message.
        """
        if not isinstance(sender_name, str) or not sender_name.strip():
            print("Error: GlobalChat sender_name must be a non-empty string.")
            return
        if not isinstance(message, str) or not message.strip():
            print(f"Warning: GlobalChat message from {sender_name} is empty or not a string.")
            # Allow empty messages for now, but log a warning.
            # Depending on rules, we might want to prevent this.

        timestamp = datetime.utcnow().isoformat()
        chat_message = {
            "sender": sender_name,
            "message": message,
            "timestamp": timestamp
        }
        self.log.append(chat_message)
        print(f"[Global Chat] {timestamp} - {sender_name}: {message}") # Optional: print to console

        if self.log_file:
            try:
                with open(self.log_file, 'a') as f:
                    f.write(json.dumps(chat_message) + "\n")
            except IOError as e:
                print(f"Error writing to global chat log file {self.log_file}: {e}")

    def get_log(self, limit: int = 0) -> list[dict]:
        """
        Returns the chat log.

        Args:
            limit: If positive, returns only the last 'limit' messages. Otherwise, returns all.

        Returns:
            A list of message dictionaries.
        """
        if limit > 0:
            return self.log[-limit:]
        return self.log

    def clear_log(self):
        """Clears the chat log."""
        self.log = []

if __name__ == '__main__':
    chat = GlobalChat()
    chat.broadcast("PlayerA", "Hello everyone! Ready for a game?")
    chat.broadcast("PlayerB", "Indeed! May the best strategist win.")
    chat.broadcast("PlayerC", "PlayerA is looking weak. We should coordinate.") # Example from spec
    chat.broadcast("PlayerA", "") # Test empty message

    print("\nFull Chat Log:")
    for entry in chat.get_log():
        print(entry)

    print("\nLast 2 Messages:")
    for entry in chat.get_log(limit=2):
        print(entry)

    # Example of how it might be passed to an AI (just the log part)
    ai_relevant_log = chat.get_log(limit=10) # AI gets last 10 messages
    print("\nLog for AI (last 10):")
    print(ai_relevant_log)
