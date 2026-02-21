"""Shared constants for UI widgets."""

BOOK_SHORT: dict[str, str] = {
    "fanduel": "FanDuel", "draftkings": "DraftK", "betmgm": "BetMGM",
    "betrivers": "BetRiv", "betonlineag": "BetOnl", "betus": "BetUS",
    "bovada": "Bovada", "williamhill_us": "Caesars", "fanatics": "Fanatic",
    "lowvig": "LowVig", "mybookieag": "MyBook", "ballybet": "Bally",
    "betanysports": "BetAny", "betparx": "BetPrx", "espnbet": "TheScr",
    "fliff": "Fliff", "hardrockbet": "HrdRck", "rebet": "Rebet",
    "betopenly": "BetOpn", "kalshi": "Kalshi", "novig": "Novig",
    "polymarket": "PolyMk", "prophetx": "PrphX",
    # DFS sites
    "betr_us_dfs": "Betr", "pick6": "Pick6",
    "prizepicks": "PrizeP", "underdog": "UDog",
}

PROP_LABELS: dict[str, str] = {
    # NBA
    "player_points": "PTS",
    "player_rebounds": "REB",
    "player_assists": "AST",
    "player_threes": "3PT",
    "player_points_rebounds_assists": "PRA",
    # NFL
    "player_pass_yds": "PaYd",
    "player_pass_tds": "PaTD",
    "player_rush_yds": "RuYd",
    "player_reception_yds": "ReYd",
    "player_receptions": "Rec",
    "player_anytime_td": "ATD",
    # MLB
    "batter_home_runs": "HR",
    "batter_hits": "Hits",
    "batter_total_bases": "TB",
    "pitcher_strikeouts": "K",
    # NHL
    "player_goals": "Goal",
    "player_shots_on_goal": "SOG",
}

MAX_DISPLAY_BOOKS = 20


def trunc(s: str, n: int) -> str:
    """Truncate string to n chars, adding ~ indicator when truncated."""
    if len(s) <= n:
        return s.ljust(n)
    return s[: n - 1] + "~"
