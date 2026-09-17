# ---------- build stage ----------
FROM node:20-alpine AS build

WORKDIR /app

# Copied first so the dependency layer is reused whenever only sources change.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Vite inlines import.meta.env at BUILD time, so the API URL has to arrive as a
# build arg. Passing it as a runtime container env does nothing.
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL

RUN npm run build

# ---------- runtime stage ----------
# Static files need a static server, not a Node runtime plus a global install.
FROM nginx:1.27-alpine AS runtime

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 3000

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://127.0.0.1:3000/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
