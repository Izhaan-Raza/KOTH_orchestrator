<?php
session_start();
if (!isset($_SESSION['logged_in'])) {
    header("Location: index.php");
    exit();
}

$cmd_output = '';
if (isset($_POST['dir'])) {
    // VULNERABLE: Command Injection in the authenticated panel
    $dir = $_POST['dir'];
    $cmd_output = shell_exec("ls -la " . $dir);
}
?>
<!DOCTYPE html>
<html>
<head><title>Admin Dashboard</title></head>
<body style="background:#111; color:#0f0; font-family:monospace; padding: 50px;">
    <h2>Welcome Admin</h2>
    <p>System Utility: Directory Lister</p>
    <form method="POST">
        Path: <input type="text" name="dir" value=".">
        <input type="submit" value="Execute">
    </form>
    <hr>
    <pre><?= htmlspecialchars($cmd_output) ?></pre>
</body>
</html>