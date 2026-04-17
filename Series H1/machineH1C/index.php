<!DOCTYPE html>
<html>
<head><title>Network Diagnostics</title></head>
<body style="font-family: monospace; background: #222; color: #0f0; padding: 20px;">
    <h2>KoTH Ping Diagnostics</h2>
    <form method="GET">
        <label>IP Address to Ping:</label>
        <input type="text" name="ip" value="127.0.0.1">
        <input type="submit" value="Execute">
    </form>
    <hr>
    <pre>
<?php
if(isset($_GET['ip'])) {
    // VULNERABILITY: Blindly concatenating user input into a shell command
    $cmd = "ping -c 1 " . $_GET['ip'];
    echo "Running: " . htmlspecialchars($cmd) . "\n\n";
    echo shell_exec($cmd);
}
?>
    </pre>
</body>
</html>