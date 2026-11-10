# syntax=docker/dockerfile:1
# ---------------------------------------------------------------- Build stage --
FROM node:22-alpine AS builder

WORKDIR /build

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
RUN npm run build

# -------------------------------------------------------------- Runtime stage --
FROM nginx:1.30-alpine AS runtime

# Remove default nginx configs
RUN rm -rf /etc/nginx/conf.d/* /usr/share/nginx/html/*

COPY nginx.conf /etc/nginx/conf.d/default.conf
# .inc is not matched by the conf.d/*.conf include; nginx.conf includes it explicitly.
COPY security-headers.inc /etc/nginx/conf.d/security-headers.inc
COPY server-common.inc /etc/nginx/conf.d/server-common.inc
# http-level maps (trusted TLS proxy, HSTS); picked up by the conf.d/*.conf include.
COPY proxy-trust.conf /etc/nginx/conf.d/00-proxy-trust.conf
COPY --from=builder /build/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1/healthz || exit 1

CMD ["nginx", "-g", "daemon off;"]
