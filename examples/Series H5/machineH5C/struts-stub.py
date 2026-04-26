#!/usr/bin/env python3
"""
Apache Struts 2 CVE-2017-5638 (Jakarta Multipart Parser) Simulation
RCE via malicious Content-Type header using OGNL injection
"""
import http.server
import subprocess
import sys
import re

class StrutsHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(b'''
<html><head><title>Struts2 Showcase</title>
<style>body{background:#1a1a3e;color:#eee;font-family:sans-serif;padding:2em;}</style>
</head><body>
<h1>Apache Struts 2 Showcase</h1>
<form method="POST" action="/login.action" enctype="multipart/form-data">
    <p>Username: <input name="username" type="text"></p>
    <p>Password: <input name="password" type="password"></p>
    <p>Document: <input name="file" type="file"></p>
    <button>Login</button>
</form>
<p style="color:#888">Struts 2.3.32 - Content-Type: multipart/form-data</p>
</body></html>''')

    def do_POST(self):
        content_type = self.headers.get('Content-Type', '')

        # CVE-2017-5638: RCE via OGNL in Content-Type header
        # Pattern: Content-Type: %{(#_='multipart/form-data')...(#[cmd])}
        if '%{' in content_type or '${' in content_type:
            # Extract the OGNL expression / simulated command
            # Real exploit uses: %{(#_='multipart/form-data').(#dm=@ognl.OgnlContext@DEFAULT_MEMBER_ACCESS)...}
            cmd_match = re.search(r'Runtime\(\)\.exec\((?:new String\[\]\{)?["\'`]?([^"\'}\]]+)["\'`]?\}?\)', content_type)
            if cmd_match:
                cmd = cmd_match.group(1)
            else:
                # Simpler extraction for CTF purposes
                cmd_match = re.search(r'exec\(["\'](.+?)["\']\)', content_type)
                cmd = cmd_match.group(1) if cmd_match else None

            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()

            if cmd:
                try:
                    output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT,
                                                     timeout=10, encoding='utf-8')
                    self.wfile.write(f'<pre>{output}</pre>'.encode())
                except Exception as e:
                    self.wfile.write(f'<pre>Error: {e}</pre>'.encode())
            else:
                self.wfile.write(b'<pre>OGNL injection detected but no command extracted</pre>')
            return

        length = int(self.headers.get('Content-Length', 0))
        _ = self.rfile.read(length)
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(b'<html><body><h1>Login Failed</h1></body></html>')

    def log_message(self, fmt, *args):
        pass

if __name__ == '__main__':
    server = http.server.HTTPServer(('0.0.0.0', 8080), StrutsHandler)
    print('Struts2 stub running on port 8080 (CVE-2017-5638)')
    sys.stdout.flush()
    server.serve_forever()
