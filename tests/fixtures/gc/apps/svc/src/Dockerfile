# Stage 1 deps
FROM node:20-alpine AS deps

# Stage 2 development — node api dev server with watch
FROM node:20-alpine AS development
ARG APP_DEV_PORT=3001
EXPOSE ${APP_DEV_PORT}

# Stage 3 build — compile the service
FROM node:20-alpine AS build
RUN npm run build

# Stage 4 production — run the compiled service
FROM node:20-alpine AS production
EXPOSE 3001
