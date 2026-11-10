import { mkdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { defineConfig, type Plugin } from 'vite';

/** Dev only: `demo.shot('name')` in the console posts a full-resolution frame here and it lands in ./shots. */
function shots(): Plugin {
  return {
    name: 'homestead-shots',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use('/__shot', (req, res) => {
        if (req.method !== 'POST') {
          res.statusCode = 405;
          res.end();
          return;
        }
        const name = (new URL(req.url ?? '/', 'http://x').searchParams.get('name') ?? 'shot').replace(/[^a-z0-9_-]/gi, '_');
        const chunks: Buffer[] = [];
        req.on('data', (c: Buffer) => chunks.push(c));
        req.on('end', () => {
          const dir = resolve(server.config.root, 'shots');
          mkdirSync(dir, { recursive: true });
          const body = Buffer.concat(chunks).toString('utf8');
          writeFileSync(resolve(dir, `${name}.jpg`), Buffer.from(body.replace(/^data:image\/\w+;base64,/, ''), 'base64'));
          res.end('ok');
        });
      });
    },
  };
}

export default defineConfig({
  base: './',
  plugins: [shots()],
  server: { port: Number(process.env.PORT) || 5183, strictPort: true, host: '127.0.0.1' },
  build: { target: 'es2022', chunkSizeWarningLimit: 1500 },
});
