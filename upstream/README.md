# Local upstream checkouts

This directory is intentionally Git-ignored except for this README in source archives. Upstream projects are not redistributed here.

Clone pinned revisions with:

```bash
python scripts/bootstrap_upstreams.py --group core
python scripts/bootstrap_upstreams.py --group v2
python scripts/bootstrap_upstreams.py --group reference
```

The lock file records the revision and integration strategy. Review each upstream's code/model licenses before production use.
