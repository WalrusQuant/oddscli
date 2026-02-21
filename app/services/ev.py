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
    player_name: str | None = None
    is_prop: bool = False


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


def compute_inline_ev(
    prices: list[float], counter_prices: list[float],
) -> tuple[float | None, float | None]:
    """Compute no-vig fair American odds and EV% of the best price.

    prices: all book prices for this outcome (e.g. all Over -110, -105, etc.)
    counter_prices: all book prices for the counter outcome (e.g. all Under)
    Returns (no_vig_american_odds, ev_pct_of_best) or (None, None) if < 3 books.
    """
    if len(prices) < 3 or len(counter_prices) < 3:
        return None, None

    # Average implied prob for each side
    avg_prob = sum(american_to_implied_prob(p) for p in prices) / len(prices)
    avg_counter = sum(american_to_implied_prob(p) for p in counter_prices) / len(counter_prices)

    # Normalize to remove vig
    total = avg_prob + avg_counter
    if total <= 0:
        return None, None
    no_vig_prob = avg_prob / total

    if no_vig_prob <= 0 or no_vig_prob >= 1:
        return None, None

    fair_american = prob_to_american(no_vig_prob)

    # EV% of the best available price
    best = max(prices)
    best_decimal = american_to_decimal(best)
    ev_pct = (no_vig_prob * best_decimal - 1) * 100

    return fair_american, ev_pct


def _effective_price(
    outcome: OutcomeOdds, bm: Bookmaker, dfs_books: dict[str, float] | None,
) -> float:
    """Return configured DFS odds or actual book price."""
    if dfs_books and bm.key in dfs_books:
        return dfs_books[bm.key]
    return outcome.price


def find_ev_bets(
    events: list[Event],
    selected_books: list[str] | None = None,
    ev_threshold: float = 2.0,
    is_props: bool = False,
    dfs_books: dict[str, float] | None = None,
) -> list[EVBet]:
    """Find +EV bets across all events and markets.

    Uses market-average no-vig probabilities as the true odds reference.
    Compares each individual book's line against the market consensus.

    When is_props=True, processes each (player, point) pair independently
    so normalization is correct (Over + Under at a specific line sum to 1).
    """
    ev_bets: list[EVBet] = []
    now = datetime.now()

    for event in events:
        if is_props:
            _find_prop_ev(
                event, ev_bets, now, selected_books, ev_threshold, dfs_books,
            )
        else:
            _find_game_ev(
                event, ev_bets, now, selected_books, ev_threshold, dfs_books,
            )

    ev_bets.sort(key=lambda b: b.ev_percentage, reverse=True)
    return ev_bets


def _find_game_ev(
    event: Event,
    ev_bets: list[EVBet],
    now: datetime,
    selected_books: list[str] | None,
    ev_threshold: float,
    dfs_books: dict[str, float] | None,
) -> None:
    """Find +EV bets for standard game markets (h2h, spreads, totals)."""
    for market_key in ("h2h", "spreads", "totals"):
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

        no_vig_probs, book_counts = _calculate_market_avg_no_vig(
            book_outcomes, dfs_books,
        )

        min_books = min(book_counts.values()) if book_counts else 0
        if min_books < 3:
            continue

        _emit_ev_bets(
            event, market_key, book_outcomes, no_vig_probs, book_counts,
            ev_bets, now, selected_books, ev_threshold, dfs_books,
        )


def _find_prop_ev(
    event: Event,
    ev_bets: list[EVBet],
    now: datetime,
    selected_books: list[str] | None,
    ev_threshold: float,
    dfs_books: dict[str, float] | None,
) -> None:
    """Find +EV bets for props — normalizes each (player, point) pair separately."""
    # Discover all prop market keys on this event
    market_keys: set[str] = set()
    for bm in event.bookmakers:
        for m in bm.markets:
            market_keys.add(m.key)

    for market_key in market_keys:
        # Collect outcomes keyed by (description, point) pair
        # Each pair groups Over + Under at the same line for the same player
        pairs: dict[str, dict[str, list[tuple[Bookmaker, OutcomeOdds]]]] = {}

        for bm in event.bookmakers:
            outcomes = _get_market_outcomes(bm, market_key)
            if not outcomes:
                continue
            for outcome in outcomes:
                if not outcome.description:
                    continue
                pair_key = f"{outcome.description}|{outcome.point}"
                outcome_key = f"{outcome.description}|{outcome.name}|{outcome.point}"
                pairs.setdefault(pair_key, {}).setdefault(
                    outcome_key, []
                ).append((bm, outcome))

        # Process each (player, point) pair independently
        for _pair_key, pair_outcomes in pairs.items():
            if len(pair_outcomes) < 2:
                continue  # Need both Over and Under

            no_vig_probs, book_counts = _calculate_market_avg_no_vig(
                pair_outcomes, dfs_books,
            )

            min_books = min(book_counts.values()) if book_counts else 0
            if min_books < 3:
                continue

            _emit_ev_bets(
                event, market_key, pair_outcomes, no_vig_probs, book_counts,
                ev_bets, now, selected_books, ev_threshold, dfs_books,
                is_prop=True,
            )


def _emit_ev_bets(
    event: Event,
    market_key: str,
    book_outcomes: dict[str, list[tuple[Bookmaker, OutcomeOdds]]],
    no_vig_probs: dict[str, float],
    book_counts: dict[str, int],
    ev_bets: list[EVBet],
    now: datetime,
    selected_books: list[str] | None,
    ev_threshold: float,
    dfs_books: dict[str, float] | None,
    is_prop: bool = False,
) -> None:
    """Check each book's odds against the market consensus and emit EVBet."""
    for outcome_key, entries in book_outcomes.items():
        no_vig_prob = no_vig_probs.get(outcome_key)
        if no_vig_prob is None or no_vig_prob <= 0 or no_vig_prob >= 1:
            continue

        fair_american = prob_to_american(no_vig_prob)
        n_books = book_counts.get(outcome_key, 0)

        for bm, outcome in entries:
            if selected_books and bm.key not in selected_books:
                continue

            price = _effective_price(outcome, bm, dfs_books)
            decimal_odds = american_to_decimal(price)
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
                        odds=price,
                        decimal_odds=decimal_odds,
                        implied_prob=american_to_implied_prob(price),
                        no_vig_prob=no_vig_prob,
                        fair_odds=fair_american,
                        ev_percentage=ev_pct,
                        edge=no_vig_prob * decimal_odds - 1,
                        detected_at=now,
                        num_books=n_books,
                        player_name=outcome.description if is_prop else None,
                        is_prop=is_prop,
                    )
                )


def _calculate_market_avg_no_vig(
    book_outcomes: dict[str, list[tuple[Bookmaker, OutcomeOdds]]],
    dfs_books: dict[str, float] | None = None,
) -> tuple[dict[str, float], dict[str, int]]:
    """Calculate no-vig probabilities from market average across all books.

    Outcomes passed in should be a related group (e.g. Over + Under at the
    same line) so normalization produces correct probabilities.

    Returns (no_vig_probs, book_counts).
    """
    no_vig: dict[str, float] = {}
    counts: dict[str, int] = {}

    avg_probs: dict[str, list[float]] = {}
    for outcome_key, entries in book_outcomes.items():
        for bm, outcome in entries:
            price = _effective_price(outcome, bm, dfs_books)
            avg_probs.setdefault(outcome_key, []).append(
                american_to_implied_prob(price)
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
