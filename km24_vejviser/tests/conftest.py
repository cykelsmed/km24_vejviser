from pathlib import Path
import sys

# Ensure project root is on sys.path so `import km24_vejviser` works
PROJECT_ROOT = Path(__file__).resolve().parents[2]
project_root_str = str(PROJECT_ROOT)
if project_root_str not in sys.path:
    sys.path.insert(0, project_root_str)
