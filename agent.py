"""
agent.py — the Agent class.

An Agent is one AI participant in a collaborative task. Each Agent:
  - has a name and a role description (system prompt)
  - uses one specific model (e.g. "groq/llama-3.3-70b-versatile")
  - optionally carries its own API key (bring-your-own-key)
  - keeps its own message history, so it remembers the full conversation

Think of it like a person who has a job description and remembers
everything they've said and heard during the meeting.
"""

from providers import ask, provider_for


class Agent:
    def __init__(self, name, model, role, api_key=None):
        """
        name:    display name shown in the transcript, e.g. "Planner"
        model:   a litellm model id, e.g. "gemini/gemini-2.5-flash"
        role:    system prompt — what this agent is and how it should behave
        api_key: optional — this agent's own API key. If omitted, the key is
                 read from .env based on the model's provider.
        """
        self.name = name
        self.model = model
        self.role = role
        self.api_key = api_key
        self.history = []  # [{"role": "user"|"assistant", "content": "..."}]

    @property
    def provider(self):
        """Which company this agent's model belongs to, e.g. 'anthropic'."""
        return provider_for(self.model)

    def reply(self, user_message):
        """Send user_message to this agent and return its text reply.

        The history is updated automatically after each call, so the agent
        remembers everything across multiple turns.
        """
        self.history.append({"role": "user", "content": user_message})

        # Full messages: system prompt first, then the whole conversation history.
        messages = [{"role": "system", "content": self.role}] + self.history

        response = ask(model=self.model, messages=messages, api_key=self.api_key)

        self.history.append({"role": "assistant", "content": response})
        return response
