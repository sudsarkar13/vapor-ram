#!/usr/bin/env python3
"""
VaporRAM — Main CLI Launcher
Ultra-Low RAM SSD Streaming Engine for google/gemma-4-E4B-it
"""
import os, sys, argparse, subprocess, webbrowser, socket, json

from . import paths
from .version import __version__

# Resolved for both a git checkout and an installed package.
HERE = paths.install_root()
ENGINE_BIN = paths.engine_bin()
PRESETS_DIR = paths.presets_dir()

BANNER = f"""\033[1;36m
  💨 VaporRAM v{__version__}
  Ultra-Low RAM SSD Streaming Engine for google/gemma-4-E4B-it
\033[0m"""

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def indent_block(text, prefix="    "):
    return "\n".join(prefix + line for line in text.splitlines())


def remote_access_help(port=8000):
    """Deliberately tunnel-first.

    Forwarding the port on a router publishes a plain HTTP service to the
    internet, which sends the API key across it in cleartext and lets anyone
    scanning the address knock on it. A tunnel gives TLS and a hostname
    without opening anything inbound.
    """
    return [
        "    The LAN URL above only works on this network. For access from anywhere,",
        "    put a TLS tunnel in front of the server rather than forwarding the port:",
        "",
        f"      cloudflared tunnel --url http://localhost:{port}",
        f"      tailscale serve {port}            # private to your tailnet",
        f"      ssh -R {port}:localhost:{port} user@your-vps",
        "",
        "    Then use the https:// address the tunnel prints as the base URL, with the",
        "    same API key. If you do forward the port on your router instead, note that",
        "    plain HTTP sends the key in cleartext — terminate TLS in front of it.",
    ]


def probe_server(port, key):
    """Ask a running server what it actually requires, instead of assuming.

    Without this, `vapor share` would print a key for a server started with
    --no-auth, or the stored key for a server started with a different one --
    telling the user something that does not work.

    Returns (running, auth_required, key_matches).
    """
    import urllib.request, urllib.error
    base = f"http://127.0.0.1:{port}"
    try:
        with urllib.request.urlopen(f"{base}/health", timeout=1.5) as r:
            health = json.loads(r.read().decode())
    except Exception:
        return False, None, None

    # /health is public but reports only the engine identity until a valid key
    # is presented, so auth_required in that thin payload is the honest answer.
    auth_required = bool(health.get("auth_required"))
    if not auth_required:
        return True, False, None

    req = urllib.request.Request(f"{base}/v1/models", headers={"X-API-Key": key or ""})
    try:
        with urllib.request.urlopen(req, timeout=1.5):
            return True, True, True
    except urllib.error.HTTPError as e:
        return True, True, e.code != 401
    except Exception:
        return True, True, None


def list_presets():
    print("=== VaporRAM Persona Presets ===")
    if os.path.exists(PRESETS_DIR):
        for f in sorted(os.listdir(PRESETS_DIR)):
            if f.endswith(".json"):
                p_path = os.path.join(PRESETS_DIR, f)
                try:
                    data = json.load(open(p_path))
                    print(f"  - \033[1;33m{f[:-5]:<10}\033[0m : {data.get('name', 'Preset')} (temp={data.get('temperature', 0.2)})")
                except Exception:
                    pass
    print()

