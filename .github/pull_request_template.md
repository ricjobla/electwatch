## Summary

<!-- What changed and why (one short paragraph). -->

## Checklist

- [ ] Lint and tests pass locally (`frontend`: `npm run lint` / `npm run build`; `backend`: `pytest -m "not live"`).
- [ ] Database changes include an Alembic migration when the schema changes.
- [ ] UI changes: briefly note what to click or compare (screenshots optional).
- [ ] Large static assets (e.g. GeoJSON, shapefiles): prefer a smaller topology, fetch at build time, or [Git LFS](https://git-lfs.com/)—avoid committing multi‑MB blobs to `main` without team agreement.
