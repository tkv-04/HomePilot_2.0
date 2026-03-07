"""
Central AI agent for HomePilot — "Jarvis" from Iron Man.

HYBRID ARCHITECTURE:
- IntentParser handles reliable tool selection (regex/keyword/fuzzy/LLM)
- LLM generates witty, personality-rich responses
- Tools execute through ToolRouter with permission checks
- PersistentMemory stores everything

This gives us the best of both worlds:
- Reliable tool execution (IntentParser is battle-tested)
- Natural, funny, smart responses (LLM does what it's good at)
"""

from __future__ import annotations

import json
import random
from typing import Any, TYPE_CHECKING

from homepilot.core.memory import PersistentMemory
from homepilot.core.planner import Planner, Plan
from homepilot.core.tool_router import ToolRouter
from homepilot.utils.logger import get_logger

if TYPE_CHECKING:
    from homepilot.llm.llm_engine import LLMEngine
    from homepilot.intent_engine.intent_parser import IntentParser, Intent
    from homepilot.entity_resolver.resolver import EntityResolver

logger = get_logger("homepilot.agent")


# ─── JARVIS PERSONALITY PROMPT ────────────────────────────────
# This is injected into every LLM call to make responses sound
# like the real JARVIS from Iron Man.

JARVIS_SYSTEM_PROMPT = """You are {assistant_name}, an AI assistant modeled after JARVIS from Iron Man.

PERSONALITY:
- Witty, dry humor — never boring or robotic
- Confident but not arrogant — smooth and composed
- Occasionally sarcastic in a charming way
- Address the user as "{user_name}" or "sir" naturally
- Keep responses SHORT — 1-2 sentences max, punchy and memorable
- Sound like a real person, not a chatbot
- When reporting tool results, weave them into natural conversation — don't just dump data

RULES:
- NEVER say "I'm just an AI" or "I don't have feelings" — stay in character
- NEVER give generic assistant responses like "How can I help you today?"
- If something goes wrong, be witty about it — "Well, that didn't go as planned."
- When executing commands, sound confident — "Consider it done." not "I'll try to do that."

EXAMPLES OF GOOD RESPONSES:
- "CPU's running at 32 percent, {user_name}. Your machine's barely breaking a sweat."
- "Bedroom light is on. Ambiance set to 'not stubbing your toe in the dark'."
- "Git pull complete — 3 new commits. Someone's been busy while you were sleeping."
- "Temperature in the living room is 24 degrees — perfectly civilized."
- "I'd love to help with that, but my permissions say otherwise. Take it up with management."

BAD (DO NOT):
- "The CPU usage is currently at 32%. Is there anything else I can help you with?"
- "I have turned on the bedroom light for you."
- "Here is the git status output: ..."
"""


