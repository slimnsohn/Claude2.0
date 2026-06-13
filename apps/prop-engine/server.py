"""Flask dev server entrypoint — mirrors the synthetic-population pattern."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.dashboard.app import create_app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5000)
