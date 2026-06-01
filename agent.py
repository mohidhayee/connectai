"""
agent.py — the Agent class.

An Agent is one AI participant in a collaborative task. Each Agent:
  - has a name and a role description (system prompt)
  - uses one specific provider (e.g. "groq" or "gemini")
  - keeps its own message history, so it remembers the full conversation

Think of it like a person who has a job description and remembers
everything they've said and heard during the meeting.
"""

from providers import ask


class Agent:
    def __init__(self, name, provider, role):
        """
        name:     display name shown in the scratchpad, e.g. "Planner"
        provider: key from config.PROVIDERS, e.g. "groq" or "gemini"
        role:     system prompt — what this agent is and how it should behave
        """
        self.name = name
        self.provider = provider
        self.role = role
        self.history = []  # [{"role": "user"|"assistant", "content": "..."}]

    def reply(self, user_message):
        """Send user_message to this agent and return its text reply.

        The history is updated automatically after each call, so the agent
        remembers everything across multiple turns.
        """
        self.history.append({"role": "user", "content": user_message})

        # Full messages: system prompt first, then the whole conversation history.
        messages = [{"role": "system", "content": self.role}] + self.history

        response = ask(prompt="", provider=self.provider, messages=messages)

        self.history.append({"role": "assistant", "content": response})
        return response
