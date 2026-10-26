import sys
from pathlib import Path

# Os módulos do projeto ficam na raiz (app.py, revisao.py, avaliar.py...)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
