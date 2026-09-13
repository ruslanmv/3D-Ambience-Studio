.PHONY: api test demo space-tree space-run upstream-core upstream-v2 upstream-reference clean

api:
	uvicorn ambience.main:app --app-dir apps/api --reload --port 8000

test:
	pytest -q

demo:
	python -m ambience.cli demo --root .

# The tree the Hugging Face Space is built from — the same one the sync workflow pushes, so
# `docker build` against it tests what the Space will actually build.
space-tree:
	rm -rf build/space
	bash deploy/huggingface/build-tree.sh build/space

# The Space's single-process arrangement, without Docker: one port, FastAPI serving the wizard.
space-run:
	cd apps/web && VITE_API_BASE_URL="" npm run build
	PYTHONPATH=apps/api AMBIENCE_WEB_DIST="$(PWD)/apps/web/dist" \
		python -m uvicorn app:app --app-dir deploy/huggingface --port 7860

upstream-core:
	python scripts/bootstrap_upstreams.py --group core

upstream-v2:
	python scripts/bootstrap_upstreams.py --group v2

upstream-reference:
	python scripts/bootstrap_upstreams.py --group reference

clean:
	rm -rf data/projects/* data/work/* data/public/*
	touch data/projects/.gitkeep data/work/.gitkeep data/public/.gitkeep
