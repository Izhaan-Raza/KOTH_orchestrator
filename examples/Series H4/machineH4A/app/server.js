const express = require('express');
const serialize = require('node-serialize');

const app = express();
app.use(express.urlencoded({ extended: true }));
app.use(express.json());

// Vulnerable deserialization endpoint
// Attack: send a serialized object with IIFE function to /profile via POST
// node-serialize 0.0.4 is vulnerable to RCE via IIFE in serialized objects
app.post('/profile', (req, res) => {
    try {
        // Intentionally vulnerable: deserializes user-controlled input directly
        const profile = serialize.unserialize(req.body.profile);
        res.json({ status: 'ok', data: profile });
    } catch(e) {
        res.status(500).json({ error: e.message });
    }
});

app.get('/', (req, res) => {
    res.send(`
        <html>
        <head><title>KoTH Profile App</title></head>
        <body style="background:#1a1a2e;color:#eee;font-family:monospace;padding:2em">
        <h1>User Profile Service</h1>
        <p>POST to /profile with JSON body: <code>{"profile": "&lt;serialized_data&gt;"}</code></p>
        <p>Example: <code>curl -X POST http://target:3000/profile -H 'Content-Type: application/json' -d '{"profile":"{\"user\":\"admin\"}"}'</code></p>
        <hr>
        <p style="color:#666">Backup files available at /var/backups/</p>
        </body>
        </html>
    `);
});

app.listen(3000, '0.0.0.0', () => {
    console.log('KoTH Profile Service running on port 3000');
});
