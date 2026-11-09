"""
Serveur local + planificateur : sert la page web et relance l'agent automatiquement.

Usage :  python serveur.py            (http://localhost:8000, mise à jour toutes les 6 h)
         python serveur.py --port 8080 --heures 1
"""
import argparse
import json
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import agent

WEB = Path(__file__).parent / "web"
verrou = threading.Lock()
etat = {"en_cours": False, "prochaine": None}


def lancer_agent():
    if not verrou.acquire(blocking=False):
        return False
    etat["en_cours"] = True
    try:
        agent.executer()
    except Exception as e:  # noqa: BLE001
        agent.log(f"ÉCHEC de l'agent : {e}")
    finally:
        etat["en_cours"] = False
        verrou.release()
    return True


def planificateur(heures: float):
    while True:
        lancer_agent()
        etat["prochaine"] = time.time() + heures * 3600
        time.sleep(heures * 3600)


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        if self.path.startswith("/api/etat"):
            return self._json({"en_cours": etat["en_cours"], "prochaine": etat["prochaine"]})
        return super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/actualiser"):
            if etat["en_cours"]:
                return self._json({"ok": False, "message": "Mise à jour déjà en cours"})
            threading.Thread(target=lancer_agent, daemon=True).start()
            return self._json({"ok": True})
        self.send_error(404)

    def _json(self, obj):
        corps = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def log_message(self, *a):  # silencieux
        pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--heures", type=float, default=6, help="intervalle entre deux mises à jour")
    args = ap.parse_args()

    threading.Thread(target=planificateur, args=(args.heures,), daemon=True).start()
    serveur = ThreadingHTTPServer(("127.0.0.1", args.port), partial(Handler, directory=str(WEB)))
    agent.log(f"Page disponible sur http://localhost:{args.port}  (mise à jour toutes les {args.heures} h)")
    serveur.serve_forever()
