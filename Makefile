.PHONY: api test demo upstream-core upstream-v2 upstream-reference clean

api:
	uvicorn ambience.main:app --app-dir apps/api --reload --port 8000

test:
	pytest -q

demo:
	python -m ambience.cli demo --root .

upstream-core:
	python scripts/bootstrap_upstreams.py --group core

upstream-v2:
	python scripts/bootstrap_upstreams.py --group v2

upstream-reference:
	python scripts/bootstrap_upstreams.py --group reference

clean:
	rm -rf data/projects/* data/work/* data/public/*
	touch data/projects/.gitkeep data/work/.gitkeep data/public/.gitkeep
