"""Entry point: `python -m odds_pipeline`. CLI itself is implemented in Task 7."""
import sys

try:
    from odds_pipeline.cli import main
except ImportError:
    sys.exit("CLI not yet implemented (see Task 7 of the implementation plan).")

if __name__ == "__main__":
    main()
