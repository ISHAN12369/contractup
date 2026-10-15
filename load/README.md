# Bounded production-path load test

Install `requirements.txt` into a separate Python 3.12 virtual environment; Locust's dependencies are tooling, not API runtime dependencies. Run only against your own test deployment with synthetic data. Set `LOAD_ACCESS_TOKEN` to a fresh Supabase access token without committing it. The script uploads one small synthetic document per user, polls ingestion, reads metadata/source, and deletes its document on graceful stop. Provider calls are disabled unless `LOAD_PROVIDER_CALLS=1`.

```sh
python -m venv .venv-load
# Activate .venv-load (Windows: .venv-load\Scripts\Activate.ps1)
python -m pip install -r load/requirements.txt
python -m locust -f load/locustfile.py --headless --host http://localhost:8000 --users 2 --spawn-rate 1 --run-time 30s --stop-timeout 10 --csv load/results/smoke
```

Create `load/results` first. Set `LOAD_SUMMARY_PATH=load/results/final-summary.json` to retain a final JSON snapshot including graceful cleanup requests (the periodic Locust CSV can stop before cleanup). For an entirely local smoke run, start Compose's postgres/redis/s3 services and `python e2e/server.py`, set `E2E_AUTH_FILE=test-results/e2e-auth.json`, and use host `http://127.0.0.1:8013`. That server uses synthetic JWTs, vectors and AI, so its latency is **not** production inference latency. Reports and temporary tokens are ignored by Git. A single token shares one user's quota and rate budget across all simulated clients. Larger tests need a pool of real test accounts, isolated infrastructure, and explicit capacity targets. Rate-limit 429s count as failures; do not silently hide them. Forced termination may leave uploads until TTL cleanup.
