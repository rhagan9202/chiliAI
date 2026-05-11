# ---- build stage ----
FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json* ./
# `npm ci` would be strictly reproducible, but the inherited lockfile has
# malformed flags on optional platform-specific esbuild binaries (each is
# tagged `extraneous` rather than `optional`, so npm ci tries to install
# the aix-ppc64 binary on linux/x64 and fails with EBADPLATFORM). Fall back
# to `npm install` so dev builds work; tightening to `npm ci` should land
# alongside a regenerated lockfile in a follow-up.
RUN npm install --no-audit --no-fund

COPY . .
RUN npm run build

# ---- runtime stage ----
FROM nginx:alpine AS runtime

# Copy built SPA assets
COPY --from=build /app/dist /usr/share/nginx/html

# Copy custom nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -qO- http://localhost:80/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
