<?php
// Vulnerable shop application - SQL Injection in product search
$host = 'localhost';
$db   = 'shopdb';
$user = 'appuser';
$pass = 'app123';

$conn = new mysqli($host, $user, $pass, $db);
if ($conn->connect_error) {
    // Show error to assist exploitation
    die("Connection failed: " . $conn->connect_error);
}

$result_html = '';
$search = '';

if (isset($_GET['search'])) {
    $search = $_GET['search']; // NO sanitization - intentionally vulnerable
    // VULNERABLE: Direct string interpolation -> SQL Injection
    $query = "SELECT id, name, price, description FROM products WHERE name LIKE '%" . $search . "%'";
    $result = $conn->query($query);
    if ($result) {
        while ($row = $result->fetch_assoc()) {
            $result_html .= "<tr><td>{$row['id']}</td><td>{$row['name']}</td><td>\${$row['price']}</td><td>{$row['description']}</td></tr>";
        }
    } else {
        $result_html = "<tr><td colspan='4'>Error: " . $conn->error . "</td></tr>";
    }
}
?>
<!DOCTYPE html>
<html>
<head><title>KoTH Shop</title>
<style>body{font-family:Arial,sans-serif;background:#1a1a2e;color:#eee;padding:2em;}
input{padding:8px;width:300px;} button{padding:8px 16px;background:#0f3460;color:white;border:none;cursor:pointer;}
table{width:100%;border-collapse:collapse;margin-top:1em;}
th,td{border:1px solid #444;padding:8px;}th{background:#0f3460;}</style>
</head>
<body>
<h1>Product Search</h1>
<form method="GET">
    <input type="text" name="search" value="<?= htmlspecialchars($search) ?>" placeholder="Search products...">
    <button type="submit">Search</button>
</form>
<?php if ($search): ?>
<h2>Results for: <?= htmlspecialchars($search) ?></h2>
<table><tr><th>ID</th><th>Name</th><th>Price</th><th>Description</th></tr>
<?= $result_html ?>
</table>
<!-- Hint: try injecting into the search parameter -->
<?php endif; ?>
</body>
</html>
