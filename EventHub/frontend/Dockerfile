FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
# Reproducible install from the lockfile.
RUN npm ci --no-audit --no-fund

COPY . .
RUN npm run build -- --configuration production

FROM nginx:1.27-alpine

RUN apk add --no-cache openssl

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY nginx-locations.conf /etc/nginx/snippets/eventhub-locations.conf
COPY nginx-security-headers.conf /etc/nginx/snippets/security-headers.conf
# TLS keys are never baked into the image: mount them at /etc/nginx/certs
# (docker-compose does) or let this hook create a self-signed pair at start.
COPY docker/10-self-signed-cert.sh /docker-entrypoint.d/10-self-signed-cert.sh
COPY --from=build /app/dist/eventhub-frontend/browser /usr/share/nginx/html

EXPOSE 80 443
