import asyncio
import time
import subprocess
import psutil
import httpx
from typing import Dict, Any, Optional

BASE_URL = "http://127.0.0.1:11434"
MODEL = "gemma4:e2b"


def get_vram_usage_mb() -> Optional[float]:
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if res.returncode == 0 and res.stdout.strip():
            return float(res.stdout.strip().split("\n")[0])
    except Exception:
        pass
    return None


def get_system_ram_gb() -> float:
    return round(psutil.virtual_memory().used / (1024**3), 2)


def get_ai_processes_ram_mb() -> float:
    total_mb = 0.0
    for p in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            name = p.info["name"].lower()
            if any(k in name for k in ["ollama", "llama"]):
                mem = p.info["memory_info"]
                if mem:
                    total_mb += mem.rss / (1024 * 1024)
        except Exception:
            continue
    return round(total_mb, 2)


async def run_benchmark():
    print("==================================================================")
    print("      SMART MANAGER HARDWARE RESOURCE BENCHMARK (RTX 3050 6GB)    ")
    print("==================================================================")

    # 1. Baseline measurements
    idle_ram = get_system_ram_gb()
    idle_vram = get_vram_usage_mb()
    ai_idle_ram = get_ai_processes_ram_mb()
    print(f"\n[BASELINE (Idle)]")
    print(f"  System RAM Used:     {idle_ram} GB / {round(psutil.virtual_memory().total / (1024**3), 2)} GB")
    print(f"  GPU VRAM Used:       {idle_vram} MB / 6144 MB")
    print(f"  Ollama/Llama RAM:    {ai_idle_ram} MB")

    test_prompt = "You are Smart Manager. Inspect my available disk drives and free storage."

    # 2. Benchmark with 4096 context tokens
    print(f"\n[TEST 1: 4096-Token Context Window (Standard)]")
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=60.0) as client:
        res4096 = await client.post(
            f"{BASE_URL}/api/generate",
            json={
                "model": MODEL,
                "prompt": test_prompt,
                "stream": False,
                "keep_alive": "5m",
                "options": {
                    "num_ctx": 4096,
                    "num_batch": 128,
                    "num_predict": 256,
                    "temperature": 0.2,
                },
            },
        )
    latency_4096 = round(time.perf_counter() - t0, 2)
    data_4096 = res4096.json()
    eval_count_4096 = data_4096.get("eval_count", 0)
    eval_duration_s = (data_4096.get("eval_duration", 0) / 1e9)
    tok_per_sec_4096 = round(eval_count_4096 / eval_duration_s, 2) if eval_duration_s > 0 else 0
    vram_4096 = get_vram_usage_mb()
    ram_4096 = get_ai_processes_ram_mb()

    print(f"  Total Latency:       {latency_4096}s")
    print(f"  Token Speed:         {tok_per_sec_4096} tok/s ({eval_count_4096} tokens generated)")
    print(f"  GPU VRAM Used:       {vram_4096} MB")
    print(f"  Ollama/Llama RAM:    {ram_4096} MB")

    # 3. Benchmark with 2048 context tokens
    print(f"\n[TEST 2: 2048-Token Context Window (Resource-Optimized)]")
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=60.0) as client:
        res2048 = await client.post(
            f"{BASE_URL}/api/generate",
            json={
                "model": MODEL,
                "prompt": test_prompt,
                "stream": False,
                "keep_alive": "5m",
                "options": {
                    "num_ctx": 2048,
                    "num_batch": 128,
                    "num_predict": 256,
                    "temperature": 0.2,
                },
            },
        )
    latency_2048 = round(time.perf_counter() - t0, 2)
    data_2048 = res2048.json()
    eval_count_2048 = data_2048.get("eval_count", 0)
    eval_duration_s = (data_2048.get("eval_duration", 0) / 1e9)
    tok_per_sec_2048 = round(eval_count_2048 / eval_duration_s, 2) if eval_duration_s > 0 else 0
    vram_2048 = get_vram_usage_mb()
    ram_2048 = get_ai_processes_ram_mb()

    print(f"  Total Latency:       {latency_2048}s")
    print(f"  Token Speed:         {tok_per_sec_2048} tok/s ({eval_count_2048} tokens generated)")
    print(f"  GPU VRAM Used:       {vram_2048} MB")
    print(f"  Ollama/Llama RAM:    {ram_2048} MB")

    # 4. Unload test
    print(f"\n[TEST 3: On-Demand VRAM & RAM Unload]")
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.post(f"{BASE_URL}/api/generate", json={"model": MODEL, "keep_alive": 0})

    await asyncio.sleep(1.0)
    unloaded_vram = get_vram_usage_mb()
    unloaded_ram = get_ai_processes_ram_mb()
    print(f"  Post-Unload VRAM:    {unloaded_vram} MB")
    print(f"  Post-Unload RAM:     {unloaded_ram} MB")

    print("\n==================================================================")
    print("                     BENCHMARK SUMMARY                            ")
    print("==================================================================")
    print(f"  Context 4096: {latency_4096}s latency | {tok_per_sec_4096} t/s | VRAM: {vram_4096} MB")
    print(f"  Context 2048: {latency_2048}s latency | {tok_per_sec_2048} t/s | VRAM: {vram_2048} MB")
    print(f"  Unload freed VRAM back to {unloaded_vram} MB and process RAM to {unloaded_ram} MB.")


if __name__ == "__main__":
    asyncio.run(run_benchmark())
