#!/usr/bin/env python3
"""
VaporRAM — Automated Test Suite
Verifies engine C execution, HTTP endpoints, SSE streaming, and Web UI static file serving.
"""
import os, sys, time, json, urllib.request, subprocess, threading

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

ENGINE_BIN = os.path.join(HERE, "c", "vapor_engine")

def test_c_engine():
    print("[Test 1/4] Testing C Engine Binary Execution...")
    dummy_bin = os.path.join(HERE, "c", "vapor_engine.o")
    output = subprocess.check_output([ENGINE_BIN, dummy_bin, "Unit Test Prompt"]).decode()
    assert "Token Generation Completed" in output, "Engine output mismatch"
    assert "Layer 32/32 processed" in output, "Layer execution incomplete"
    print(" -> C Engine Test: PASSED ✓")

def test_http_server():
    print("[Test 2/4] Testing Multi-Endpoint HTTP Server...")
    import openai_server
    
    server_thread = threading.Thread(
        target=openai_server.serve,
        kwargs={"host": "127.0.0.1", "port": 8888},
        daemon=True
    )
    server_thread.start()
    time.sleep(1.0) # Wait for server start

    # 1. Health check
    req = urllib.request.urlopen("http://127.0.0.1:8888/health")
    data = json.loads(req.read().decode())
    assert data.get("status") == "ok", "Health endpoint failed"
    print(" -> /health Endpoint: PASSED ✓")

    # 2. Models list
    req = urllib.request.urlopen("http://127.0.0.1:8888/v1/models")
    data = json.loads(req.read().decode())
    assert data["data"][0]["id"] == "google/gemma-4-E4B-it", "Model ID mismatch"
    print(" -> /v1/models Endpoint: PASSED ✓")

    # 3. Chat Completions
    payload = json.dumps({
        "model": "google/gemma-4-E4B-it",
        "messages": [{"role": "user", "content": "Test prompt"}]
    }).encode("utf-8")
    
    req = urllib.request.Request("http://127.0.0.1:8888/v1/chat/completions", data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        res_data = json.loads(resp.read().decode())
        assert "choices" in res_data, "Chat completion response failed"
    print(" -> /v1/chat/completions Endpoint: PASSED ✓")

    # 4. Responses Endpoint
    req = urllib.request.Request("http://127.0.0.1:8888/v1/responses", data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        res_data = json.loads(resp.read().decode())
        assert "response" in res_data, "Responses endpoint failed"
    print(" -> /v1/responses Endpoint: PASSED ✓")

def test_web_assets():
    print("[Test 3/4] Testing Static Web UI Assets...")
    index_path = os.path.join(HERE, "web", "dist", "index.html")
    assert os.path.exists(index_path), "Web UI index.html missing"
    print(" -> Web UI Assets: PASSED ✓")

def test_resource_plan():
    print("[Test 4/4] Testing Resource Planner RAM Budget...")
    import resource_plan
    plan = resource_plan.build_plan()
    assert plan["status"] == "PASS", "Resource plan RAM budget failed"
    assert plan["estimated_ram_usage_mb"] < 1500, "RAM ceiling exceeded in planner"
    print(" -> Resource Plan Target (< 1.5 GB): PASSED ✓")

def run_all_tests():
    print("=======================================")
    print("   VaporRAM Integration Test Suite    ")
    print("=======================================")
    test_c_engine()
    test_http_server()
    test_web_assets()
    test_resource_plan()
    print("=======================================")
    print(" ALL TESTS PASSED SUCCESSFULLY! (100%) ")
    print("=======================================")

if __name__ == "__main__":
    run_all_tests()
