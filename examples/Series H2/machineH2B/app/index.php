<?php
mysqli_report(MYSQLI_REPORT_OFF);
session_start();
// Force TCP connection to bypass UNIX socket permissions
$conn = new mysqli('127.0.0.1', 'appuser', 'app123', 'admin_panel');

$error = '';
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $user = $_POST['username'];
    $pass = $_POST['password'];

    // VULNERABLE: Direct string interpolation
    $query = "SELECT * FROM users WHERE username = '$user' AND password = '$pass'";
    $result = $conn->query($query);

    if ($result && $result->num_rows > 0) {
        $_SESSION['logged_in'] = true;
        header("Location: admin.php");
        exit();
    } else {
        $error = "Invalid credentials!";
    }
}
?>
<!DOCTYPE html>
<html>
<head><title>Admin Portal</title></head>
<body style="background:#111; color:#0f0; font-family:monospace; padding: 50px;">
    <h2>KoTH Internal Dashboard</h2>
    <form method="POST">
        Username: <input type="text" name="username"><br><br>
        Password: <input type="password" name="password"><br><br>
        <input type="submit" value="Login">
    </form>
    <p style="color:red;"><?= $error ?></p>
</body>
</html>