<?php
// SSRF vulnerable endpoint - fetches a URL provided by the user
$url = '';
$content = '';
$error = '';

if (isset($_GET['url'])) {
    $url = $_GET['url'];
    // VULNERABLE: No SSRF protection - allows fetching internal services
    $ch = curl_init($url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_FOLLOWLOCATION, true);
    curl_setopt($ch, CURLOPT_TIMEOUT, 5);
    // Allow internal network access (no restriction on IP)
    $content = curl_exec($ch);
    if (curl_error($ch)) {
        $error = curl_error($ch);
    }
    curl_close($ch);
}
?>
<!DOCTYPE html>
<html>
<head><title>KoTH URL Fetcher</title>
<style>
body{background:#0d1117;color:#c9d1d9;font-family:'Courier New',monospace;padding:2em;}
input{background:#161b22;border:1px solid #30363d;color:#c9d1d9;padding:8px;width:400px;}
button{background:#238636;color:white;border:none;padding:8px 16px;cursor:pointer;}
pre{background:#161b22;border:1px solid #30363d;padding:1em;white-space:pre-wrap;word-break:break-all;}
.hint{color:#8b949e;font-size:0.85em;}
</style>
</head>
<body>
<h1>🌐 URL Content Fetcher</h1>
<p>Enter a URL to fetch its content:</p>
<form method="GET">
    <input type="text" name="url" value="<?= htmlspecialchars($url) ?>" placeholder="http://example.com">
    <button type="submit">Fetch</button>
</form>
<p class="hint">Try fetching http://example.com or any other URL...</p>

<?php if ($content): ?>
<h2>Response from: <?= htmlspecialchars($url) ?></h2>
<pre><?= htmlspecialchars($content) ?></pre>
<?php elseif ($error): ?>
<p style="color:#f85149">Error: <?= htmlspecialchars($error) ?></p>
<?php endif; ?>

<!-- Developer note: Internal API at http://127.0.0.1:1337/api - do not expose -->
</body>
</html>
