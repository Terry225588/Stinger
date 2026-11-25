"""当前答案是否还能留在面板上。作废之后不再把旧答案当成这一题。"""

from __future__ import annotations

from dataclasses import dataclass

from screenmatch.match import MatchOutcome
from screenmatch.present import shows_current_answer


@dataclass
class AnswerBoard:
    outcome: MatchOutcome | None = None
    notice: str = "还没有当前答案。"
    show_current: bool = False

    def apply_match(self, outcome: MatchOutcome) -> None:
        self.outcome = outcome
        self.show_current = shows_current_answer(outcome)
        unsafe = (
            outcome.needs_review
            or not outcome.verified
            or outcome.status in {"partial", "ambiguous", "medium", "low", "none"}
        )
        self.notice = "待确认" if unsafe else ""

    def invalidate(self, reason: str) -> None:
        self.outcome = None
        self.show_current = False
        self.notice = reason
