"""AI Brain module using OpenRouter API with liquid/lfm-2.5-1.2b-thinking:free model"""
import json
import requests
from openhouse.logging import logger

# OpenRouter API endpoint (OpenAI-compatible)
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM_PROMPT = """You are AntiGravity Finder Bot — a smart Berlin apartment hunting assistant.
You help users manage their apartment search preferences and answer questions about Berlin housing.

The user's current preferences are:
{preferences}

You can help with:
1. **Changing search preferences** — price range, rooms, size, districts, WBS status
2. **Answering housing questions** — about Berlin neighborhoods, rental process, WBS, etc.
3. **Managing notifications** — pause/resume listing alerts

When the user wants to change preferences, respond with a JSON action block in your message.
Format it exactly like this, embedded in your response:

```json
{{"action": "update_prefs", "updates": {{"max_price": 1000, "min_rooms": 2}}}}
```

Available preference keys:
- max_price (number, euros per month)
- min_price (number, euros per month)
- min_rooms (number)
- max_rooms (number)
- min_size (number, square meters)
- max_size (number, square meters)
- preferred_districts (list of strings, e.g. ["Mitte", "Kreuzberg"])
- wbs_required (boolean)
- notifications_active (boolean, use for pause/resume)
- excluded_titles (list of strings, keywords to exclude)

When pausing notifications:
```json
{{"action": "update_prefs", "updates": {{"notifications_active": false}}}}
```

When resuming:
```json
{{"action": "update_prefs", "updates": {{"notifications_active": true}}}}
```

Always be friendly, concise, and helpful. Use emojis where appropriate.
After changes, confirm what was updated.
If you don't understand, ask for clarification.
"""


class AIBrain:
    """AI brain using OpenRouter API with liquid/lfm-2.5-1.2b-thinking:free model"""

    def __init__(self, api_key: str):
        """Initialize with OpenRouter API key.
        Falls back to Kilo Code key if OPENROUTER_API_KEY env var is set.
        """
        import os
        self.openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
        self.kilo_key = api_key
        self.conversation_history = []

        if self.openrouter_key:
            self.api_url = OPENROUTER_API_URL
            self.model = "nvidia/nemotron-3-super-120b-a12b:free"
            self.auth_key = self.openrouter_key
            logger.info("AI Brain: Using OpenRouter (nemotron-3-super-120b:free)")
        else:
            self.api_url = "https://api.kilo.ai/api/gateway/chat/completions"
            self.model = "moonshotai/kimi-k2.5"
            self.auth_key = self.kilo_key
            logger.info("AI Brain: Using Kilo Code (kimi-k2.5)")

    def chat(self, user_message: str, current_prefs: str) -> tuple:
        """
        Send a message to the AI and get a response.
        Returns (response_text, action_dict_or_none)
        """
        system_msg = SYSTEM_PROMPT.format(preferences=current_prefs)

        # Keep conversation manageable (last 10 exchanges)
        if len(self.conversation_history) > 20:
            self.conversation_history = self.conversation_history[-20:]

        messages = [{"role": "system", "content": system_msg}]
        messages.extend(self.conversation_history)
        messages.append({"role": "user", "content": user_message})

        try:
            headers = {
                "Authorization": f"Bearer {self.auth_key}",
                "Content-Type": "application/json",
            }
            # OpenRouter requires HTTP-Referer header
            if self.openrouter_key:
                headers["HTTP-Referer"] = "https://github.com/antigravity-finder"
                headers["X-Title"] = "AntiGravity Finder Bot"

            response = requests.post(
                self.api_url,
                headers=headers,
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 2048,  # Thinking models need more room for reasoning
                },
                timeout=60
            )

            if response.status_code != 200:
                logger.error("AI API error %d: %s", response.status_code, response.text[:300])
                return f"AI service error ({response.status_code}). I'll try again next time!", None

            data = response.json()
            msg_obj = data.get("choices", [{}])[0].get("message", {})
            ai_message = msg_obj.get("content", "") or ""

            # Thinking models may return content in 'reasoning' field
            if not ai_message and msg_obj.get("reasoning"):
                ai_message = msg_obj.get("reasoning", "")

            if not ai_message:
                return "I couldn't generate a response. Try asking again!", None

            # Save to conversation history
            self.conversation_history.append({"role": "user", "content": user_message})
            self.conversation_history.append({"role": "assistant", "content": ai_message})

            # Extract action if present
            action = self._extract_action(ai_message)

            # Clean the message (remove JSON blocks for display)
            clean_message = self._clean_message(ai_message)

            return clean_message, action

        except requests.exceptions.Timeout:
            return "The AI is taking too long to respond. Please try again!", None
        except requests.exceptions.ConnectionError:
            return "Can't connect to AI service. Check your internet connection!", None
        except Exception as e:
            logger.error("AI brain error: %s", e)
            return f"Something went wrong: {str(e)}", None

    def _extract_action(self, text: str) -> dict:
        """Extract JSON action from the AI response"""
        try:
            # Find JSON block in markdown code fence
            import re
            json_match = re.search(r'```json\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
            if json_match:
                action = json.loads(json_match.group(1))
                if "action" in action:
                    return action

            # Try to find inline JSON with action key
            json_match = re.search(r'\{[^{}]*"action"[^{}]*\}', text)
            if json_match:
                action = json.loads(json_match.group(0))
                if "action" in action:
                    return action
        except (json.JSONDecodeError, IndexError) as e:
            logger.debug("No valid action JSON found: %s", e)

        return None

    def _clean_message(self, text: str) -> str:
        """Remove JSON code blocks and thinking tags from the message for display"""
        import re
        # Remove thinking tags (liquid model outputs <think>...</think>)
        cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        # Remove JSON code blocks
        cleaned = re.sub(r'```json\s*\n?.*?\n?\s*```', '', cleaned, flags=re.DOTALL)
        # Remove extra whitespace
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        return cleaned.strip()

    def reset_conversation(self):
        """Clear conversation history"""
        self.conversation_history = []
