# Multi-stage: Node builds the Angular bundle, nginx serves it and
# reverse-proxies /api to the backend service.

FROM node:22-alpine AS build
WORKDIR /src

COPY package*.json ./
RUN npm ci --no-audit --no-fund

COPY . .
RUN npm run build -- --configuration=production

FROM nginx:1.27-alpine
COPY --from=build /src/dist/frontend/browser /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
