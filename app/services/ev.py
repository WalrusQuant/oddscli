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


class ArbBet(BaseModel):
    """A detected two-leg arbitrage opportunity."""

    sport_key: str
    event_id: str
    home_team: str
    away_team: str
    market: str
    book_a: str
    book_a_title: str
    outcome_a: str
    odds_a: float
    point_a: float | None = None
    book_b: str
    book_b_title: str
    outcome_b: str
    odds_b: float
    point_b: float | None = None
    profit_pct: float  # guaranteed profit percentage
    implied_sum: float  # sum of implied probs (< 1.0 means arb)
    player_name: str | None = None
    is_prop: bool = False


class MiddleBet(BaseModel):
    """A detected cross-line middle opportunity."""

    sport_key: str
    event_id: str
    home_team: str
    away_team: str
    market: str
    book_a: str
    book_a_title: str
    line_a: float
    odds_a: float
    outcome_a: str
    book_b: str
    book_b_title: str
    line_b: float
    odds_b: float
    outcome_b: str
    middle_low: float
    middle_high: float
    window_size: float
    combined_cost: float  # sum of implied probs for both legs
    hit_prob: float = 0.0  # estimated probability of landing in the middle
    ev_percentage: float = 0.0  # expected value as a percentage of total stake
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
    odds_range: tuple[float, float] | None = None,
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
                odds_range,
            )
        else:
            _find_game_ev(
                event, ev_bets, now, selected_books, ev_threshold, dfs_books,
                odds_range,
            )

    ev_bets.sort(key=lambda b: b.ev_percentage, reverse=True)
    return ev_bets


def _discover_market_keys(event: Event) -> set[str]:
    """Discover all market keys available on an event."""
    keys: set[str] = set()
    for bm in event.bookmakers:
        for m in bm.markets:
            keys.add(m.key)
    return keys


def _find_game_ev(
    event: Event,
    ev_bets: list[EVBet],
    now: datetime,
    selected_books: list[str] | None,
    ev_threshold: float,
    dfs_books: dict[str, float] | None,
    odds_range: tuple[float, float] | None = None,
) -> None:
    """Find +EV bets for standard game markets (dynamic discovery for alt lines)."""
    for market_key in _discover_market_keys(event):
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
            odds_range=odds_range,
        )


