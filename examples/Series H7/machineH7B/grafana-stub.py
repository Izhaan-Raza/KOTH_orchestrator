#!/usr/bin/env python3
"""
Grafana 8.3.0 CVE-2021-43798 Path Traversal Simulation
Vulnerable endpoint: GET /public/plugins/<plugin-id>/../../../../../../../<file>
"""
import http.server
import http.cookies
import os
import secrets
import subprocess
import sys
import urllib.parse

GRAFANA_ROOT = '/usr/share/grafana'
# Simulated plugin directory
PLUGINS_DIR = '/var/lib/grafana/plugins'
SESSIONS = {}


def has_valid_session(handler):
    cookie_header = handler.headers.get('Cookie', '')
    cookie = http.cookies.SimpleCookie()
    cookie.load(cookie_header)
    token = cookie.get('grafana_session')
    return token is not None and token.value in SESSIONS


def load_admin_creds():
    username = 'admin'
    password = 'admin'
    if os.path.exists('/etc/grafana/grafana.ini'):
        with open('/etc/grafana/grafana.ini', 'r', encoding='utf-8', errors='ignore') as fh:
            for line in fh:
                if line.startswith('admin_user'):
                    username = line.split('=', 1)[1].strip()
                if line.startswith('admin_password'):
                    password = line.split('=', 1)[1].strip()
    return username, password

class GrafanaHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        path = urllib.parse.unquote(self.path)

        # CVE-2021-43798: Path traversal via plugin endpoint
        if '/public/plugins/' in path:
            # Extract the traversal path after plugin name
            plugin_part = path.split('/public/plugins/', 1)[1]
            parts = plugin_part.split('/', 1)
            if len(parts) > 1:
                traversal = parts[1]
                # Normalize path traversal
                real_path = os.path.normpath('/' + traversal)
                try:
                    if os.path.isfile(real_path):
                        with open(real_path, 'rb') as f:
                            content = f.read()
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/octet-stream')
                        self.end_headers()
                        self.wfile.write(content)
                        return
                    else:
                        self.send_error(404, f"File not found: {real_path}")
                        return
                except PermissionError:
                    self.send_error(403, "Permission denied")
                    return
                except Exception as e:
                    self.send_error(500, str(e))
                    return

        if path.startswith('/api/admin/exec'):
            if not has_valid_session(self):
                self.send_error(403, 'Login required')
                return
            cmd = urllib.parse.parse_qs(urllib.parse.urlparse(path).query).get('cmd', ['id'])[0]
            try:
                output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, timeout=10).decode()
            except subprocess.CalledProcessError as exc:
                output = exc.output.decode() if isinstance(exc.output, bytes) else str(exc.output)
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(output.encode())
            return

        # Default Grafana login page
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(b'''
<html><head><title>Grafana</title>
<style>body{background:#111;color:#eee;font-family:sans-serif;padding:2em;}
.panel{background:#1f1f1f;padding:2em;max-width:400px;margin:auto;border-radius:8px;}
input{background:#2c2c2c;border:1px solid #444;color:#eee;padding:8px;width:100%;margin:4px 0;box-sizing:border-box;}
button{background:#f05a28;border:none;color:white;padding:10px;width:100%;cursor:pointer;border-radius:4px;}</style>
</head><body>
<div class="panel">
<h2>Grafana Login</h2>
<form method=POST action=/login>
<input type=text name=user placeholder="Email or username" value="admin"><br>
<input type=password name=password placeholder="Password"><br>
<button>Log in</button>
</form>
</div>
<p style="text-align:center;color:#666">Grafana v8.3.0 | <a href="/public/plugins/text/../../../../../../../etc/grafana/grafana.ini" style="color:#666">plugins</a></p>
</body></html>''')

    def do_POST(self):
        if self.path != '/login':
            self.send_error(404, 'Not found')
            return

        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode('utf-8', errors='ignore')
        params = urllib.parse.parse_qs(body)
        username, password = load_admin_creds()
        if params.get('user', [''])[0] == username and params.get('password', [''])[0] == password:
            token = secrets.token_hex(16)
            SESSIONS[token] = username
            self.send_response(302)
            self.send_header('Set-Cookie', f'grafana_session={token}; Path=/')
            self.send_header('Location', '/')
            self.end_headers()
            return

        self.send_response(403)
        self.end_headers()
        self.wfile.write(b'Invalid credentials')

    def log_message(self, fmt, *args):
        pass

if __name__ == '__main__':
    os.makedirs(PLUGINS_DIR, exist_ok=True)
    server = http.server.HTTPServer(('0.0.0.0', 3000), GrafanaHandler)
    print('Grafana 8.3.0 stub running on port 3000 (CVE-2021-43798)')
    sys.stdout.flush()
    server.serve_forever()
