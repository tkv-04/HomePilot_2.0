"""
Personality system for Jarvis.

Gives the assistant a configurable personality with
contextual response variations, greetings, and
conversational flair.
"""

from __future__ import annotations

import random
from datetime import datetime


class Personality:
    """
    Jarvis personality engine.

    Provides contextual greetings, acknowledgments,
    and conversational embellishments to make interactions
    feel natural and engaging.
    """

    def __init__(self, name: str = "Jarvis") -> None:
        self.name = name

    def greeting(self) -> str:
        """Generate a time-appropriate greeting."""
        hour = datetime.now().hour
        if hour < 6:
            time_greet = random.choice([
                "You're up early!",
                "Burning the midnight oil?",
                "Good very-early morning!",
            ])
        elif hour < 12:
            time_greet = random.choice([
                "Good morning!",
                "Morning! Hope you slept well.",
                "Good morning! Ready for today?",
            ])
        elif hour < 17:
            time_greet = random.choice([
                "Good afternoon!",
                "Hey there! How's your day going?",
                "Good afternoon! What can I do for you?",
            ])
        elif hour < 21:
            time_greet = random.choice([
                "Good evening!",
                "Evening! How can I help?",
                "Good evening! Winding down?",
            ])
        else:
            time_greet = random.choice([
                "Good night!",
                "It's getting late! How can I help?",
                "Evening! Still need something?",
            ])

        return f"{time_greet} I'm {self.name}. How can I help?"

    def acknowledge(self) -> str:
        """Casual acknowledgment before executing a command."""
        return random.choice([
            "On it.",
            "Sure thing.",
            "Right away.",
            "Consider it done.",
            "Got it.",
            "Absolutely.",
            "Coming right up.",
            "No problem.",
        ])

    def confirm_action(self, action_description: str) -> str:
        """Confirm an action was completed."""
        prefix = random.choice([
            "Done!",
            "All set!",
            "There you go.",
            "Taken care of.",
        ])
        return f"{prefix} {action_description}"

    def error_response(self) -> str:
        """Friendly error message."""
        return random.choice([
            "I'm sorry, something went wrong. Could you try that again?",
            "Hmm, that didn't work as expected. Let's try again.",
            "I ran into an issue. Could you repeat that?",
            "Oops, something went sideways. Try again?",
        ])

    def not_understood(self) -> str:
        """Response when the command isn't recognized."""
        return random.choice([
            "I didn't quite catch that. Could you rephrase?",
            "I'm not sure what you mean. Could you say it differently?",
            "Sorry, I didn't understand. Can you try again?",
            "I'm not sure how to help with that. Could you be more specific?",
        ])

    def thank_response(self) -> str:
        """Response to 'thank you'."""
        return random.choice([
            "You're welcome!",
            "Happy to help!",
            "Anytime!",
            "My pleasure!",
            "Glad I could help!",
            "No problem at all!",
        ])

    def farewell(self) -> str:
        """Farewell message."""
        hour = datetime.now().hour
        if hour < 12:
            return "Have a great morning!"
        elif hour < 17:
            return "Have a great afternoon!"
        elif hour < 21:
            return "Enjoy your evening!"
        else:
            return "Good night! Sleep well."

    def idle_prompt(self) -> str:
        """Prompt when no speech is detected after wake word."""
        return random.choice([
            "I'm listening. What can I do for you?",
            "I didn't hear anything. Try again?",
            "I'm here — go ahead.",
            "Hmm, I didn't catch anything. Could you repeat that?",
        ])

    def timer_alert(self, message: str = "") -> str:
        """Timer expiration alert."""
        prefix = random.choice([
            "Heads up!",
            "Time's up!",
            "Ding ding!",
            "Alert!",
        ])
        if message:
            return f"{prefix} {message}"
        return f"{prefix} Your timer has finished."
