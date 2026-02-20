"""Entry point for the OddsCLI application."""

from __future__ import annotations


def main() -> None:
    from app.ui.app import OddsTickerApp

    app = OddsTickerApp()
    app.run()


if __name__ == "__main__":
    main()
