# Stage 1 deps
FROM node:20-alpine AS deps

# Stage 2 development — Vite dev server on the app dev port
FROM node:20-alpine AS development
ARG APP_DEV_PORT=5177
EXPOSE ${APP_DEV_PORT}

# Stage 3 build — produce static assets
FROM node:20-alpine AS build
RUN npm run build

# Stage 4 production — nginx serves the built assets on :80
ARG NGINX_VERSION=1.27-alpine
FROM nginx:${NGINX_VERSION} AS production
EXPOSE 80