def _find_prop_ev(
    event: Event,
    ev_bets: list[EVBet],
    now: datetime,
    selected_books: list[str] | None,
    ev_threshold: float,
    dfs_books: dict[str, float] | None,
    odds_range: tuple[float, float] | None = None,
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
                is_prop=True, odds_range=odds_range,
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
    odds_range: tuple[float, float] | None = None,
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

            # Skip bets outside the configured odds range
            if odds_range is not None:
                lo, hi = odds_range
                if price < lo or price > hi:
                    continue

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


# ── Arbitrage detection ──


def find_arb_bets(
    events: list[Event],
    min_profit_pct: float = 0.1,
    dfs_books: dict[str, float] | None = None,
) -> list[ArbBet]:
    """Find two-leg arbitrage opportunities across all events/markets.

    An arb exists when the sum of the best implied probabilities across
    opposing outcomes is < 1.0 (guaranteed profit regardless of outcome).
    """
    arbs: list[ArbBet] = []
    _featured = {"h2h", "spreads", "totals"}
    for event in events:
        for market_key in _discover_market_keys(event) & _featured:
            _find_market_arbs(event, market_key, arbs, min_profit_pct, dfs_books)
    arbs.sort(key=lambda a: a.profit_pct, reverse=True)
    return arbs


def _find_market_arbs(
    event: Event,
    market_key: str,
    arbs: list[ArbBet],
    min_profit_pct: float,
    dfs_books: dict[str, float] | None,
) -> None:
    """Find arbs in a single market of an event.

    Only pairs mutually exclusive outcomes at the SAME line:
    - h2h: Team A vs Team B (no point)
    - spreads: Team A -3.5 vs Team B +3.5 (same absolute line)
    - totals: Over 220.5 vs Under 220.5 (same total)
    Cross-line opportunities are middles, not arbs.
    """
    # Group outcomes by the line they belong to. For spreads/totals,
    # group by point so we only compare same-line sides.
    # For h2h, all outcomes share the same "line" (None).
    line_groups: dict[float | None, dict[str, list[tuple[Bookmaker, OutcomeOdds]]]] = {}

    for bm in event.bookmakers:
        outcomes = _get_market_outcomes(bm, market_key)
        if not outcomes:
            continue
        for outcome in outcomes:
            # For spreads, both sides have the same absolute spread
            # (e.g., -3.5 and +3.5). Group by |point| so they match.
            # For totals, Over and Under share the same point value.
            # For h2h, point is None.
            if market_key == "h2h" or "h2h" in market_key:
                line_key: float | None = None
            elif outcome.point is not None:
                line_key = abs(outcome.point)
            else:
                line_key = None

            side_key = f"{outcome.name}|{outcome.point}"
            line_groups.setdefault(line_key, {}).setdefault(side_key, []).append(
                (bm, outcome)
            )

    # For each line group, find arbs among its sides
    for _line, sides in line_groups.items():
        if len(sides) < 2:
            continue

        # Find best price per side
        best_per_side: dict[str, tuple[float, Bookmaker, OutcomeOdds]] = {}
        for side_key, entries in sides.items():
            for bm, outcome in entries:
                price = _effective_price(outcome, bm, dfs_books)
                if side_key not in best_per_side or price > best_per_side[side_key][0]:
                    best_per_side[side_key] = (price, bm, outcome)

        # Check all pairs within this line group
        side_keys = list(best_per_side.keys())
        for i in range(len(side_keys)):
            for j in range(i + 1, len(side_keys)):
                key_a, key_b = side_keys[i], side_keys[j]
                price_a, bm_a, out_a = best_per_side[key_a]
                price_b, bm_b, out_b = best_per_side[key_b]

                imp_a = american_to_implied_prob(price_a)
                imp_b = american_to_implied_prob(price_b)
                imp_sum = imp_a + imp_b

                if imp_sum < 1.0:
                    profit = (1.0 / imp_sum - 1.0) * 100
                    if profit >= min_profit_pct:
                        arbs.append(ArbBet(
                            sport_key=event.sport_key,
                            event_id=event.id,
                            home_team=event.home_team,
                            away_team=event.away_team,
                            market=market_key,
                            book_a=bm_a.key,
                            book_a_title=bm_a.title,
                            outcome_a=out_a.name,
                            odds_a=price_a,
                            point_a=out_a.point,
                            book_b=bm_b.key,
                            book_b_title=bm_b.title,
                            outcome_b=out_b.name,
                            odds_b=price_b,
                            point_b=out_b.point,
                            profit_pct=profit,
                            implied_sum=imp_sum,
                        ))


# ── Middles detection ──

# Per-point probability of landing on any specific integer/half-point
# in common sports. Derived from empirical scoring distributions.
# For a total of ~220 in NBA, each individual point has roughly a 3-4%
# chance. For NFL spreads around 40-50, each point is ~5-6%.
# These are conservative estimates — actual density peaks near the line.
_POINT_DENSITY: dict[str, float] = {
    "basketball_nba": 0.035,
    "basketball_ncaab": 0.04,
    "americanfootball_nfl": 0.045,
    "americanfootball_ncaaf": 0.045,
    "baseball_mlb": 0.08,
    "icehockey_nhl": 0.07,
}
_DEFAULT_POINT_DENSITY = 0.04


def _estimate_middle_hit_prob(
    window_size: float, sport_key: str, market_key: str,
) -> float:
    """Estimate probability of the result landing inside the middle window.

    Uses sport-specific point density (probability per integer point in the
    window). For half-point lines (e.g., 220.5 to 222.5), the integers
    inside are 221 and 222 — that's 2 landing spots, not 2.5.

    Returns a probability between 0 and 1.
    """
    density = _POINT_DENSITY.get(sport_key, _DEFAULT_POINT_DENSITY)

    # Count integer landing spots inside the window.
    # For totals: Over 220.5 / Under 222.5 → integers 221, 222 → 2 spots
    # For spreads: -3 / +4.5 → margin of victory 4 → 1 spot (exactly 4)
    # General: floor(window) spots if both endpoints are half-points,
    # otherwise floor(window) spots. This is approximate.
    import math
    landing_spots = max(1, math.floor(window_size))

    # Cap at a reasonable probability (a 10-point window isn't 35%)
    hit_prob = min(landing_spots * density, 0.30)
    return hit_prob


def _compute_middle_ev(
    odds_a: float, odds_b: float, hit_prob: float,
) -> float:
    """Compute EV% of a middle as a percentage of total stake (2 units).

    Scenarios:
    - Middle hits (prob = hit_prob): win both legs. Profit = dec_a + dec_b - 2
    - Middle misses (prob = 1 - hit_prob): win one, lose one.
      On a miss, the better-priced leg wins on average. Net ≈ max(dec) - 2.
      (Slightly pessimistic since we don't know which side misses, but the
      losing side always costs exactly 1 unit and the winning side pays dec-1.)
      The worst case miss is the cheaper leg winning: min(dec) - 2.
      We use the average of the two miss scenarios.
    """
    dec_a = american_to_decimal(odds_a)
    dec_b = american_to_decimal(odds_b)

    profit_if_hit = dec_a + dec_b - 2  # both win
    # Miss scenario: either side A wins (profit dec_a - 2) or side B wins (profit dec_b - 2)
    # We don't know the split, so average them
    profit_if_miss = ((dec_a - 2) + (dec_b - 2)) / 2

    ev = hit_prob * profit_if_hit + (1 - hit_prob) * profit_if_miss
    # Express as % of total stake (2 units)
    return (ev / 2) * 100


def find_middle_bets(
    events: list[Event],
    min_window: float = 0.5,
    max_combined_cost: float = 1.08,
    dfs_books: dict[str, float] | None = None,
) -> list[MiddleBet]:
    """Find cross-line middle opportunities.

    Middles occur when different books offer different lines on the same
    outcome, creating a "window" where both bets can win.

    For spreads: Team A -3 at Book1, Opponent +4 at Book2 → middle at 3-4
    For totals: Over 220.5 at Book1, Under 222.5 at Book2 → middle at 220.5-222.5
    """
    middles: list[MiddleBet] = []
    for event in events:
        for market_key in _discover_market_keys(event) & {"spreads", "totals"}:
            _find_market_middles(
                event, market_key, middles, min_window, max_combined_cost, dfs_books,
            )
    middles.sort(key=lambda m: m.ev_percentage, reverse=True)
    return middles


def _find_market_middles(
    event: Event,
    market_key: str,
    middles: list[MiddleBet],
    min_window: float,
    max_combined_cost: float,
    dfs_books: dict[str, float] | None,
) -> None:
    """Find middles in a single market."""
    if "spread" in market_key:
        _find_spread_middles(event, market_key, middles, min_window, max_combined_cost, dfs_books)
    elif "total" in market_key:
        _find_total_middles(event, market_key, middles, min_window, max_combined_cost, dfs_books)


def _find_spread_middles(
    event: Event,
    market_key: str,
    middles: list[MiddleBet],
    min_window: float,
    max_combined_cost: float,
    dfs_books: dict[str, float] | None,
) -> None:
    """Find spread middles: same team at different lines across books."""
    # Collect (team_name → [(point, price, bm)]) ignoring point grouping
    team_lines: dict[str, list[tuple[float, float, Bookmaker]]] = {}
    for bm in event.bookmakers:
        outcomes = _get_market_outcomes(bm, market_key)
        if not outcomes:
            continue
        for out in outcomes:
            if out.point is None:
                continue
            price = _effective_price(out, bm, dfs_books)
            team_lines.setdefault(out.name, []).append((out.point, price, bm))

    # For each pair of teams (A, B), check if A's spread + B's spread create a window
    teams = list(team_lines.keys())
    for i in range(len(teams)):
        for j in range(i + 1, len(teams)):
            team_a, team_b = teams[i], teams[j]
            for pt_a, price_a, bm_a in team_lines[team_a]:
                for pt_b, price_b, bm_b in team_lines[team_b]:
                    if bm_a.key == bm_b.key:
                        continue
                    # Middle exists if pt_a + pt_b > 0
                    # e.g., Team A -3, Team B +4 → window = |(-3) + 4| = 1
                    window = pt_a + pt_b
                    if window >= min_window:
                        imp_a = american_to_implied_prob(price_a)
                        imp_b = american_to_implied_prob(price_b)
                        cost = imp_a + imp_b
                        if cost <= max_combined_cost:
                            low = min(-pt_a, pt_b)
                            high = max(-pt_a, pt_b)
                            hp = _estimate_middle_hit_prob(
                                window, event.sport_key, market_key,
                            )
                            ev_pct = _compute_middle_ev(price_a, price_b, hp)
                            middles.append(MiddleBet(
                                sport_key=event.sport_key,
                                event_id=event.id,
                                home_team=event.home_team,
                                away_team=event.away_team,
                                market=market_key,
                                book_a=bm_a.key,
                                book_a_title=bm_a.title,
                                line_a=pt_a,
                                odds_a=price_a,
                                outcome_a=team_a,
                                book_b=bm_b.key,
                                book_b_title=bm_b.title,
                                line_b=pt_b,
                                odds_b=price_b,
                                outcome_b=team_b,
                                middle_low=low,
                                middle_high=high,
                                window_size=window,
                                combined_cost=cost,
                                hit_prob=hp,
                                ev_percentage=ev_pct,
                            ))


def _find_total_middles(
    event: Event,
    market_key: str,
    middles: list[MiddleBet],
    min_window: float,
    max_combined_cost: float,
    dfs_books: dict[str, float] | None,
) -> None:
    """Find total middles: Over X at one book, Under Y at another where Y > X."""
    overs: list[tuple[float, float, Bookmaker]] = []
    unders: list[tuple[float, float, Bookmaker]] = []

    for bm in event.bookmakers:
        outcomes = _get_market_outcomes(bm, market_key)
        if not outcomes:
            continue
        for out in outcomes:
            if out.point is None:
                continue
            price = _effective_price(out, bm, dfs_books)
            if out.name == "Over":
                overs.append((out.point, price, bm))
            elif out.name == "Under":
                unders.append((out.point, price, bm))

    for ov_pt, ov_price, ov_bm in overs:
        for un_pt, un_price, un_bm in unders:
            if ov_bm.key == un_bm.key:
                continue
            window = un_pt - ov_pt
            if window >= min_window:
                imp_ov = american_to_implied_prob(ov_price)
                imp_un = american_to_implied_prob(un_price)
                cost = imp_ov + imp_un
                if cost <= max_combined_cost:
                    hp = _estimate_middle_hit_prob(
                        window, event.sport_key, market_key,
                    )
                    ev_pct = _compute_middle_ev(ov_price, un_price, hp)
                    middles.append(MiddleBet(
                        sport_key=event.sport_key,
                        event_id=event.id,
                        home_team=event.home_team,
                        away_team=event.away_team,
                        market=market_key,
                        book_a=ov_bm.key,
                        book_a_title=ov_bm.title,
                        line_a=ov_pt,
                        odds_a=ov_price,
                        outcome_a="Over",
                        book_b=un_bm.key,
                        book_b_title=un_bm.title,
                        line_b=un_pt,
                        odds_b=un_price,
                        outcome_b="Under",
                        middle_low=ov_pt,
                        middle_high=un_pt,
                        window_size=window,
                        combined_cost=cost,
                        hit_prob=hp,
                        ev_percentage=ev_pct,
                    ))


# ── Prop Arbitrage detection ──


def find_prop_arb_bets(
    events: list[Event],
    min_profit_pct: float = 0.1,
    dfs_books: dict[str, float] | None = None,
) -> list[ArbBet]:
    """Find two-leg arb opportunities on player props.

    Groups outcomes by (player, market, point) and checks if the best
    Over + best Under implied probs sum to < 1.0 at the same line.
    """
    arbs: list[ArbBet] = []
    for event in events:
        for market_key in _discover_market_keys(event):
            _find_prop_market_arbs(
                event, market_key, arbs, min_profit_pct, dfs_books,
            )
    arbs.sort(key=lambda a: a.profit_pct, reverse=True)
    return arbs


def _find_prop_market_arbs(
    event: Event,
    market_key: str,
    arbs: list[ArbBet],
    min_profit_pct: float,
    dfs_books: dict[str, float] | None,
) -> None:
    """Find arbs in a single prop market — same player, same line."""
    # Group by (player, point) → side → best price
    groups: dict[str, dict[str, list[tuple[float, Bookmaker, OutcomeOdds]]]] = {}

    for bm in event.bookmakers:
        outcomes = _get_market_outcomes(bm, market_key)
        if not outcomes:
            continue
        for out in outcomes:
            if not out.description or out.point is None:
                continue
            group_key = f"{out.description}|{out.point}"
            price = _effective_price(out, bm, dfs_books)
            groups.setdefault(group_key, {}).setdefault(out.name, []).append(
                (price, bm, out)
            )

    for group_key, sides in groups.items():
        if len(sides) < 2:
            continue

        # Find best price per side
        best_per_side: dict[str, tuple[float, Bookmaker, OutcomeOdds]] = {}
        for side_name, entries in sides.items():
            for price, bm, out in entries:
                if side_name not in best_per_side or price > best_per_side[side_name][0]:
                    best_per_side[side_name] = (price, bm, out)

        # Check all pairs
        side_names = list(best_per_side.keys())
        for i in range(len(side_names)):
            for j in range(i + 1, len(side_names)):
                name_a, name_b = side_names[i], side_names[j]
                price_a, bm_a, out_a = best_per_side[name_a]
                price_b, bm_b, out_b = best_per_side[name_b]

                imp_a = american_to_implied_prob(price_a)
                imp_b = american_to_implied_prob(price_b)
                imp_sum = imp_a + imp_b

                if imp_sum < 1.0:
                    profit = (1.0 / imp_sum - 1.0) * 100
                    if profit >= min_profit_pct:
                        arbs.append(ArbBet(
                            sport_key=event.sport_key,
                            event_id=event.id,
                            home_team=event.home_team,
                            away_team=event.away_team,
                            market=market_key,
                            book_a=bm_a.key,
                            book_a_title=bm_a.title,
                            outcome_a=out_a.name,
                            odds_a=price_a,
                            point_a=out_a.point,
                            book_b=bm_b.key,
                            book_b_title=bm_b.title,
                            outcome_b=out_b.name,
                            odds_b=price_b,
                            point_b=out_b.point,
                            profit_pct=profit,
                            implied_sum=imp_sum,
                            player_name=out_a.description,
                            is_prop=True,
                        ))


# ── Prop Middles detection ──


def find_prop_middle_bets(
    events: list[Event],
    min_window: float = 0.5,
    max_combined_cost: float = 1.08,
    dfs_books: dict[str, float] | None = None,
) -> list[MiddleBet]:
    """Find cross-line middle opportunities on player props.

    Groups by (player, market) across all lines, then looks for
    Over at line X (Book A) vs Under at line Y (Book B) where Y > X.
    """
    middles: list[MiddleBet] = []
    for event in events:
        for market_key in _discover_market_keys(event):
            _find_prop_market_middles(
                event, market_key, middles, min_window, max_combined_cost, dfs_books,
            )
    middles.sort(key=lambda m: m.ev_percentage, reverse=True)
    return middles


def _find_prop_market_middles(
    event: Event,
    market_key: str,
    middles: list[MiddleBet],
    min_window: float,
    max_combined_cost: float,
    dfs_books: dict[str, float] | None,
) -> None:
    """Find middles in a single prop market for each player."""
    # Group by player → collect Overs and Unders with their lines
    player_overs: dict[str, list[tuple[float, float, Bookmaker]]] = {}
    player_unders: dict[str, list[tuple[float, float, Bookmaker]]] = {}

    for bm in event.bookmakers:
        outcomes = _get_market_outcomes(bm, market_key)
        if not outcomes:
            continue
        for out in outcomes:
            if not out.description or out.point is None:
                continue
            price = _effective_price(out, bm, dfs_books)
            if out.name == "Over":
                player_overs.setdefault(out.description, []).append(
                    (out.point, price, bm)
                )
            elif out.name == "Under":
                player_unders.setdefault(out.description, []).append(
                    (out.point, price, bm)
                )

    # For each player, find Over X / Under Y cross-line opportunities
    for player in player_overs:
        if player not in player_unders:
            continue
        overs = player_overs[player]
        unders = player_unders[player]

        for ov_pt, ov_price, ov_bm in overs:
            for un_pt, un_price, un_bm in unders:
                if ov_bm.key == un_bm.key:
                    continue
                window = un_pt - ov_pt
                if window >= min_window:
                    imp_ov = american_to_implied_prob(ov_price)
                    imp_un = american_to_implied_prob(un_price)
                    cost = imp_ov + imp_un
                    if cost <= max_combined_cost:
                        hp = _estimate_middle_hit_prob(
                            window, event.sport_key, market_key,
                        )
                        ev_pct = _compute_middle_ev(ov_price, un_price, hp)
                        middles.append(MiddleBet(
                            sport_key=event.sport_key,
                            event_id=event.id,
                            home_team=event.home_team,
                            away_team=event.away_team,
                            market=market_key,
                            book_a=ov_bm.key,
                            book_a_title=ov_bm.title,
                            line_a=ov_pt,
                            odds_a=ov_price,
                            outcome_a="Over",
                            book_b=un_bm.key,
                            book_b_title=un_bm.title,
                            line_b=un_pt,
                            odds_b=un_price,
                            outcome_b="Under",
                            middle_low=ov_pt,
                            middle_high=un_pt,
                            window_size=window,
                            combined_cost=cost,
                            hit_prob=hp,
                            ev_percentage=ev_pct,
                            player_name=player,
                            is_prop=True,
                        ))
