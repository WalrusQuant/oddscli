"""EV calculation engine: implied probability, vig removal, EV%, edge detection."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.api.models import Bookmaker, Event, OutcomeOdds


class EVBet(BaseModel):
    """A detected +EV betting opportunity."""

    sport_key: str
    book: str
    book_title: str
    event_id: str
    home_team: str
    away_team: str
    market: str  # h2h, spreads, totals
    outcome_name: str
    outcome_point: float | None = None
    odds: float  # American odds offered by this book
    decimal_odds: float
    implied_prob: float  # Book's implied prob (with vig)
    no_vig_prob: float  # Market consensus fair probability
    fair_odds: float  # No-vig fair American odds
    ev_percentage: float
    edge: float  # decimal edge
    detected_at: datetime | None = None
    num_books: int = 0  # How many books contributed to the market average


def american_to_decimal(american: float) -> float:
    """Convert American odds to decimal odds."""
    if american >= 100:
        return (american / 100) + 1
    else:
        return (100 / abs(american)) + 1


def american_to_implied_prob(american: float) -> float:
    """Convert American odds to implied probability."""
    if american < 0:
        return abs(american) / (abs(american) + 100)
    else:
        return 100 / (american + 100)


def prob_to_american(prob: float) -> float:
    """Convert a probability to American odds."""
    if prob <= 0 or prob >= 1:
        return 0.0
    if prob >= 0.5:
        return -(prob / (1 - prob)) * 100
    else:
        return ((1 - prob) / prob) * 100


def remove_vig(probs: list[float]) -> list[float]:
    """Normalize probabilities to sum to 1 (remove vig)."""
    total = sum(probs)
    if total == 0:
        return probs
    return [p / total for p in probs]


def _get_market_outcomes(
    bookmaker: Bookmaker, market_key: str
) -> list[OutcomeOdds] | None:
    for m in bookmaker.markets:
        if m.key == market_key:
            return m.outcomes
    return None


def find_ev_bets(
    events: list[Event],
    selected_books: list[str] | None = None,
    ev_threshold: float = 2.0,
) -> list[EVBet]:
    """Find +EV bets across all events and markets.

    Uses market-average no-vig probabilities as the true odds reference.
    Compares each individual book's line against the market consensus.
    """
    ev_bets: list[EVBet] = []
    now = datetime.now()

    for event in events:
        for market_key in ("h2h", "spreads", "totals"):
            # Collect all outcomes by name+point across bookmakers
            book_outcomes: dict[str, list[tuple[Bookmaker, OutcomeOdds]]] = {}

            for bm in event.bookmakers:
                outcomes = _get_market_outcomes(bm, market_key)
                if not outcomes:
                    continue

                for outcome in outcomes:
                    key = f"{outcome.name}|{outcome.point}"
                    book_outcomes.setdefault(key, []).append((bm, outcome))

            if not book_outcomes:
                continue

            # Calculate market-average no-vig probabilities
            no_vig_probs, book_counts = _calculate_market_avg_no_vig(book_outcomes)

            # Need at least 3 books for a reliable market average
            min_books = min(book_counts.values()) if book_counts else 0
            if min_books < 3:
                continue

            # Check each book's odds against the market consensus
            for outcome_key, entries in book_outcomes.items():
                no_vig_prob = no_vig_probs.get(outcome_key)
                if no_vig_prob is None or no_vig_prob <= 0 or no_vig_prob >= 1:
                    continue

                fair_american = prob_to_american(no_vig_prob)
                n_books = book_counts.get(outcome_key, 0)

                for bm, outcome in entries:
                    if selected_books and bm.key not in selected_books:
                        continue

                    decimal_odds = american_to_decimal(outcome.price)
                    ev_pct = (no_vig_prob * decimal_odds - 1) * 100

                    if ev_pct >= ev_threshold:
                        ev_bets.append(
                            EVBet(
                                sport_key=event.sport_key,
                                book=bm.key,
                                book_title=bm.title,
                                event_id=event.id,
                                home_team=event.home_team,
                                away_team=event.away_team,
                                market=market_key,
                                outcome_name=outcome.name,
                                outcome_point=outcome.point,
                                odds=outcome.price,
                                decimal_odds=decimal_odds,
                                implied_prob=american_to_implied_prob(outcome.price),
                                no_vig_prob=no_vig_prob,
                                fair_odds=fair_american,
                                ev_percentage=ev_pct,
                                edge=no_vig_prob * decimal_odds - 1,
                                detected_at=now,
                                num_books=n_books,
                            )
                        )

    ev_bets.sort(key=lambda b: b.ev_percentage, reverse=True)
    return ev_bets


def _calculate_market_avg_no_vig(
    book_outcomes: dict[str, list[tuple[Bookmaker, OutcomeOdds]]],
) -> tuple[dict[str, float], dict[str, int]]:
    """Calculate no-vig probabilities from market average across all books.

    Returns (no_vig_probs, book_counts) where book_counts tracks how many
    books contributed to each outcome's average.
    """
    no_vig: dict[str, float] = {}
    counts: dict[str, int] = {}

    # Average the implied probability for each outcome across all books
    avg_probs: dict[str, list[float]] = {}
    for outcome_key, entries in book_outcomes.items():
        for _bm, outcome in entries:
            avg_probs.setdefault(outcome_key, []).append(
                american_to_implied_prob(outcome.price)
            )

    raw_probs = {k: sum(v) / len(v) for k, v in avg_probs.items() if v}
    for k, v in avg_probs.items():
        counts[k] = len(v)

    # Normalize to remove vig (sum to 1)
    total = sum(raw_probs.values())
    if total > 0:
        for k, p in raw_probs.items():
            no_vig[k] = p / total

    return no_vig, counts
