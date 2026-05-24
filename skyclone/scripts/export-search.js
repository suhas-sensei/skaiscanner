import '../src/env.js';
import { runFlightSearch } from '../src/searchEngine.js';

function readArgs(argv) {
  const args = {};
  for (let index = 2; index < argv.length; index += 1) {
    const key = argv[index];
    if (!key.startsWith('--')) continue;
    args[key.slice(2)] = argv[index + 1];
    index += 1;
  }
  return args;
}

const args = readArgs(process.argv);
const query = {
  origin: String(args.origin || '').toUpperCase(),
  destination: String(args.destination || '').toUpperCase(),
  date: args.date,
  returnDate: args.returnDate || null,
  passengers: Number(args.passengers || 1)
};

if (!query.origin || !query.destination || !query.date) {
  console.error('Usage: node scripts/export-search.js --origin DEL --destination BOM --date YYYY-MM-DD [--returnDate YYYY-MM-DD]');
  process.exit(2);
}

const result = await runFlightSearch(query);
console.log(JSON.stringify({ query, ...result }));
