FROM node:22-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .
RUN npm run build -- --configuration production

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY nginx-locations.conf /etc/nginx/snippets/eventhub-locations.conf
COPY certs/server.crt /etc/nginx/certs/server.crt
COPY certs/server.key /etc/nginx/certs/server.key
COPY --from=build /app/dist/eventhub-frontend/browser /usr/share/nginx/html

EXPOSE 80 443