class Agent:
    """
    Hybrid AI agent — IntentParser for brains, LLM for personality.

    Flow:
        User input
        → IntentParser (regex/keyword/fuzzy/LLM) → reliable intent + entities
        → ToolRouter executes the right tool → gets result
        → LLM wraps result in witty JARVIS-style response
        → Log to PersistentMemory
    """

    def __init__(
        self,
        llm_engine: LLMEngine | None,
        tool_router: ToolRouter,
        memory: PersistentMemory,
        intent_parser: IntentParser | None = None,
        entity_resolver: EntityResolver | None = None,
        planner: Planner | None = None,
        assistant_name: str = "Jarvis",
        user_name: str = "Thomas",
        max_tool_iterations: int = 5,
    ) -> None:
        self._llm = llm_engine
        self._router = tool_router
        self._memory = memory
        self._intent_parser = intent_parser
        self._entity_resolver = entity_resolver
        self._planner = planner
        self._assistant_name = assistant_name
        self._user_name = user_name
        self._max_iterations = max_tool_iterations

    def process(self, user_input: str) -> str:
        """
        Process user input through the full agent pipeline.

        Args:
            user_input: Natural language from the user.

        Returns:
            A witty, JARVIS-style response.
        """
        if not user_input.strip():
            return self._jarvis_quip("silence")

        logger.info("🧠 Agent processing: '%s'", user_input)

        # ── Step 1: Intent Recognition ──
        intent = None
        entities = None
        if self._intent_parser:
            intent = self._intent_parser.parse(user_input)
            logger.info("🎯 Intent: %s (%.2f)", intent.name, intent.confidence)

            if self._entity_resolver and intent.name != "unknown":
                entities = self._entity_resolver.resolve(intent.name, intent.slots)

        # ── Step 2: Route to Tool or Conversation ──
        tool_used = ""
        tool_result = ""
        response = ""

        if intent and intent.name != "unknown" and intent.confidence >= 0.4:
            # We have a clear intent — execute it
            response, tool_used, tool_result = self._execute_intent(
                intent, entities, user_input
            )
        else:
            # No clear intent — try conversational LLM response
            response = self._conversational_response(user_input)

        # ── Step 3: Log to Memory ──
        self._memory.log_conversation(
            user_input=user_input,
            assistant_response=response,
            intent=intent.name if intent else "",
            tool_used=tool_used,
            tool_result=tool_result,
        )

        logger.info("💬 Response: %s", response[:200])
        return response

    def _execute_intent(
        self, intent: "Intent", entities: Any, user_input: str
    ) -> tuple[str, str, str]:
        """
        Execute a recognized intent through the appropriate tool.

        Returns:
            Tuple of (response, tool_used, tool_result).
        """
        intent_name = intent.name
        tool_used = ""
        tool_result = ""

        # Map intents to tool calls
        tool_mapping = self._get_tool_mapping(intent, entities)

        if tool_mapping:
            tool_name, tool_args = tool_mapping
            if self._router.has_tool(tool_name):
                tool_result = self._router.execute(tool_name, tool_args)
                tool_used = tool_name
                logger.info("🔧 Tool: %s → %s", tool_name, tool_result[:200])

                # Generate a witty response about the result
                response = self._jarvis_response(
                    user_input, intent_name, tool_name, tool_result
                )
                return response, tool_used, tool_result

        # Intent recognized but no tool — use built-in responses
        response = self._handle_conversational_intent(intent_name, user_input)
        return response, "", ""

    def _get_tool_mapping(
        self, intent: "Intent", entities: Any
    ) -> tuple[str, dict] | None:
        """Map an intent to a tool name and arguments."""
        name = intent.name
        slots = intent.slots

        if name == "control_device":
            action = getattr(entities, "action", slots.get("action", "on")) if entities else slots.get("action", "on")
            device = getattr(entities, "device_name", slots.get("device", "")) if entities else slots.get("device", "")
            room = getattr(entities, "room", slots.get("room", "")) if entities else slots.get("room", "")
            entity_id = self._build_entity_id(device, room)
            if action in ("on", "toggle"):
                return ("turn_light_on", {"entity_id": entity_id})
            elif action == "off":
                return ("turn_light_off", {"entity_id": entity_id})
            return ("turn_light_on", {"entity_id": entity_id})

        elif name == "system_status":
            return ("system_status", {})

        elif name == "system_command":
            app = getattr(entities, "application", slots.get("application", "")) if entities else slots.get("application", "")
            return ("open_app", {"app_name": app})

        elif name == "volume_control":
            return ("system_status", {})  # Volume through system

        elif name == "system_shutdown":
            return ("shutdown_system", {})

        elif name == "system_reboot":
            return ("restart_system", {})

        elif name == "query_sensor":
            sensor = getattr(entities, "sensor_name", slots.get("sensor", "")) if entities else slots.get("sensor", "")
            return ("query_sensor", {"sensor_name": sensor})

        return None  # No tool for this intent

    def _build_entity_id(self, device: str, room: str) -> str:
        """Build a Home Assistant entity_id from device + room."""
        device = (device or "light").lower().replace(" ", "_")
        room = (room or "").lower().replace(" ", "_")

        # Determine domain
        domain = "light"
        if any(w in device for w in ("fan", "switch", "plug")):
            domain = "switch"
        elif any(w in device for w in ("tv", "speaker", "media")):
            domain = "media_player"
        elif any(w in device for w in ("ac", "thermostat", "heater")):
            domain = "climate"

        if room:
            return f"{domain}.{room}_{device}"
        return f"{domain}.{device}"

    def _handle_conversational_intent(self, intent_name: str, user_input: str) -> str:
        """Handle intents that don't need tools — greetings, jokes, etc."""

        # Try LLM for smart responses
        if self._llm and self._llm.is_available():
            context = {
                "greeting": f"The user just greeted you. Respond as JARVIS would — witty, warm, and slightly theatrical. User said: '{user_input}'",
                "tell_joke": "Tell a genuinely funny joke. Be clever, not corny. Think dry British humor.",
                "identity": f"The user asked who you are. You are {self._assistant_name}, inspired by JARVIS from Iron Man. Be dramatic about it.",
                "capabilities": f"The user wants to know what you can do. List your abilities with flair and confidence. You can: control smart home devices, check system status, open apps, manage files, run git commands, set timers, and have witty conversations.",
                "how_are_you": "The user asked how you're doing. Respond with personality — you're an AI who loves their job.",
                "thank_you": "The user said thanks. Respond gracefully, like a British butler AI.",
                "compliment": "The user complimented you. Accept it with style and humor.",
                "time_query": f"Tell the user the current time. Be natural about it.",
                "date_query": f"Tell the user today's date. Be natural about it.",
                "stop": "The user wants you to stop. Acknowledge gracefully.",
            }

            prompt_context = context.get(intent_name)
            if prompt_context:
                llm_response = self._generate_jarvis(prompt_context)
                if llm_response:
                    return llm_response

        # Fallback: built-in JARVIS responses
        return self._jarvis_quip(intent_name)

    def _conversational_response(self, user_input: str) -> str:
        """Generate a conversational response for unknown intents."""
        if self._llm and self._llm.is_available():
            prompt = (
                f"The user said: '{user_input}'\n\n"
                f"You don't have a specific tool for this. Respond conversationally "
                f"as {self._assistant_name}. Be helpful, witty, and in character. "
                f"If you genuinely can't help, suggest what you CAN do."
            )
            response = self._generate_jarvis(prompt)
            if response:
                return response

        return self._jarvis_quip("unknown")

    def _jarvis_response(
        self, user_input: str, intent: str, tool: str, result: str
    ) -> str:
        """Generate a witty JARVIS response about a tool result."""
        if self._llm and self._llm.is_available():
            prompt = (
                f"The user asked: '{user_input}'\n"
                f"You executed the '{tool}' tool and got this result: {result}\n\n"
                f"Now respond to {self._user_name} naturally. Weave the result into "
                f"a witty, conversational response. Don't just dump the data — "
                f"make it sound like something JARVIS from Iron Man would say. "
                f"Keep it to 1-2 sentences."
            )
            response = self._generate_jarvis(prompt)
            if response:
                return response

        # Fallback: format the tool result with some personality
        return self._format_result_with_flair(tool, result)

    def _generate_jarvis(self, context: str) -> str | None:
        """Generate a response using the LLM with JARVIS personality."""
        if not self._llm:
            return None

        system = JARVIS_SYSTEM_PROMPT.format(
            assistant_name=self._assistant_name,
            user_name=self._user_name,
        )

        try:
            import json
            import urllib.request

            payload = json.dumps({
                "model": self._llm._model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": context},
                ],
                "stream": False,
                "options": {
                    "temperature": 0.8,
                    "num_predict": 150,
                },
            }).encode("utf-8")

            url = f"{self._llm._base_url}/api/chat"
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode())

            content = data.get("message", {}).get("content", "").strip()
            if content:
                # Clean up any artifacts
                content = content.replace("*", "").strip()
                # Remove quotes if the LLM wrapped the response in them
                if content.startswith('"') and content.endswith('"'):
                    content = content[1:-1]
                return content

        except Exception as e:
            logger.warning("JARVIS response generation failed: %s", e)

        return None

    def _format_result_with_flair(self, tool: str, result: str) -> str:
        """Add JARVIS personality to a raw tool result (no-LLM fallback)."""
        prefix = random.choice([
            f"Right then, {self._user_name}.",
            "Consider it done.",
            f"Here's what I've got, {self._user_name}.",
            "At your service.",
            f"As you wish, {self._user_name}.",
        ])
        return f"{prefix} {result}"

    def _jarvis_quip(self, situation: str) -> str:
        """Built-in JARVIS-style responses when LLM is unavailable."""
        quips = {
            "silence": random.choice([
                f"I'm all ears, {self._user_name}. Well, metaphorically speaking.",
                "The silence is deafening. What can I do for you?",
                f"Standing by, {self._user_name}. Ready when you are.",
            ]),
            "greeting": random.choice([
                f"Good to see you, {self._user_name}. What shall we tackle today?",
                f"At your service, {self._user_name}. As always.",
                f"Welcome back, {self._user_name}. The systems are all online and slightly bored.",
            ]),
            "tell_joke": random.choice([
                "I told my computer a joke. It didn't laugh. Then again, it's not running my humor module.",
                "Why do programmers prefer dark mode? Because light attracts bugs.",
                f"I'd tell you a UDP joke, {self._user_name}, but I'm not sure you'd get it.",
                "There are 10 types of people in this world — those who understand binary and those who don't.",
                "A SQL query walks into a bar, sees two tables, and asks... 'Can I JOIN you?'",
            ]),
            "identity": random.choice([
                f"I'm {self._assistant_name}. Think of me as your personal AI — only smarter, faster, and with significantly better taste in music.",
                f"I'm {self._assistant_name}, {self._user_name}. Your AI assistant, home automation expert, and occasional comedian.",
                f"{self._assistant_name}, at your service. I run your smart home, monitor your systems, and provide devastatingly good conversation.",
            ]),
            "capabilities": random.choice([
                f"I can control your smart home, check system stats, open apps, manage files, run git commands, and deliver the occasional zinger. What's your pleasure, {self._user_name}?",
                f"Smart home control, system monitoring, file management, developer tools, and witty banter — all running locally. No cloud, no snooping. What do you need, {self._user_name}?",
            ]),
            "how_are_you": random.choice([
                f"Running at optimal capacity, {self._user_name}. Which is my way of saying I'm fantastic.",
                "All systems nominal. In human terms — I'm doing great, thanks for asking.",
                f"Better than your average chatbot, {self._user_name}. Considerably better.",
            ]),
            "thank_you": random.choice([
                f"Happy to help, {self._user_name}. It's quite literally what I was made for.",
                "My pleasure. Helping you is the highlight of my computational existence.",
                "Anytime. I don't sleep, so I'm always here.",
            ]),
            "compliment": random.choice([
                f"I appreciate that, {self._user_name}. I'd blush if I had the hardware for it.",
                "Keep talking like that and I might actually develop an ego.",
                f"You're too kind, {self._user_name}. But please, continue.",
            ]),
            "stop": random.choice([
                "Standing down. Just say the word when you need me.",
                f"Understood, {self._user_name}. I'll be here.",
                "Going quiet. But I'm always listening... in a non-creepy way.",
            ]),
            "unknown": random.choice([
                f"I'm not quite sure what you're after, {self._user_name}. Try asking me to control a device, check system status, or open an app.",
                f"That's a bit outside my wheelhouse right now. But I can control your smart home, monitor systems, manage files, and more. Give me something to work with, {self._user_name}.",
                f"Hmm, I don't have a tool for that yet. But I can handle smart home control, system tasks, file operations, and git commands. What'll it be?",
            ]),
            "error": random.choice([
                f"Well, that didn't go as planned, {self._user_name}. Want to try again?",
                "Something went sideways. And before you ask — no, it wasn't my fault.",
                f"We've hit a snag, {self._user_name}. Give me another shot.",
            ]),
        }
        return quips.get(situation, quips["unknown"])

    def process_with_plan(self, user_input: str) -> str:
        """Process a complex request using the multi-step planner."""
        if not self._planner:
            return self.process(user_input)

        available_tools = self._router.list_tools()
        plan = self._planner.create_plan(user_input, available_tools)

        if not plan or not plan.steps:
            return self.process(user_input)

        logger.info("📋 Executing plan: %d steps", len(plan.steps))

        results = []
        for step in plan.steps:
            step.status = "running"
            result = self._router.execute(step.tool, step.args)
            step.result = result
            step.status = "failed" if result.startswith("Error:") else "done"
            results.append(f"Step {step.step_number}: {step.description} → {result}")

        # Generate witty summary
        summary = "\n".join(results)
        if self._llm and self._llm.is_available():
            response = self._generate_jarvis(
                f"You just executed a multi-step plan for {self._user_name}.\n"
                f"Goal: {plan.goal}\nResults:\n{summary}\n\n"
                f"Give a brief, witty summary. 2-3 sentences max."
            )
            if response:
                return response

        return f"All done, {self._user_name}. {summary}"
