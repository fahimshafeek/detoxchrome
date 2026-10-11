const { spawn } = require('child_process');

const p = spawn('npx', ['-y', 'shadcn-svelte@latest', 'init'], {
  stdio: ['pipe', 'pipe', 'pipe']
});

let outputBuffer = '';
let timeoutId = null;

p.stdout.on('data', (data) => {
  const output = data.toString();
  process.stdout.write(output);
  outputBuffer += output;

  if (timeoutId) clearTimeout(timeoutId);

  timeoutId = setTimeout(() => {
    if (outputBuffer.includes('?')) {
      p.stdin.write('\r');
      outputBuffer = '';
    }
  }, 500); // wait 500ms after output stabilizes
});

p.stderr.on('data', (data) => {
  console.error(data.toString());
});

p.on('close', (code) => {
  console.log(`child process exited with code ${code}`);
});
