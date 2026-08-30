#!/usr/bin/env node
/**
 * Publish an over-the-air update with a short, readable message.
 *
 * `eas update` prompts for a message and prefills it with the entire commit
 * body. Ours run well past the 1024-character limit, so the prompt arrives as
 * a wall of text and the message ends up truncated mid-word in the dashboard.
 * Pass the commit subject line instead, which also skips the prompt.
 *
 * Usage: node scripts/publish-update.js <channel>
 */
const { execFileSync } = require('node:child_process');

const channel = process.argv[2];
if (!channel) {
  console.error('Usage: node scripts/publish-update.js <channel>');
  process.exit(1);
}

let message;
try {
  message = execFileSync('git', ['log', '-1', '--pretty=%s'], {
    encoding: 'utf8',
  }).trim();
} catch {
  message = `Update ${channel}`;
}

// A dirty tree means the bundle does not match the commit the message names,
// so say so rather than labelling the update with a commit it isn't.
const dirty = execFileSync('git', ['status', '--porcelain'], { encoding: 'utf8' }).trim();
if (dirty) {
  message = `${message} (+ uncommitted changes)`;
}

console.log(`Publishing to "${channel}": ${message}\n`);

execFileSync(
  'eas',
  ['update', '--channel', channel, '--platform', 'android', '--message', message],
  { stdio: 'inherit', shell: true },
);
