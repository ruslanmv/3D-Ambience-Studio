"""Space entry point: `uvicorn app:app`.

A Docker Space is conventionally started from a root-level `app.py`, and the Hugging Face
scaffold that creates one says so, so that is what this file is — four lines that re-export the
real application. Nothing lives here: every route, mount and middleware is defined in
`ambience.main`, and a second definition of the app would be a second thing to keep in step.

The import works because the image sets PYTHONPATH to the directory holding the `ambience`
package; see deploy/huggingface/Dockerfile.
"""

from ambience.main import app

__all__ = ["app"]
