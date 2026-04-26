const express = require('express');
const { execSync } = require('child_process');

const app = express();
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Internal admin API - runs as root, accessible only internally
// No authentication - vulnerable to SSRF -> RCE chain

app.get('/api', (req, res) => {
    res.json({
        service: 'Internal Admin API',
        version: '1.0',
        endpoints: ['/api/status', '/api/exec'],
        note: 'Internal use only'
    });
});

app.get('/api/status', (req, res) => {
    res.json({ status: 'running', uptime: process.uptime() });
});

// VULNERABLE: Unauthenticated command execution endpoint running as root
app.get('/api/exec', (req, res) => {
    const cmd = req.query.cmd;
    if (!cmd) {
        return res.json({ error: 'No command specified. Use ?cmd=<command>' });
    }
    try {
        const output = execSync(cmd, { encoding: 'utf8', timeout: 10000 });
        res.json({ output: output });
    } catch (e) {
        res.json({ error: e.message, stderr: e.stderr });
    }
});

app.listen(1337, '127.0.0.1', () => {
    console.log('Internal Admin API listening on 127.0.0.1:1337 (root)');
});
