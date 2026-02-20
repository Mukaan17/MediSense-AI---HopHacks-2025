#!/bin/bash
# Activation script for the deep learning RAG environment

echo "Activating Deep Learning RAG Environment..."
source venv/bin/activate

# Load .env if present
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
  echo "Loaded environment variables from .env"
fi

echo "Environment activated! You can now:"
echo "- Run Python scripts with: python your_script.py"
echo "- Start Jupyter: jupyter notebook"
echo "- Start JupyterLab: jupyter lab"
echo "- Run tests: pytest"
echo "- Format code: black ."
echo "- Check code: flake8 ."
echo ""
echo "To deactivate, simply run: deactivate"

