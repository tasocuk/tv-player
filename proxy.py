#!/usr/bin/env python3
"""
CORS + HTTP proxy for the TV player.

Neden gerekli?
  Tarayıcı iki şeyi engeller:
    1) https sayfadan http sunucuya istek (mixed content)
    2) CORS izni vermeyen sunucuya fetch
  Xtream panelleri genelde ikisine de takılır. Bu script araya girer,
  gerekli başlıkları ekler ve player'ı da kendisi servis eder.

Kullanım:
  python3 proxy.py --upstream http://SUNUCU:PORT
  # sonra TV'de:  http://<bu-bilgisayarın-ip>:8099/

Gereksinim: sadece Python 3 (ek paket yok).
Not: Bu makine açık olduğu sürece çalışır. 7/24 istiyorsan
     Raspberry Pi veya sürekli açık bir mini PC uygun olur.
"""

import argparse
import os
import re
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
UPSTREAM = ""
HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "content-encoding",
    "content-length",
}


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "tvproxy"

    # ------------------------------------------------------------ helpers
    def log_message(self, fmt, *args):
        sys.stderr.write("  %s\n" % (fmt % args))

    def cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,HEAD,OPTIONS")
        self.send_header("Access-Control-Expose-Headers", "*")

    def do_OPTIONS(self):
        self.send_response(204)
        self.cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_HEAD(self):
        self.do_GET(body=False)

    # --------------------------------------------------------------- main
    def do_GET(self, body=True):
        path = self.path

        # 1) statik dosyalar (player'ın kendisi)
        if path == "/" or path.startswith("/index.html") or path.startswith("/assets"):
            return self.serve_static("index.html" if path == "/" else path.lstrip("/").split("?")[0], body)

        # 2) geri kalan her şey upstream'e
        return self.serve_proxy(path, body)

    def serve_static(self, rel, body=True):
        rel = urllib.parse.unquote(rel)
        full = os.path.normpath(os.path.join(HERE, rel))
        if not full.startswith(HERE) or not os.path.isfile(full):
            self.send_error(404, "not found")
            return
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".json": "application/json",
        }.get(os.path.splitext(full)[1], "application/octet-stream")

        data = open(full, "rb").read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.cors()
        self.end_headers()
        if body:
            self.wfile.write(data)

    def serve_proxy(self, path, body=True):
        url = UPSTREAM + path
        req = urllib.request.Request(url, method="GET")
        # bazı paneller User-Agent'a bakıyor
        req.add_header("User-Agent", self.headers.get("User-Agent", "VLC/3.0.20"))
        rng = self.headers.get("Range")
        if rng:
            req.add_header("Range", rng)

        try:
            up = urllib.request.urlopen(req, timeout=25)
        except urllib.error.HTTPError as e:
            up = e
        except Exception as e:
            self.send_response(502)
            self.cors()
            msg = ("upstream error: %s" % e).encode()
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            if body:
                self.wfile.write(msg)
            return

        ctype = up.headers.get("Content-Type", "")
        is_m3u8 = path.lower().split("?")[0].endswith(".m3u8") or "mpegurl" in ctype.lower()

        self.send_response(up.status)
        for k, v in up.headers.items():
            if k.lower() in HOP:
                continue
            self.send_header(k, v)
        self.cors()

        # HLS playlist: içindeki mutlak upstream adreslerini proxy'ye çevir
        if is_m3u8:
            text = up.read().decode("utf-8", "replace")
            text = text.replace(UPSTREAM, "")
            text = re.sub(r"^(https?://[^\s]+)$",
                          lambda m: "/__abs/" + urllib.parse.quote(m.group(1), safe=""),
                          text, flags=re.M)
            data = text.encode()
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if body:
                self.wfile.write(data)
            return

        self.end_headers()
        if not body:
            return
        try:
            while True:
                chunk = up.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass  # TV kanal değiştirdi


def main():
    global UPSTREAM
    ap = argparse.ArgumentParser()
    ap.add_argument("--upstream", required=True, help="http://sunucu:port")
    ap.add_argument("--port", type=int, default=8099)
    a = ap.parse_args()

    UPSTREAM = a.upstream.rstrip("/")
    ip = lan_ip()

    print("")
    print("  TV Player proxy")
    print("  ---------------")
    print("  upstream : %s" % UPSTREAM)
    print("  TV'de aç : http://%s:%d/" % (ip, a.port))
    print("  Player'daki 'Sunucu adresi' alanına da aynı adresi yaz:")
    print("             http://%s:%d" % (ip, a.port))
    print("")
    print("  Durdurmak için Ctrl+C")
    print("")

    ThreadingHTTPServer(("0.0.0.0", a.port), Handler).serve_forever()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  durduruldu")
