# Deployment Instructions for GitHub Pages (GovCloud)

## Repository Information
- **GitHub URL**: https://github.uskgc.com/Fed-Incubator/Crushing-Fraud-XAI
- **Deployed Site**: https://fed-incubator.github.uskgc.com/Crushing-Fraud-XAI/

## Setup (One-time Configuration)

### 1. Enable GitHub Pages in Repository Settings

1. Go to: https://github.uskgc.com/Fed-Incubator/Crushing-Fraud-XAI/settings/pages
2. Under **Source**, select: **GitHub Actions**
3. Save the configuration

### 2. Push Code to GitHub

```bash
# Navigate to project root
cd "/Users/ningwang1/Documents/Capabitility Development/AI Program Integrity/Crushing Fraud XAI"

# Initialize git repository (if not already done)
git init

# Add remote (if not already done)
git remote add origin https://github.uskgc.com/Fed-Incubator/Crushing-Fraud-XAI.git

# Stage all files
git add .

# Commit
git commit -m "Add fraud detection UI with GitHub Pages deployment"

# Push to main branch
git push -u origin main
```

## Automatic Deployment

The GitHub Actions workflow (`.github/workflows/deploy.yml`) will automatically:
- Build the React app when you push to the `main` branch
- Deploy to GitHub Pages

**Trigger automatic deployment:**
```bash
git add .
git commit -m "Update UI"
git push
```

Check deployment status at:
https://github.uskgc.com/Fed-Incubator/Crushing-Fraud-XAI/actions

## Manual Local Build

Test the production build locally before deploying:

```bash
cd "code-starters/ui"

# Install dependencies
npm install

# Build for production
npm run build

# Preview the production build
npm run preview
```

The preview server will show exactly what will be deployed to GitHub Pages.

## Configuration Files

### `vite.config.js`
- **base**: `/Crushing-Fraud-XAI/` - Required for GitHub Pages project sites
- **outDir**: `dist` - Build output directory

### `.github/workflows/deploy.yml`
- Automatically builds and deploys on push to `main`
- Can also be triggered manually via GitHub Actions UI

## Troubleshooting

### Build Fails
- Check GitHub Actions logs at: https://github.uskgc.com/Fed-Incubator/Crushing-Fraud-XAI/actions
- Verify `package-lock.json` is committed
- Run `npm run build` locally to test

### Page Not Loading
- Ensure GitHub Pages is enabled in repository settings
- Verify the source is set to "GitHub Actions"
- Check that the base path in `vite.config.js` matches repository name

### Assets Not Loading (404 errors)
- Verify `base: '/Crushing-Fraud-XAI/'` in `vite.config.js`
- Clear browser cache
- Check browser console for specific errors

## GovCloud Considerations

GitHub Enterprise on GovCloud (github.uskgc.com) may have:
- Different authentication requirements
- Specific security policies
- Network access restrictions

Ensure your GovCloud environment supports GitHub Pages and Actions.

## Updating the Deployment

After making code changes:

```bash
cd "/Users/ningwang1/Documents/Capabitility Development/AI Program Integrity/Crushing Fraud XAI"
git add .
git commit -m "Describe your changes"
git push
```

The site will rebuild and deploy automatically within 2-5 minutes.

## Accessing the Deployed Site

Once deployed, access your fraud detection dashboard at:
**https://fed-incubator.github.uskgc.com/Crushing-Fraud-XAI/**