def main():
    parser = argparse.ArgumentParser(description="VaporRAM — Ultra-Low RAM SSD Streaming Engine for google/gemma-4-E4B-it")
    parser.add_argument("--version", action="version", version=f"VaporRAM {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    # Commands
    subparsers.add_parser("doctor", help="Run system and hardware diagnostics")
    subparsers.add_parser("plan", help="Display memory budget breakdown (< 1.5 GB RAM)")
    subparsers.add_parser("bench", help="Run performance & RAM benchmark")
    subparsers.add_parser("profile", help="Run high-precision RAM memory profiler")
    
    inspect_parser = subparsers.add_parser("inspect", help="Inspect model weight files and tensor layout")
    inspect_parser.add_argument("--dir", default=paths.default_model_dir(), help="Model directory")

    subparsers.add_parser("config", help="Run interactive terminal configuration wizard")
    subparsers.add_parser("lan", help="Display LAN IP and network sharing instructions")
    subparsers.add_parser("presets", help="List available persona presets")
    subparsers.add_parser("init-config", help="Create default vapor.json configuration file")
    subparsers.add_parser("release", help="Build standalone release distribution tarball (.tar.gz)")

    comp_parser = subparsers.add_parser("completion", help="Generate shell autocompletion script (bash/zsh)")
    comp_parser.add_argument("shell", nargs="?", default="bash", choices=["bash", "zsh"], help="Shell type (bash or zsh)")

    download_parser = subparsers.add_parser("download", help="Download google/gemma-4-E4B-it weights")
    download_parser.add_argument("--repo", default="google/gemma-4-E4B-it", help="Hugging Face repo ID")
    download_parser.add_argument("--dest", default=paths.default_model_dir(), help="Destination directory")

    run_parser = subparsers.add_parser("run", help="One-shot prompt generation")
    run_parser.add_argument("prompt", nargs="+", help="Prompt text")
    run_parser.add_argument("--preset", default=None, help="Preset name (e.g. coder, reasoner, concise)")
    run_parser.add_argument("--think", dest="think", action="store_true", default=None,
                            help="Show the model's reasoning (default: on when supported)")
    run_parser.add_argument("--think-level", dest="think_level", default=None,
                            choices=["low", "medium", "high", "xhigh"],
                            help="How hard to think (default: high)")
    run_parser.add_argument("--no-think", dest="think", action="store_false",
                            help="Skip reasoning and answer directly")

    chat_parser = subparsers.add_parser("chat", help="Interactive terminal chat session")
    chat_parser.add_argument("--preset", default=None, help="Preset name (e.g. coder, reasoner, concise)")
    chat_parser.add_argument("--think", dest="think", action="store_true", default=None,
                            help="Show the model's reasoning (default: on when supported)")
    chat_parser.add_argument("--think-level", dest="think_level", default=None,
                            choices=["low", "medium", "high", "xhigh"],
                            help="How hard to think (default: high)")
    chat_parser.add_argument("--no-think", dest="think", action="store_false",
                            help="Skip reasoning and answer directly")

    serve_parser = subparsers.add_parser("serve", help="Host LAN HTTP API server")
    serve_parser.add_argument("--host", default="0.0.0.0", help="Host address (default: 0.0.0.0)")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port number (default: 8000)")
    serve_parser.add_argument("--api-key", default=None,
                              help="API key clients must present (default: generated and reused)")
    serve_parser.add_argument("--new-key", action="store_true",
                              help="Issue a fresh API key, revoking the previous one")
    serve_parser.add_argument("--no-auth", action="store_true",
                              help="Serve without an API key (anyone who can reach the port can use the model)")
    serve_parser.add_argument("--think", dest="think", action="store_true", default=None,
                            help="Enable model reasoning (default: on when the model supports it)")
    serve_parser.add_argument("--think-level", dest="think_level", default=None,
                            choices=["low", "medium", "high", "xhigh"],
                            help="How hard to think (default: high)")
    serve_parser.add_argument("--no-think", dest="think", action="store_false",
                            help="Disable model reasoning")
    serve_parser.add_argument("--no-preload", action="store_true",
                              help="Load the weights on the first message instead of at startup")

    web_parser = subparsers.add_parser("web", help="Launch server and open Web UI in browser")
    web_parser.add_argument("--port", type=int, default=8000, help="Port number (default: 8000)")
    # Loopback by default: `web` means "open the dashboard here", and binding
    # every interface is a sharing decision the user should make on purpose.
    web_parser.add_argument("--host", default="127.0.0.1",
                            help="Host address (default: 127.0.0.1, local only)")
    web_parser.add_argument("--share", action="store_true",
                            help="Bind all interfaces so other devices on the network can connect")
    web_parser.add_argument("--api-key", default=None, help="API key to require when sharing")
    web_parser.add_argument("--no-auth", action="store_true",
                            help="Skip API key authentication even when sharing")
    web_parser.add_argument("--think", dest="think", action="store_true", default=None,
                            help="Enable model reasoning (default: on when the model supports it)")
    web_parser.add_argument("--think-level", dest="think_level", default=None,
                            choices=["low", "medium", "high", "xhigh"],
                            help="How hard to think (default: high)")
    web_parser.add_argument("--no-think", dest="think", action="store_false",
                            help="Disable model reasoning")
    web_parser.add_argument("--no-preload", action="store_true",
                            help="Load the weights on the first message instead of at startup")

    stop_parser = subparsers.add_parser(
        "stop", help="Stop a running VaporRAM server from another terminal")
    stop_parser.add_argument("--port", type=int, default=8000, help="Port the server listens on (default: 8000)")

    share_parser = subparsers.add_parser(
        "share", help="Show the URL, API key and client snippets for other devices")
    share_parser.add_argument("--port", type=int, default=8000, help="Port the server listens on (default: 8000)")
    share_parser.add_argument("--new-key", action="store_true",
                              help="Issue a fresh API key, revoking the previous one")
    share_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    args = parser.parse_args()

    if not args.command:
        print(BANNER)
        parser.print_help()
        sys.exit(0)

    if args.command == "doctor":
        from . import doctor
        results = doctor.run_doctor()
        print(doctor.format_doctor(results))
    
    elif args.command == "plan":
        from . import resource_plan
        plan = resource_plan.build_plan()
        print(resource_plan.format_plan(plan))

    elif args.command == "bench":
        paths.ensure_tools_importable()
        import bench
        bench.run_benchmark()

    elif args.command == "profile":
        paths.ensure_tools_importable()
        import profile_memory
        profile_memory.profile_memory()

    elif args.command == "inspect":
        paths.ensure_tools_importable()
        import inspect_shards
        inspect_shards.inspect_shards(args.dir)

    elif args.command == "config":
        paths.ensure_tools_importable()
        import configure_wizard
        configure_wizard.run_wizard()

    elif args.command == "completion":
        paths.ensure_tools_importable()
        import generate_completion
        generate_completion.generate(args.shell)

    elif args.command == "release":
        paths.ensure_tools_importable()
        import package_release
        package_release.create_release()

    elif args.command == "presets":
        list_presets()

    elif args.command == "init-config":
        from . import config
        config.save_default_config()

    elif args.command == "download":
        paths.ensure_tools_importable()
        import download_model
        download_model.download_model(args.repo, args.dest)

    elif args.command == "lan":
        local_ip = get_local_ip()
        print("=== VaporRAM Local Area Network (LAN) Gateway ===")
        print(f" Local Host IP : \033[1;32m{local_ip}\033[0m")
        print(f" Web UI URL    : \033[1;36mhttp://{local_ip}:8000/\033[0m")
        print(f" API Endpoint  : \033[1;36mhttp://{local_ip}:8000/v1/chat/completions\033[0m")
        print(f" Responses API : \033[1;36mhttp://{local_ip}:8000/v1/responses\033[0m")
        print("\n Requests from other devices need the API key.")
        print(" Run \033[1;33mvapor share\033[0m for the key and ready-to-paste client snippets.")

    elif args.command == "run":
        from . import openai_server
        prompt_str = " ".join(args.prompt)
        preset_id = args.preset or "default"
        if preset_id not in openai_server.PRESETS:
            print(f"\033[1;33m[Warning]\033[0m Unknown preset '{preset_id}'; using default.")
            preset_id = "default"
        want_think = args.think
        if want_think is None:
            want_think = openai_server.THINKING_ENABLED
        want_think = want_think and openai_server.detect_thinking_support()
        if args.think_level:
            openai_server.REASONING_EFFORT = args.think_level

        state = {"in_think": False}

        def show_thinking(piece):
            # Reasoning is dimmed so it reads as working-out rather than answer.
            if not state["in_think"]:
                sys.stdout.write("\033[90m\u2500\u2500 thinking \u2500\u2500\n")
                state["in_think"] = True
            sys.stdout.write(piece)
            sys.stdout.flush()

        def show_answer(piece):
            if state["in_think"]:
                sys.stdout.write("\033[0m\n\033[90m\u2500\u2500 answer \u2500\u2500\033[0m\n")
                state["in_think"] = False
            sys.stdout.write(piece)
            sys.stdout.flush()

        print(f"\033[1;36m[VaporRAM Output]\033[0m")
        try:
            openai_server.generate_text(
                [{"role": "user", "content": prompt_str}],
                preset_id=preset_id,
                enable_thinking=want_think,
                on_chunk=show_answer,
                on_thinking=show_thinking if want_think else None,
            )
            print("\n")
        except openai_server.EngineError as e:
            print(f"\033[1;31m[Engine Error]\033[0m {e}\n")
            sys.exit(1)

    elif args.command == "chat":
        from . import openai_server
        preset_id = args.preset or "default"
        if preset_id not in openai_server.PRESETS:
            print(f"\033[1;33m[Warning]\033[0m Unknown preset '{preset_id}'; using default.")
            preset_id = "default"
        preset = openai_server.PRESETS[preset_id]

        print("\033[1;36m=== VaporRAM Interactive Terminal Chat ===\033[0m")
        print(f" Model   : \033[1;33m{openai_server.MODEL_ID}\033[0m")
        print(f" Preset  : \033[1;35m{preset['name']}\033[0m (temp={preset['temperature']}, top_p={preset['top_p']})")
        print(f" Context : \033[1;32m{openai_server.n_ctx} tokens\033[0m")
        think_state = {"on": args.think if args.think is not None
                       else openai_server.THINKING_ENABLED}
        think_state["on"] = think_state["on"] and openai_server.detect_thinking_support()
        if args.think_level:
            openai_server.REASONING_EFFORT = args.think_level
        print(f" Thinking: \033[1;35m{'on' if think_state['on'] else 'off'}\033[0m"
              f" \033[90m(effort: {openai_server.REASONING_EFFORT})\033[0m"
              f" \033[1;30m(/think to toggle)\033[0m")
        print(" Commands: \033[1;30m/stats, /presets, /think, /clear, /reset, /exit\033[0m\n")

        # Conversation history is kept and replayed, so follow-up questions have context.
        history = []
        while True:
            try:
                cmd = input("\033[1;32mVaporUser > \033[0m").strip()
                if not cmd:
                    continue
                if cmd.lower() in ("/exit", "exit", "quit"):
                    print("Goodbye!")
                    break
                elif cmd.lower() == "/stats":
                    rss = openai_server.get_process_rss_mb()
                    total, avail = openai_server.get_live_ram()
                    state = openai_server.get_model_state()
                    print(f" Engine RSS : {rss} MB" if rss else " Engine RSS : unavailable")
                    print(f" Host RAM   : {avail:.1f} GB free of {total:.1f} GB")
                    print(f" Context    : {openai_server.n_ctx} tokens")
                    print(f" Model      : {state['status']} — {state['message']}")
                    print(f" History    : {len(history)} messages\n")
                    continue
                elif cmd.lower() == "/presets":
                    list_presets()
                    continue
                elif cmd.lower() == "/clear":
                    os.system("cls" if os.name == "nt" else "clear")
                    continue
                elif cmd.lower() in ("/think", "/thinking"):
                    if not openai_server.detect_thinking_support():
                        print(" This model has no thinking channel; leaving it off.\n")
                        continue
                    think_state["on"] = not think_state["on"]
                    print(f" Thinking {'on' if think_state['on'] else 'off'}.\n")
                    continue
                elif cmd.lower() == "/reset":
                    history = []
                    print(" Conversation history cleared.\n")
                    continue

                history.append({"role": "user", "content": cmd})
                turn = {"in_think": False}

                def on_think(piece):
                    if not turn["in_think"]:
                        sys.stdout.write("\033[90m\u2500\u2500 thinking \u2500\u2500\n")
                        turn["in_think"] = True
                    sys.stdout.write(piece)
                    sys.stdout.flush()

                def on_answer(piece):
                    if turn["in_think"]:
                        sys.stdout.write("\033[0m\n\033[1;36mVaporRAM >\033[0m ")
                        turn["in_think"] = False
                    sys.stdout.write(piece)
                    sys.stdout.flush()

                if not think_state["on"]:
                    sys.stdout.write("\033[1;36mVaporRAM >\033[0m ")
                    sys.stdout.flush()
                try:
                    reply = openai_server.generate_text(
                        history,
                        preset_id=preset_id,
                        enable_thinking=think_state["on"],
                        on_chunk=on_answer,
                        on_thinking=on_think if think_state["on"] else None,
                    )
                    history.append({"role": "assistant", "content": reply})
                    print("\n")
                except openai_server.EngineError as e:
                    history.pop()
                    print(f"\033[1;31m{e}\033[0m\n")
            except KeyboardInterrupt:
                print("\nSession interrupted.")
                break
            except EOFError:
                print()
                break

    elif args.command == "serve":
        from . import openai_server
        # Before anything spawns a thread: a thread that does not block SIGINT
        # can absorb the CTRL+C that sigwait() is waiting for.
        openai_server.block_shutdown_signals()
        if args.think is not None:
            openai_server.THINKING_ENABLED = args.think
        if args.think_level:
            openai_server.REASONING_EFFORT = args.think_level
        if args.new_key:
            openai_server.rotate_api_key()
        openai_server.serve(host=args.host, port=args.port, api_key=args.api_key,
                            require_auth=False if args.no_auth else None,
                            preload=not args.no_preload)

    elif args.command == "web":
        import threading, time
        from . import openai_server
        # Must precede the browser-opening thread below, so that thread
        # inherits the block and cannot swallow CTRL+C.
        openai_server.block_shutdown_signals()
        if args.think is not None:
            openai_server.THINKING_ENABLED = args.think
        if args.think_level:
            openai_server.REASONING_EFFORT = args.think_level
        host = "0.0.0.0" if args.share else args.host
        share = openai_server.configure_sharing(
            host, args.port, api_key=args.api_key,
            require_auth=False if args.no_auth else None)

        # Open the local dashboard, carrying the key in the URL when one is
        # required — otherwise `vapor web --share` would launch a browser that
        # immediately gets a 401 from its own server.
        local = f"http://localhost:{args.port}/"
        if share["auth_required"]:
            local += f"?key={share['api_key']}"

        def open_browser():
            time.sleep(1.5)
            webbrowser.open(local)
        threading.Thread(target=open_browser, daemon=True).start()
        openai_server.serve(host=host, port=args.port, api_key=args.api_key,
                            require_auth=False if args.no_auth else None,
                            preload=not args.no_preload)

    elif args.command == "stop":
        # Uses the same endpoint as the dashboard's Stop button, so it works
        # whenever the Web UI does -- including when the terminal cannot
        # deliver CTRL+C to the server process.
        import urllib.request, urllib.error
        from . import openai_server
        base = f"http://127.0.0.1:{args.port}"
        key = openai_server.load_persisted_api_key()

        def attempt(headers):
            req = urllib.request.Request(f"{base}/v1/system/stop", data=b"{}",
                                         headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status

        try:
            try:
                attempt({"Content-Type": "application/json"})
            except urllib.error.HTTPError as e:
                if e.code != 401 or not key:
                    raise
                attempt({"Content-Type": "application/json", "X-API-Key": key})
            print(f"\033[32m[VaporRAM]\033[0m Server on port {args.port} stopped.")
        except urllib.error.HTTPError as e:
            if e.code == 401:
                print(f"\033[1;31m[VaporRAM]\033[0m Server on port {args.port} rejected the stored API key.")
                print("  Pass the key the server was started with, or use: kill <pid>")
            else:
                print(f"\033[1;31m[VaporRAM]\033[0m Server returned HTTP {e.code}.")
            sys.exit(1)
        except Exception:
            print(f"\033[1;33m[VaporRAM]\033[0m No server responding on port {args.port}.")
            sys.exit(1)

    elif args.command == "share":
        from . import openai_server
        key = (openai_server.rotate_api_key() if args.new_key
               else openai_server.load_persisted_api_key() or openai_server.resolve_api_key())
        running, auth_required, key_matches = probe_server(args.port, key)
        info = openai_server.share_urls(
            host="0.0.0.0", port=args.port, api_key=key,
            # Describe the live server when there is one; otherwise describe
            # what `vapor serve` would do, which is require a key.
            auth_required=True if auth_required is None else auth_required)
        snippets = openai_server.client_snippets(info)
        info["server_running"] = running

        if args.json:
            print(json.dumps({"share": info, "snippets": snippets}, indent=2))
        else:
            print(BANNER)
            print("\033[1;36m  Share this model with another device\033[0m\n")
            print(openai_server.format_share_block(info))
            if not running:
                print(f"\n  \033[1;33m! No server is listening on port {args.port} yet.\033[0m")
                print(f"  \033[90m  Start one with: \033[0mvapor serve --port {args.port}")
            elif key_matches is False:
                print(f"\n  \033[1;33m! The server on port {args.port} rejected this key.\033[0m")
                print("  \033[90m  It was started with a different --api-key; use that one,\033[0m")
                print("  \033[90m  or restart it without --api-key to use the stored key.\033[0m")
            print("\n\033[1;36m  From another device on the same network\033[0m")
            print("\033[90m" + indent_block(snippets["curl"]) + "\033[0m")
            print("\n\033[1;36m  Any OpenAI-compatible client\033[0m")
            print("\033[90m" + indent_block(snippets["openai_python"]) + "\033[0m")
            print("\n\033[1;36m  Reaching it from outside this network\033[0m")
            for line in remote_access_help(args.port):
                print(f"\033[90m{line}\033[0m")
            print()

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
