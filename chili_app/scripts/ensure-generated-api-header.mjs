import { readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'

const target = resolve(process.cwd(), 'src/lib/api/schema.ts')
const header = `// Generated from backend OpenAPI. Do not edit by hand.
// Run: npm run codegen:api

`

const current = readFileSync(target, 'utf8')
const withoutExistingHeader = current.replace(
  /^\/\/ Generated from backend OpenAPI\. Do not edit by hand\.\n\/\/ Run: npm run codegen:api\n\n/,
  '',
)
writeFileSync(target, `${header}${withoutExistingHeader}`, 'utf8')
