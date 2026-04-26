import sys
from pathlib import Path

# Add the backend directory to Python path so relative imports work
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))
