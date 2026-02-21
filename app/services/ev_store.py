"""SQLite persistence for EV bet history."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from app.services.ev import EVBet

DB_PATH = Path(__file__).resolve().parent.parent.parent / "ev_history.db"


class EVStore:
    """Stores and queries EV bet history in SQLite."""

    def __init__(self, db_path: Path = DB_PATH) -> None:
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS ev_bets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sport_key TEXT NOT NULL,
                book TEXT NOT NULL,
                book_title TEXT NOT NULL,
                event_id TEXT NOT NULL,
                home_team TEXT NOT NULL,
                away_team TEXT NOT NULL,
                market TEXT NOT NULL,
                outcome_name TEXT NOT NULL,
                outcome_point_str TEXT NOT NULL DEFAULT '',
                odds REAL NOT NULL,
                fair_odds REAL NOT NULL,
                no_vig_prob REAL NOT NULL,
                ev_percentage REAL NOT NULL,
                edge REAL NOT NULL,
                num_books INTEGER NOT NULL DEFAULT 0,
                detected_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                player_name TEXT NOT NULL DEFAULT '',
                is_prop INTEGER NOT NULL DEFAULT 0,
                UNIQUE(book, event_id, market, outcome_name, outcome_point_str, player_name)
            )
        """)
        self._conn.commit()

    def upsert_bets(self, bets: list[EVBet]) -> None:
        """Insert new bets or update existing ones."""
        now = datetime.now().isoformat()
        for bet in bets:
            pt_str = str(bet.outcome_point) if bet.outcome_point is not None else ""
            player = bet.player_name or ""
            self._conn.execute("""
                INSERT INTO ev_bets
                    (sport_key, book, book_title, event_id, home_team, away_team,
                     market, outcome_name, outcome_point_str, odds, fair_odds,
                     no_vig_prob, ev_percentage, edge, num_books,
                     detected_at, last_seen_at, is_active,
                     player_name, is_prop)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(book, event_id, market, outcome_name, outcome_point_str, player_name)
                DO UPDATE SET
                    odds = excluded.odds,
                    fair_odds = excluded.fair_odds,
                    no_vig_prob = excluded.no_vig_prob,
                    ev_percentage = excluded.ev_percentage,
                    edge = excluded.edge,
                    num_books = excluded.num_books,
                    last_seen_at = excluded.last_seen_at,
                    is_active = 1
            """, (
                bet.sport_key, bet.book, bet.book_title, bet.event_id,
                bet.home_team, bet.away_team, bet.market,
                bet.outcome_name, pt_str,
                bet.odds, bet.fair_odds, bet.no_vig_prob,
                bet.ev_percentage, bet.edge, bet.num_books,
                bet.detected_at.isoformat() if bet.detected_at else now,
                now,
                player, 1 if bet.is_prop else 0,
            ))
        self._conn.commit()

    def mark_stale_for_sport(self, sport_key: str, active_event_ids: set[str]) -> None:
        """Mark bets inactive if their event is gone from the current feed."""
        if not active_event_ids:
            self._conn.execute(
                "UPDATE ev_bets SET is_active = 0 WHERE sport_key = ? AND is_active = 1",
                (sport_key,),
            )
        else:
            placeholders = ",".join("?" * len(active_event_ids))
            self._conn.execute(f"""
                UPDATE ev_bets SET is_active = 0
                WHERE sport_key = ? AND is_active = 1
                AND event_id NOT IN ({placeholders})
            """, [sport_key] + list(active_event_ids))
        self._conn.commit()

    def deactivate_missing(
        self, sport_key: str, current_bets: list[EVBet], *, is_props: bool = False,
    ) -> None:
        """Deactivate bets that were previously active but aren't in the current scan.

        Scopes by is_prop so game and prop deactivations don't interfere.
        """
        prop_val = 1 if is_props else 0

        if not current_bets:
            self._conn.execute(
                "UPDATE ev_bets SET is_active = 0 "
                "WHERE sport_key = ? AND is_active = 1 AND is_prop = ?",
                (sport_key, prop_val),
            )
            self._conn.commit()
            return

        # Build set of current bet keys
        current_keys = set()
        for b in current_bets:
            pt = str(b.outcome_point) if b.outcome_point is not None else ""
            player = b.player_name or ""
            current_keys.add((b.book, b.event_id, b.market, b.outcome_name, pt, player))

        # Get all active bets for this sport scoped by prop type
        rows = self._conn.execute(
            "SELECT id, book, event_id, market, outcome_name, outcome_point_str, player_name "
            "FROM ev_bets WHERE sport_key = ? AND is_active = 1 AND is_prop = ?",
            (sport_key, prop_val),
        ).fetchall()

        stale_ids = []
        for r in rows:
            key = (
                r["book"], r["event_id"], r["market"],
                r["outcome_name"], r["outcome_point_str"], r["player_name"],
            )
            if key not in current_keys:
                stale_ids.append(r["id"])

        if stale_ids:
            placeholders = ",".join("?" * len(stale_ids))
            self._conn.execute(
                f"UPDATE ev_bets SET is_active = 0 WHERE id IN ({placeholders})",
                stale_ids,
            )
            self._conn.commit()

    def get_active_for_sport(
        self, sport_key: str, limit: int = 40, *, is_props: bool = False,
    ) -> list[dict]:
        """Get currently active EV bets for a specific sport."""
        prop_val = 1 if is_props else 0
        rows = self._conn.execute("""
            SELECT *,
                ROUND((julianday('now', 'localtime') - julianday(detected_at)) * 24 * 60, 1)
                    AS minutes_active
            FROM ev_bets
            WHERE is_active = 1 AND sport_key = ? AND is_prop = ?
            ORDER BY ev_percentage DESC
            LIMIT ?
        """, (sport_key, prop_val, limit)).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self._conn.close()
