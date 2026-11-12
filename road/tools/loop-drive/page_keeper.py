"""A headless road page: hello + watching every 2 s and play, as world.js does; frames dropped."""
import json, sys, time, threading
from websockets.sync.client import connect
secs = float(sys.argv[1]) if len(sys.argv) > 1 else 300
with connect("ws://127.0.0.1:8400/ws", open_timeout=5, max_size=None) as ws:
    send = lambda m: ws.send(json.dumps(m))
    send({"ev": "hello", "since": 1e15}); send({"ev": "world", "domain": "responder", "atoms": ["watching", "hello"]})
    send({"ev": "world", "domain": "responder", "atoms": ["play"]})
    stop = time.time() + secs
    def drain():
        try:
            while True: ws.recv()
        except Exception: pass
    threading.Thread(target=drain, daemon=True).start()
    while time.time() < stop:
        time.sleep(2); send({"ev": "world", "domain": "responder", "atoms": ["watching"]})
