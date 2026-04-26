<?php
// phpMyAdmin stub - simulates the login/SQL execution interface
session_start();

$logged_in = isset($_SESSION['loggedin']) && $_SESSION['loggedin'];

// Auto-login since root has no password
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['pma_username'])) {
    if ($_POST['pma_username'] === 'root' && $_POST['pma_password'] === '') {
        $_SESSION['loggedin'] = true;
        $logged_in = true;
    }
}

// SQL execution
$result_html = '';
if ($logged_in && isset($_POST['sql'])) {
    $conn = new mysqli('localhost', 'root', '');
    if (!$conn->connect_error) {
        $multi = $conn->multi_query($_POST['sql']);
        do {
            if ($res = $conn->store_result()) {
                $result_html .= '<table border=1 style="border-collapse:collapse">';
                $fields = $res->fetch_fields();
                $result_html .= '<tr>';
                foreach ($fields as $f) $result_html .= '<th>' . $f->name . '</th>';
                $result_html .= '</tr>';
                while ($row = $res->fetch_row()) {
                    $result_html .= '<tr>';
                    foreach ($row as $v) $result_html .= '<td>' . htmlspecialchars((string)$v) . '</td>';
                    $result_html .= '</tr>';
                }
                $result_html .= '</table>';
                $res->free();
            }
        } while ($conn->more_results() && $conn->next_result());
        if ($conn->error) $result_html .= '<p style="color:red">Error: ' . $conn->error . '</p>';
    }
}
?>
<!DOCTYPE html>
<html>
<head><title>phpMyAdmin</title>
<style>body{background:#f5f5f5;font-family:sans-serif;padding:1em;}
.panel{background:white;padding:1.5em;border-radius:4px;box-shadow:0 1px 3px rgba(0,0,0,.2);}
input,textarea{padding:6px;border:1px solid #ccc;} button{background:#d33;color:white;border:none;padding:8px 16px;cursor:pointer;}
table{font-size:0.85em;margin-top:1em;}th{background:#6c757d;color:white;padding:4px 8px;}td{padding:4px 8px;border:1px solid #ddd;}</style>
</head>
<body>
<?php if (!$logged_in): ?>
<div class="panel" style="max-width:400px;margin:auto;margin-top:5em">
<h2>phpMyAdmin</h2>
<form method=POST>
<p>Username: <input name=pma_username value="root"></p>
<p>Password: <input type=password name=pma_password placeholder="(leave blank for root)"></p>
<button>Go</button>
</form>
</div>
<?php else: ?>
<div class="panel">
<h2>phpMyAdmin - SQL Console (root@localhost)</h2>
<form method=POST>
<textarea name=sql rows=8 style="width:100%;font-family:monospace"><?= htmlspecialchars($_POST['sql'] ?? 'SELECT * FROM mysql.user LIMIT 5;') ?></textarea><br>
<button type=submit>Execute</button>
</form>
<?= $result_html ?>
<p><small>Tip: <code>SELECT sys_exec('id');</code> after loading the UDF</small></p>
</div>
<?php endif; ?>
</body>
</html>
