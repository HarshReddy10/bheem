"""State machine for the Closing Agent conversation flow.

States represent the customer's position in the closing journey.
Transitions are validated but non-fatal — invalid transitions log
a warning and proceed (useful for error recovery).
"""

import enum
from typing import Dict, List


class State(str, enum.Enum):
    GREETING = "GREETING"
    DISCOVERING_COURSE = "DISCOVERING_COURSE"
    ANSWERING_QUESTIONS = "ANSWERING_QUESTIONS"
    AWAITING_PURCHASE_CONFIRMATION = "AWAITING_PURCHASE_CONFIRMATION"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    PAID = "PAID"


class StateMachine:
    """Finite-state machine for the closing agent."""

    # Valid transitions from each state
    TRANSITIONS: Dict[State, List[State]] = {
        State.GREETING: [
            State.DISCOVERING_COURSE,
            State.ANSWERING_QUESTIONS,
        ],
        State.DISCOVERING_COURSE: [
            State.AWAITING_PURCHASE_CONFIRMATION,
            State.ANSWERING_QUESTIONS,
            State.DISCOVERING_COURSE,  # switch to different course
        ],
        State.ANSWERING_QUESTIONS: [
            State.AWAITING_PURCHASE_CONFIRMATION,
            State.DISCOVERING_COURSE,
            State.ANSWERING_QUESTIONS,  # continue asking
        ],
        State.AWAITING_PURCHASE_CONFIRMATION: [
            State.PAYMENT_PENDING,
            State.ANSWERING_QUESTIONS,
            State.DISCOVERING_COURSE,
        ],
        State.PAYMENT_PENDING: [
            State.PAID,
            State.ANSWERING_QUESTIONS,
        ],
        State.PAID: [
            State.GREETING,           # restart for new purchase
            State.ANSWERING_QUESTIONS,
        ],
    }

    @classmethod
    def is_valid_transition(cls, current_state: State, next_state: State) -> bool:
        """Check if transitioning from current_state to next_state is valid."""
        if current_state not in cls.TRANSITIONS:
            return False
        return next_state in cls.TRANSITIONS[current_state]

    @classmethod
    def get_initial_state(cls) -> State:
        return State.GREETING
