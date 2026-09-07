.PHONY: help install test lint data train clean verify checkpoints checkpoints-verbose

help:
	@echo "BioForm-LM: Generative Biologics Formulation Design"
	@echo "===================================================="
	@echo ""
	@echo "Available commands:"
	@echo "  make install   - Install dependencies from requirements.txt"
	@echo "  make test      - Run all unit tests (pytest)"
	@echo "  make lint      - Check code style (black, isort, flake8, mypy)"
	@echo "  make format    - Auto-format code (black, isort)"
	@echo "  make data      - Generate 1K synthetic samples for quick testing"
	@echo "  make data-large - Generate 100K synthetic samples for training"
	@echo "  make train     - Train BioFormLM on 1K samples (smoke test)"
	@echo "  make train-full - Train BioFormLM on 100K samples"
	@echo "  make checkpoints - List available model checkpoints"
	@echo "  make checkpoints-verbose - List checkpoints with epoch/loss details"
	@echo "  make verify    - Run verification pipeline (tests + data + train)"
	@echo "  make clean     - Remove generated artifacts and cache"
	@echo ""

install:
	pip install -r requirements.txt
	@echo "✓ Dependencies installed"

test:
	pytest tests/test_simulator.py -v --tb=short
	@echo "✓ Tests passed"

lint:
	black --check bioform-lm config.py simulator/ data/ model/ experiments/ tests/
	isort --check-only bioform-lm config.py simulator/ data/ model/ experiments/ tests/
	flake8 bioform-lm config.py simulator/ data/ model/ experiments/ tests/ --max-line-length=100 --ignore=E203,W503
	mypy bioform-lm config.py simulator/ data/ model/ experiments/ tests/ --ignore-missing-imports
	@echo "✓ Lint checks passed"

format:
	black bioform-lm config.py simulator/ data/ model/ experiments/ tests/
	isort bioform-lm config.py simulator/ data/ model/ experiments/ tests/
	@echo "✓ Code formatted"

data:
	python scripts/generate_data.py 1000
	@echo "✓ 1K synthetic samples generated"

data-large:
	python scripts/generate_data.py 100000
	@echo "✓ 100K synthetic samples generated"

train:
	python scripts/train.py --phase synthetic --num_samples 1000 --device cuda
	@echo "✓ Training on 1K samples completed"

train-full:
	python scripts/train.py --phase synthetic --num_samples 100000 --device cuda
	@echo "✓ Full training on 100K samples completed"

evaluate:
	@echo "⚠ Evaluation module not yet implemented"
	@echo "This target will be available once evaluation/ package is built"

checkpoints:
	python scripts/list_checkpoints.py
	@echo ""

checkpoints-verbose:
	python scripts/list_checkpoints.py --verbose
	@echo ""

verify: test data train
	@echo "✓ Verification pipeline passed"

clean:
	rm -rf __pycache__ .pytest_cache .mypy_cache .coverage htmlcov
	rm -rf simulator/__pycache__ data/__pycache__ model/__pycache__ experiments/__pycache__ tests/__pycache__
	rm -rf data/*.csv data/*.parquet
	rm -rf experiments/checkpoints experiments/train.log
	rm -f config_snapshot.json
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@echo "✓ Artifacts cleaned"
