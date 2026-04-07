"""Project entry point."""

from core.app import ProjectApp


def main() -> int:
    """Run the minimal project skeleton."""

    app = ProjectApp()
    print(app.run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
