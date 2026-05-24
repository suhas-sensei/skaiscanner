import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('..', import.meta.url));
const envPath = join(root, '.env');

if (existsSync(envPath)) {
  process.loadEnvFile(envPath);
}
