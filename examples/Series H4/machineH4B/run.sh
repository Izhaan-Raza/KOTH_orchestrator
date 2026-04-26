#!/bin/bash
set -e

cat <<'PY' > /tmp/spring4shell_stub.py
import http.server
import subprocess
import sys
import urllib.parse


INDEX = b"""<html><body>
<h1>Spring MVC Demo App</h1>
<p>Spring Framework 5.3.17 (CVE-2022-22965 - Spring4Shell)</p>
<form method='POST' action='/greeting'>
  <input name='name' value='World'>
  <button>Submit</button>
</form>
<p>Exploit hint: submit the class.module.classLoader pipeline fields with a cmd parameter.</p>
</body></html>"""


class VulnerableHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(INDEX)

    def do_POST(self):
        length = int(self.headers.get('Content-Length', '0'))
        body = self.rfile.read(length).decode('utf-8', errors='ignore')
        params = urllib.parse.parse_qs(body)

        if 'class.module.classLoader' in body:
            cmd = params.get('cmd', ['id'])[0]
            try:
                output = subprocess.check_output(
                    cmd,
                    shell=True,
                    stderr=subprocess.STDOUT,
                    timeout=10,
                    text=True,
                )
            except subprocess.CalledProcessError as exc:
                output = exc.output
            except Exception as exc:
                output = str(exc)

            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(output.encode())
            return

        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'Hello from Spring MVC')

    def log_message(self, fmt, *args):
        pass


server = http.server.ThreadingHTTPServer(('0.0.0.0', 8080), VulnerableHandler)
print('Spring4Shell stub running on :8080 as springuser')
sys.stdout.flush()
server.serve_forever()
PY

chown springuser:springuser /tmp/spring4shell_stub.py
exec su -s /bin/bash springuser -c 'python3 /tmp/spring4shell_stub.py'
