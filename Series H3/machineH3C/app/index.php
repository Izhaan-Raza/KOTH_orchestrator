<?php
// Simple login app - credentials leaked via .git history
$valid_user = 'admin';
$valid_pass = 'koth_admin_2024'; // Same as in git history

$msg = '';
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    if ($_POST['username'] === $valid_user && $_POST['password'] === $valid_pass) {
        $msg = '<p style="color:lime">Login successful! Welcome, admin.</p>';
        // RCE via admin panel
        if (isset($_POST['cmd'])) {
            $output = shell_exec($_POST['cmd']);
            $msg .= '<pre>' . htmlspecialchars($output) . '</pre>';
        }
    } else {
        $msg = '<p style="color:red">Invalid credentials.</p>';
    }
}
?>
<!DOCTYPE html>
<html>
<head><title>KoTH Admin Panel</title>
<style>body{font-family:monospace;background:#0d0d0d;color:#00ff00;padding:2em;}
input{background:#1a1a1a;color:#00ff00;border:1px solid #00ff00;padding:6px;margin:4px;}
button{background:#003300;color:#00ff00;border:1px solid #00ff00;padding:6px 12px;cursor:pointer;}
</style></head>
<body>
<h1>Admin Login</h1>
<?= $msg ?>
<form method="POST">
  <input type="text" name="username" placeholder="Username"><br>
  <input type="password" name="password" placeholder="Password"><br>
  <button type="submit">Login</button>
</form>
</body>
</html>
