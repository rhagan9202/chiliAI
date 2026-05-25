# Integrity AI - UI Code Starter

React-based UI prototype for the Program Integrity XAI Accelerator queue/evidence/feedback workflow.

## Running with Docker (No Node.js installation needed)

### Step 1: Install dependencies
```bash
docker run --rm -v "$PWD:/app" -w /app node:20-alpine npm install
```

### Step 2: Start development server
```bash
docker run --rm -p 3000:3000 -v "$PWD:/app" -w /app node:20-alpine npm run dev
```

### Step 3: Open in browser
Visit: http://localhost:3000

## Running locally (if Node.js is installed)

```bash
npm install
npm run dev
```

## Build for production

```bash
docker run --rm -v "$PWD:/app" -w /app node:20-alpine npm run build
```

The built files will be in the `dist/` folder.
