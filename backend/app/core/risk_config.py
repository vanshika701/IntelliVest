"""Phase 7 risk-profile questionnaire: the ONE place to edit questions,
answer scores and profile bands. Product decisions, kept in code so they
are reviewed and versioned like everything else.

Method (see docs/PHASE_7_PORTFOLIO.md):
- Risk CAPACITY is how much loss someone can afford (facts: horizon,
  emergency fund, income stability, existing EMIs).
- Risk TOLERANCE is how much loss they are willing to sit through
  (attitude: reaction to a fall, objective, experience, acceptable loss).
- The profile comes from the LOWER of the two. This is the usual
  suitability practice: a keen investor without a safety net still gets a
  cautious profile.

Scores and band edges are our own choices, not taken from a published
questionnaire. Change RISK_QUESTIONNAIRE_VERSION whenever any of them
change, so stored profiles can be recognised as scored under old rules.
"""

from dataclasses import dataclass
from typing import Literal

RISK_QUESTIONNAIRE_VERSION = "risk-v1"

Dimension = Literal["capacity", "tolerance"]


@dataclass(frozen=True)
class Option:
    id: str
    label: str
    score: int  # 1 (least risk) to 5 (most risk)


@dataclass(frozen=True)
class Question:
    id: str
    dimension: Dimension
    text: str
    options: tuple[Option, ...]


QUESTIONS: tuple[Question, ...] = (
    # --- Capacity: what the user can afford -----------------------------
    Question(
        "horizon",
        "capacity",
        "When will you need most of the money you plan to invest?",
        (
            Option("under_1y", "Within 1 year", 1),
            Option("1_3y", "In 1 to 3 years", 2),
            Option("3_5y", "In 3 to 5 years", 3),
            Option("5_10y", "In 5 to 10 years", 4),
            Option("over_10y", "More than 10 years from now", 5),
        ),
    ),
    Question(
        "emergency_fund",
        "capacity",
        "How many months of expenses could you cover from savings you won't invest?",
        (
            Option("none", "None", 1),
            Option("under_3m", "Less than 3 months", 2),
            Option("3_6m", "3 to 6 months", 4),
            Option("over_6m", "More than 6 months", 5),
        ),
    ),
    Question(
        "income_stability",
        "capacity",
        "How steady is your income?",
        (
            Option("none", "I have no regular income", 1),
            Option("variable", "It changes a lot from month to month", 2),
            Option("stable", "Steady salary or business income", 4),
            Option("very_stable", "Very secure, with more than one source", 5),
        ),
    ),
    Question(
        "emi_share",
        "capacity",
        "What share of your monthly income goes to loan EMIs?",
        (
            Option("over_40", "More than 40%", 1),
            Option("25_40", "25% to 40%", 2),
            Option("10_25", "10% to 25%", 4),
            Option("under_10", "Less than 10%, or no loans", 5),
        ),
    ),
    # --- Tolerance: what the user is willing to accept -------------------
    Question(
        "drop_reaction",
        "tolerance",
        "Your investments fall 20% in one month. What would you most likely do?",
        (
            Option("sell_all", "Sell everything", 1),
            Option("sell_some", "Sell some", 2),
            Option("hold", "Wait and do nothing", 3),
            Option("buy_some", "Invest a little more", 4),
            Option("buy_more", "Invest a lot more while prices are low", 5),
        ),
    ),
    Question(
        "objective",
        "tolerance",
        "What matters most to you for this money?",
        (
            Option("protect", "Not losing any of it", 1),
            Option("income", "Steady, modest returns", 2),
            Option("balanced", "A balance of growth and safety", 3),
            Option("growth", "Growth, accepting some ups and downs", 4),
            Option("max_growth", "The highest growth, accepting large swings", 5),
        ),
    ),
    Question(
        "experience",
        "tolerance",
        "What have you invested in before?",
        (
            Option("none", "Nothing yet", 1),
            Option("deposits", "Only bank FDs, RDs or PPF", 2),
            Option("funds", "Mutual funds", 3),
            Option("stocks", "Individual stocks", 4),
            Option("stocks_long", "Stocks, through at least one big market fall", 5),
        ),
    ),
    Question(
        "max_loss",
        "tolerance",
        "What is the largest fall in one year you could accept without selling?",
        (
            Option("under_5", "Less than 5%", 1),
            Option("5_10", "5% to 10%", 2),
            Option("10_20", "10% to 20%", 3),
            Option("20_30", "20% to 30%", 4),
            Option("over_30", "More than 30%", 5),
        ),
    ),
)

QUESTION_BY_ID: dict[str, Question] = {q.id: q for q in QUESTIONS}


@dataclass(frozen=True)
class RiskProfile:
    id: str
    label: str
    min_score: float  # inclusive lower edge on the 0-100 scale
    description: str


# Ordered from least to most risk. A score belongs to the last band whose
# min_score it reaches.
PROFILES: tuple[RiskProfile, ...] = (
    RiskProfile(
        "conservative", "Conservative", 0,
        "Protecting what you have matters more than growth.",
    ),
    RiskProfile(
        "moderately_conservative", "Moderately conservative", 20,
        "Mostly stable investments, with a small part aiming for growth.",
    ),
    RiskProfile(
        "moderate", "Moderate", 40,
        "A balance of growth and stability, with moderate ups and downs.",
    ),
    RiskProfile(
        "moderately_aggressive", "Moderately aggressive", 60,
        "Mostly growth investments; you can sit through sizeable falls.",
    ),
    RiskProfile(
        "aggressive", "Aggressive", 80,
        "Maximum long-term growth, accepting large and lasting falls.",
    ),
)

PROFILE_BY_ID: dict[str, RiskProfile] = {p.id: p for p in PROFILES}

# Answers that cap the profile whatever the scores say: these situations
# make large losses unaffordable. (question id, option id) -> highest profile.
PROFILE_CAPS: dict[tuple[str, str], str] = {
    ("horizon", "under_1y"): "conservative",
    ("emergency_fund", "none"): "moderately_conservative",
}

# A tolerance score this many points above capacity gets a note
# explaining why the profile is lower than the user might expect.
TOLERANCE_GAP_NOTE_POINTS = 30
