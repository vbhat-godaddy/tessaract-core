#ARTIFACT_NAME = $(shell basename "$$PWD")
ARTIFACT_NAME=tesseract
ARTIFACT_VERSION=0.1.0

.PHONY: build
build:
	mkdir build
	poetry build -f wheel
	poetry export --without-hashes --format requirements.txt > requirements.txt
	poetry run pip install -I --target build -r requirements.txt
	poetry run pip install -I --target build --no-deps dist/${ARTIFACT_NAME}-${ARTIFACT_VERSION}-py3-none-any.whl
	ls dist/
	cd build && zip ../dist/${ARTIFACT_NAME}-${ARTIFACT_VERSION}.zip . -r9 -x "*.pyc"
	cd src && zip -g ../dist/${ARTIFACT_NAME}-${ARTIFACT_VERSION}.zip index.py

.PHONY: clean
clean:
	rm -f .coverage
	rm -f coverage.xml
	rm -f report.xml
	rm -f requirements.txt
	rm -rf .eggs
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf build
	rm -rf dist

