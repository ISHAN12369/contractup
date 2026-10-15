"""Authenticated ingestion/read lifecycle. Only synthetic text is uploaded."""
import json
import os
import time
from pathlib import Path

from gevent import sleep
from locust import HttpUser, between, events, task
from locust.exception import StopUser

TEXT = b"1. Rent\nThe tenant pays monthly rent of INR 24000 on the fifth day of each month.\n2. Exit\nEither party gives 45 days of written notice."


@events.quitting.add_listener
def save_final_stats(environment, **kwargs):
    target = os.getenv("LOAD_SUMMARY_PATH")
    if target:
        entries = [*environment.stats.entries.values(), environment.stats.total]
        result = [{"method": item.method, "name": item.name, "requests": item.num_requests,
                   "failures": item.num_failures, "mean_ms": item.avg_response_time,
                   "p95_ms": item.get_response_time_percentile(0.95)} for item in entries]
        Path(target).write_text(json.dumps({"synthetic": True, "provider_calls": os.getenv("LOAD_PROVIDER_CALLS") == "1",
                                          "results": result}, indent=2) + "\n", encoding="utf-8")


class ContractUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        self.doc_id = None
        token = os.getenv("LOAD_ACCESS_TOKEN", "")
        fixture = os.getenv("E2E_AUTH_FILE")
        if fixture:
            token = json.loads(Path(fixture).read_text(encoding="utf-8"))["alice"]["access_token"]
        if not token:
            raise RuntimeError("Set LOAD_ACCESS_TOKEN or a local E2E_AUTH_FILE before running")
        self.client.headers["Authorization"] = "Bearer " + token
        with self.client.post("/upload", files={"file": ("synthetic-lease.txt", TEXT, "text/plain")}, timeout=20, catch_response=True) as response:
            if response.status_code != 202:
                response.failure("Upload did not return a queue ticket")
                raise StopUser()
            self.doc_id = response.json()["doc_id"]
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            with self.client.get(f"/ingestion/{self.doc_id}", name="/ingestion/:id", timeout=10, catch_response=True) as response:
                if response.status_code != 200:
                    response.failure("Ingestion status unavailable")
                    raise StopUser()
                state = response.json()["status"]
                if state == "ready":
                    return
                if state == "failed":
                    response.failure("Ingestion failed")
                    raise StopUser()
            sleep(1)
        raise StopUser()

    @task(3)
    def metadata(self):
        self.client.get(f"/document/{self.doc_id}", name="/document/:id", timeout=10)

    @task
    def source(self):
        self.client.get(f"/document/{self.doc_id}/source", name="/document/:id/source", timeout=10)

    @task
    def retrieval(self):
        # Explicit opt-in: real deployments may incur provider charges.
        if os.getenv("LOAD_PROVIDER_CALLS") == "1":
            self.client.post("/chat", json={"doc_id": self.doc_id, "question": "What is the monthly rent?"}, timeout=60)
        else:
            self.metadata()

    def on_stop(self):
        if self.doc_id:
            self.client.delete(f"/document/{self.doc_id}", name="/document/:id", timeout=10)
