<?php
/**
 * Zilo WP Bridge — remote WP-CLI execution endpoint
 *
 * Place this file at: /var/www/html/zilo/wp-bridge.php
 *
 * On the server, set environment variable:
 *   WP_BRIDGE_SECRET=<your-strong-secret-here>
 *
 * In Apache VirtualHost or .htaccess, expose the env var to PHP:
 *   SetEnv WP_BRIDGE_SECRET your-strong-secret-here
 *
 * Render env vars needed:
 *   WP_BRIDGE_URL=https://wp.zilo.pro
 *   WP_BRIDGE_SECRET=<same-secret>
 */
declare(strict_types=1);

header('Content-Type: application/json');

// Only allow POST
if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    exit(json_encode(['error' => 'Method Not Allowed']));
}

// Verify secret key
$secret = getenv('WP_BRIDGE_SECRET') ?: '';
if (empty($secret)) {
    http_response_code(500);
    exit(json_encode(['error' => 'WP_BRIDGE_SECRET not configured on server']));
}

$provided_key = $_SERVER['HTTP_X_BRIDGE_KEY'] ?? '';
if (!hash_equals($secret, $provided_key)) {
    http_response_code(403);
    exit(json_encode(['error' => 'Forbidden']));
}

// Parse args from JSON body
$body = json_decode(file_get_contents('php://input'), true);
$args = $body['args'] ?? [];
$wp_url = $body['url'] ?? null;

if (empty($args) || !is_array($args)) {
    http_response_code(400);
    exit(json_encode(['error' => 'args array required']));
}

// Build WP-CLI command
$wp_path = getenv('WP_CLI_PATH') ?: '/var/www/html/zilo';
$cmd_parts = ['wp', '--allow-root', '--path=' . $wp_path];
if ($wp_url) {
    $cmd_parts[] = '--url=' . $wp_url;
}
$cmd_parts = array_merge($cmd_parts, $args);

// Escape all parts and execute
$escaped = implode(' ', array_map('escapeshellarg', $cmd_parts));
$output_lines = [];
$return_code = 0;
exec($escaped . ' 2>&1', $output_lines, $return_code);
$output = implode("\n", $output_lines);

echo json_encode([
    'returncode' => $return_code,
    'stdout' => $return_code === 0 ? $output : '',
    'stderr' => $return_code !== 0 ? $output : '',
]);
