"""SST demo verification entry point.

Run ``python run_demo.py`` for the backend regression checks.  Use
``python -m uvicorn backend.app.main:app --reload`` to start the UI/API.
"""
from scripts.check_demo import main


if __name__ == "__main__":
    main()
