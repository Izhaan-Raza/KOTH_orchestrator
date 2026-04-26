from flask import Flask, request, render_template_string

app = Flask(__name__)

INDEX_PAGE = """
<!DOCTYPE html>
<html>
<head>
<title>KoTH Greeting Service</title>
<style>
body { background: #0d0d0d; color: #39ff14; font-family: 'Courier New', monospace; padding: 2em; }
input { background: #1a1a1a; border: 1px solid #39ff14; color: #39ff14; padding: 8px; width: 300px; }
button { background: #001a00; border: 1px solid #39ff14; color: #39ff14; padding: 8px 16px; cursor: pointer; }
.output { background: #111; border: 1px solid #333; padding: 1em; margin-top: 1em; }
</style>
</head>
<body>
<h1>🖥️ KoTH Greeting Service</h1>
<form method="GET">
    <input type="text" name="name" placeholder="Enter your name..." value="{{ name_raw }}">
    <button type="submit">Greet Me!</button>
</form>
{% if greeting %}
<div class="output">
    <h2>{{ greeting }}</h2>
</div>
{% endif %}
<p style="color:#333">Powered by Jinja2 Template Engine</p>
<!-- Hint: What happens if your name contains {{ 7*7 }}? -->
</body>
</html>
"""

@app.route('/', methods=['GET'])
def index():
    name = request.args.get('name', '')
    name_raw = name

    if name:
        # VULNERABLE: Direct template string rendering with user input
        # This allows SSTI - try: {{7*7}}, {{config}}, {{''.__class__.__mro__[1].__subclasses__()}}
        template = f"Hello, {name}! Welcome to KoTH."
        try:
            # The vulnerability: using render_template_string with unsanitized input
            greeting = render_template_string(template)
        except Exception as e:
            greeting = f"Template error: {str(e)}"
    else:
        greeting = None

    return render_template_string(INDEX_PAGE, greeting=greeting, name_raw=name_raw)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
