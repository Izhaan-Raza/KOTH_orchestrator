#!/usr/bin/env python3
"""
Laravel CVE-2021-3129 (Ignition Debug Mode RCE) Simulation
Vulnerable when APP_DEBUG=true in Laravel < 8.4.3
Attack: POST to /_ignition/execute-solution with a Log solution that uses phar deserialization
"""
import http.server
import json
import subprocess
import sys
import os

# Simulate the Laravel environment
LARAVEL_HTML = b"""
<!DOCTYPE html>
<html>
<head><title>Laravel - KoTH App</title>
<style>
body { background: #f8f9fa; font-family: sans-serif; }
.container { max-width: 1200px; margin: auto; padding: 2em; }
.error { background: #fff; border: 1px solid #dee2e6; padding: 2em; border-radius: 8px; }
.badge { background: #dc3545; color: white; padding: 2px 8px; border-radius: 12px; font-size: 0.8em; }
</style>
</head>
<body><div class="container">
<h1>Laravel <span class="badge">DEBUG MODE</span></h1>
<div class="error">
<h2>Welcome to KoTH Laravel App</h2>
<p>The application is running in <strong>debug mode</strong> (APP_DEBUG=true).</p>
<p>Framework: <strong>Laravel 8.4.2</strong></p>
<p>Ignition version: <strong>2.5.1</strong></p>
<hr>
<p>Endpoint: <code>POST /_ignition/execute-solution</code></p>
<p>Required body:</p>
<pre>{"solution": "Facade\\\\Ignition\\\\Solutions\\\\MakeViewVariableOptionalSolution",
"parameters": {"variableName": "username", "viewFile": "php://filter/..."}}</pre>
<p style="color:#666">CVE-2021-3129: Phar deserialization via PHP filter chains</p>
</div>
</div></body></html>
"""

class LaravelHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.send_header('X-Powered-By', 'PHP/8.0.2')
        self.end_headers()
        self.wfile.write(LARAVEL_HTML)

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()

        if b'_ignition/execute-solution' in self.path.encode() or '/_ignition' in self.path:
            try:
                data = json.loads(body)
                solution = data.get('solution', '')
                params = data.get('parameters', {})

                # Simulate the CVE-2021-3129 phar deserialization RCE
                # The viewFile parameter is used to trigger phar:// deserialization
                view_file = params.get('viewFile', '')
                if 'convert.base64-decode' in view_file or 'phar://' in view_file:
                    # In reality this triggers RCE via phar deserialization
                    # For CTF we simulate it by executing a command if present
                    cmd = params.get('cmd', params.get('command', ''))
                    if cmd:
                        output = subprocess.check_output(cmd, shell=True,
                                                        stderr=subprocess.STDOUT,
                                                        timeout=10, encoding='utf-8')
                        self.wfile.write(json.dumps({'output': output}).encode())
                        return

                self.wfile.write(json.dumps({
                    'solution': solution,
                    'output': 'Solution executed (simulate: use phar deserialization chain)'
                }).encode())
            except Exception as e:
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        else:
            self.wfile.write(json.dumps({'message': 'Not found'}).encode())

    def log_message(self, fmt, *args):
        pass

if __name__ == '__main__':
    server = http.server.HTTPServer(('0.0.0.0', 8000), LaravelHandler)
    print('Laravel 8.4.2 debug stub running on port 8000 (CVE-2021-3129)')
    sys.stdout.flush()
    server.serve_forever()
