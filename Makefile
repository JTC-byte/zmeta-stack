PYTHON ?= python

ifeq ($(OS),Windows_NT)
  VENV_PY := .venv/Scripts/python.exe
else
  VENV_PY := .venv/bin/python
endif

ifneq ($(wildcard $(VENV_PY)),)
  PYTHON := $(VENV_PY)
endif

ARGS ?=

.PHONY: health
health:
	$(PYTHON) scripts/run_health_check.py $(ARGS)
