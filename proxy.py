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
import json
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
PRESET = None          # TV'de hiçbir şey yazmamak için sayfaya gömülen ayar
PRESET_FILE = ""       # ayarın diske yazıldığı yer (yeniden başlatınca kaybolmasın)
UA = "VLC/3.0.20 LibVLC/3.0.20"
HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "content-encoding",
    "content-length",
}


SETUP_PAGE = """<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>TV Kurulum</title>
<style>
 body{background:#0b0d12;color:#e8ecf4;font:400 17px/1.45 system-ui,-apple-system,sans-serif;
      margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}
 .c{width:min(680px,100%);background:#141821;border:1px solid #262e3d;border-radius:16px;padding:30px}
 h1{font-size:25px;margin:0 0 6px} p.s{color:#8a93a6;margin:0 0 22px}
 label{display:block;color:#8a93a6;font-size:14px;margin:18px 0 6px}
 input{width:100%;padding:13px 14px;background:#1b2130;border:1px solid #262e3d;
       border-radius:9px;color:inherit;font:inherit;box-sizing:border-box}
 button{width:100%;margin-top:22px;padding:15px;background:#1f6fd0;border:0;border-radius:9px;
        color:#fff;font:600 17px system-ui;cursor:pointer}
 #m{margin-top:18px;font-size:16px;display:none} #m.on{display:block}
 .ok{color:#3ecf8e} .bad{color:#ff5c5c}
 code{background:#000;padding:2px 7px;border-radius:5px;font-size:15px}
</style></head><body><div class="c">
 <h1>Televizyon kurulumu</h1>
 <p class="s">Kaydet dedikten sonra televizyonda adresi açman yeterli — orada hiçbir şey yazmayacaksın.</p>
 <label for="u">M3U liste adresi</label>
 <input id="u" placeholder="http://sunucu.com:80/get.php?username=...&amp;type=m3u_plus" spellcheck="false">
 <button id="b">Kaydet</button>
 <div id="m"></div>
</div><script>
 // Bu sayfa player ile aynı adreste olduğu için, daha önce girilmiş ayar
 // tarayıcıda kayıtlıysa doğrudan buraya gelir; kullanıcı yapıştırmak zorunda kalmaz.
 try{ var c = JSON.parse(localStorage.getItem('cfg')||'null');
      if (c && c.m3u) document.getElementById('u').value = c.m3u; }catch(e){}
 var m = document.getElementById('m');
 document.getElementById('b').onclick = async function(){
   var v = document.getElementById('u').value.trim();
   if(!v){ m.className='on bad'; m.textContent='Adres boş.'; return; }
   m.className='on'; m.textContent='Kaydediliyor…';
   try{
     var r = await fetch('/__preset',{method:'POST',body:JSON.stringify({m3u:v})});
     if(!r.ok) throw new Error('HTTP '+r.status);
     m.className='on ok';
     m.innerHTML='✓ Kaydedildi. Şimdi televizyonda <code>'+location.host+'</code> adresini aç.';
   }catch(e){ m.className='on bad'; m.textContent='Kaydedilemedi: '+e.message; }
 };
</script></body></html>"""


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

    def do_POST(self):
        global PRESET
        if self.path.split("?")[0] != "/__preset":
            self.send_error(404, "not found")
            return
        try:
            n = int(self.headers.get("Content-Length", "0"))
            data = json.loads(self.rfile.read(n).decode("utf-8"))
            url = (data.get("m3u") or "").strip()
            if not url:
                raise ValueError("m3u bos")
            PRESET = {"mode": "m3u", "m3u": url}
            if PRESET_FILE:
                with open(PRESET_FILE, "w", encoding="utf-8") as f:
                    json.dump(PRESET, f)
            out = b'{"ok":true}'
            self.send_response(200)
        except Exception as e:
            out = json.dumps({"ok": False, "error": str(e)}).encode()
            self.send_response(400)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.cors()
        self.end_headers()
        self.wfile.write(out)

    # --------------------------------------------------------------- main
    def do_GET(self, body=True):
        path = self.path

        # 0) kurulum sayfası
        if path.split("?")[0] in ("/__setup", "/__setup/"):
            body_bytes = SETUP_PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body_bytes)))
            self.send_header("Cache-Control", "no-store")
            self.cors()
            self.end_headers()
            if body:
                self.wfile.write(body_bytes)
            return

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

        # index.html servis edilirken ayarı sayfaya göm: televizyonun
        # tarayıcısında hiçbir şey yazmadan liste açılsın.
        if PRESET and full.endswith("index.html"):
            tag = ('<script>window.__PRESET=%s;</script>'
                   % json.dumps(PRESET)).encode()
            data = data.replace(b"</head>", tag + b"</head>", 1)

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
        # Çoğu panel tarayıcı User-Agent'ını reddediyor, medya oynatıcı
        # kimliğini kabul ediyor. Tarayıcınınkini geçirmek yerine sabitliyoruz.
        req.add_header("User-Agent", UA)
        req.add_header("Accept", "*/*")
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
    global UPSTREAM, PRESET, PRESET_FILE
    ap = argparse.ArgumentParser()
    ap.add_argument("--upstream", required=True, help="http://sunucu:port")
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--m3u", default="",
                    help="M3U liste adresi; verilirse sayfaya gömülür ve "
                         "televizyonda elle yazmak gerekmez")
    a = ap.parse_args()

    UPSTREAM = a.upstream.rstrip("/")
    PRESET_FILE = os.path.join(HERE, "preset.json")
    if a.m3u:
        PRESET = {"mode": "m3u", "m3u": a.m3u}
    elif os.path.isfile(PRESET_FILE):
        try:
            with open(PRESET_FILE, encoding="utf-8") as f:
                PRESET = json.load(f)
        except Exception:
            PRESET = None
    ip = lan_ip()

    print("")
    print("  TV Player proxy")
    print("  ---------------")
    print("  upstream : %s" % UPSTREAM)
    print("  TV'de aç : http://%s:%d/" % (ip, a.port))
    print("  Player'daki 'Sunucu adresi' alanına da aynı adresi yaz:")
    print("             http://%s:%d" % (ip, a.port))
    print("")
    if PRESET:
        print("  Ayar sayfaya gömüldü: televizyonda adresi açman yeterli.")
        print("")
    print("  Ayarı tarayıcıdan yapmak için: http://%s:%d/__setup" % (ip, a.port))
    print("")
    print("  Durdurmak için Ctrl+C")
    print("")

    ThreadingHTTPServer(("0.0.0.0", a.port), Handler).serve_forever()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  durduruldu")
