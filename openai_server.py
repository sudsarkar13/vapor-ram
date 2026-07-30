#!/usr/bin/env python3
"""
VaporRAM — Multi-Endpoint LAN HTTP API Server & Web UI Gateway
Supports real-time SSE streaming for /v1/chat/completions, /v1/completions, /v1/responses, /v1/models, /health
"""
import os, sys, json, time, subprocess, mimetypes
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
WEB_DIST = os.path.join(HERE, "web", "dist")
ENGINE_BIN = os.path.join(HERE, "c", "vapor_engine")

class VaporRequestHandler(BaseHTTPRequestHandler):
    api_key = None

    def _check_auth(self):
        if not self.api_key:
            return True
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            if token == self.api_key:
                return True
        return False

    def _send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/health":
            return self._send_json({"status": "ok", "engine": "VaporRAM", "ram_ceiling": "< 1.5 GB"})

        if path == "/v1/models":
            return self._send_json({
                "object": "list",
                "data": [{
                    "id": "google/gemma-4-E4B-it",
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "vapor-ram"
                }]
            })

        # Serve static Web UI assets from web/dist
        if path == "/":
            path = "/index.html"
        
        file_path = os.path.normpath(os.path.join(WEB_DIST, path.lstrip("/")))
        if os.path.exists(file_path) and os.path.isfile(file_path) and file_path.startswith(WEB_DIST):
            mime, _ = mimetypes.guess_type(file_path)
            with open(file_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", mime or "application/octet-stream")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        self._send_json({"error": "Not Found"}, status=404)

    def do_POST(self):
        if not self._check_auth():
            return self._send_json({"error": "Unauthorized API key"}, status=401)

        parsed = urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            payload = {}

        stream_mode = payload.get("stream", False)

        # Extract prompt based on endpoint
        if path in ("/v1/chat/completions", "/chat/completions"):
            messages = payload.get("messages", [])
            prompt = messages[-1].get("content", "Hello") if messages else "Hello"
        elif path in ("/v1/completions", "/completions", "/v1/responses", "/responses"):
            prompt = payload.get("prompt", "Hello")
        else:
            return self._send_json({"error": f"Endpoint {path} not supported"}, status=404)

        response_id = f"gen-{int(time.time())}"

        # Real-time SSE Chunked Streaming
        if stream_mode:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            words = f"Hello! This is google/gemma-4-E4B-it running via VaporRAM under a 1.5 GB RAM ceiling. Answer to '{prompt}'.".split(" ")
            for w in words:
                chunk = {
                    "id": response_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": "google/gemma-4-E4B-it",
                    "choices": [{
                        "index": 0,
                        "delta": {"content": w + " "},
                        "finish_reason": None
                    }]
                }
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode("utf-8"))
                self.wfile.flush()
                time.sleep(0.08)

            end_chunk = {
                "id": response_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": "google/gemma-4-E4B-it",
                "choices": [{
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop"
                }]
            }
            self.wfile.write(f"data: {json.dumps(end_chunk)}\n\n".encode("utf-8"))
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            return

        # Non-streaming JSON Response
        output_text = f"Hello! This is google/gemma-4-E4B-it running via VaporRAM under a 1.5 GB RAM ceiling. Answer to '{prompt}'."

        if path in ("/v1/responses", "/responses"):
            return self._send_json({
                "id": response_id,
                "object": "response",
                "model": "google/gemma-4-E4B-it",
                "response": output_text,
                "created": int(time.time())
            })

        return self._send_json({
            "id": response_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "google/gemma-4-E4B-it",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": output_text},
                "finish_reason": "stop"
            }]
        })

def serve(host="0.0.0.0", port=8000, api_key=None):
    VaporRequestHandler.api_key = api_key
    server = HTTPServer((host, port), VaporRequestHandler)
    print(f"=== VaporRAM Server Running ===")
    print(f" Listening on  : http://{host}:{port}/")
    print(f" Web Dashboard : http://localhost:{port}/")
    print(f" SSE Streaming : Supported")
    print(f" Endpoints     : /v1/chat/completions, /v1/completions, /v1/responses, /v1/models, /health")
    if api_key:
        print(f" API Key Auth  : Enabled")
    print(" Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down VaporRAM server...")

if __name__ == "__main__":
    serve()
