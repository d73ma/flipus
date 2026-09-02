"""
FLIPUS v1.2 — Load test ringan.

Run: storage/scripts/load_test.py

Simple async load test:
- 100 concurrent requests
- Mix of endpoints (login, master, agregat)
- Report p50, p95, p99 response times

Requires: httpx[asyncio]
"""

import asyncio
import time
import statistics
import sys
import httpx


BASE_URL = "http://localhost:8000/api/v1"
CONCURRENT = 20
TOTAL_REQUESTS = 100


async def login(client: httpx.AsyncClient) -> str:
    """Get JWT (sequential first)."""
    r = await client.post(f"{BASE_URL}/auth/login", json={
        "username": "bendahara",
        "password": "Bendahara123!",
    })
    r.raise_for_status()
    return r.json()["access_token"]


async def make_request(client: httpx.AsyncClient, headers: dict, path: str) -> float:
    """Single GET request, return latency in ms."""
    start = time.perf_counter()
    try:
        r = await client.get(f"{BASE_URL}{path}", headers=headers, timeout=30)
        r.raise_for_status()
    except Exception as e:
        return -1.0  # error
    return (time.perf_counter() - start) * 1000


async def worker(client: httpx.AsyncClient, headers: dict, results: list):
    """Worker: do N requests."""
    endpoints = [
        "/master/uni",
        "/master/misi",
        "/agregat/tenant",
        "/dashboard/sabat-info",
    ]
    for i in range(TOTAL_REQUESTS // CONCURRENT):
        path = endpoints[i % len(endpoints)]
        latency = await make_request(client, headers, path)
        results.append((path, latency))


async def main():
    print(f"=== FLIPUS v1.2 — Load Test ===")
    print(f"Target: {BASE_URL}")
    print(f"Concurrent: {CONCURRENT}")
    print(f"Total requests: {TOTAL_REQUESTS}\n")

    async with httpx.AsyncClient() as client:
        # Sequential login
        try:
            token = await login(client)
            print(f"✓ Login OK")
        except Exception as e:
            print(f"❌ Login gagal: {e}")
            sys.exit(1)

        headers = {"Authorization": f"Bearer {token}"}

        # Concurrent load
        results = []
        start = time.perf_counter()
        tasks = [
            worker(client, headers, results)
            for _ in range(CONCURRENT)
        ]
        await asyncio.gather(*tasks)
        elapsed = time.perf_counter() - start

        # Stats
        latencies = [r[1] for r in results if r[1] >= 0]
        errors = [r for r in results if r[1] < 0]

        if not latencies:
            print("❌ All requests failed!")
            return 1

        latencies.sort()
        p50 = latencies[len(latencies) // 2]
        p95 = latencies[int(len(latencies) * 0.95)]
        p99 = latencies[int(len(latencies) * 0.99)]
        avg = statistics.mean(latencies)
        rps = len(latencies) / elapsed

        print(f"\n=== Results ===")
        print(f"Time: {elapsed:.2f}s")
        print(f"Requests: {len(latencies)} ({len(errors)} errors)")
        print(f"RPS: {rps:.1f}")
        print(f"Latency avg: {avg:.1f}ms")
        print(f"Latency p50: {p50:.1f}ms")
        print(f"Latency p95: {p95:.1f}ms")
        print(f"Latency p99: {p99:.1f}ms")
        print(f"Max: {max(latencies):.1f}ms")
        print(f"Min: {min(latencies):.1f}ms")

        # Per endpoint
        print(f"\n=== Per Endpoint ===")
        by_endpoint = {}
        for path, lat in results:
            if lat < 0:
                continue
            by_endpoint.setdefault(path, []).append(lat)
        for path, lats in sorted(by_endpoint.items()):
            print(f"  {path}: n={len(lats)}, avg={statistics.mean(lats):.1f}ms, max={max(lats):.1f}ms")

        # Health check
        if p95 < 500:
            print(f"\n✅ Performance OK (p95 < 500ms)")
            return 0
        else:
            print(f"\n⚠ Performance warning (p95 > 500ms)")
            return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))