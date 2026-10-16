# node-api release image, two stages: production dependencies installed from the lockfile the
# release carries, then only the built service and those dependencies, as the unprivileged `node`
# user ({toolchain.version|22}, {port}, {healthcheck} the driver's probe).
FROM node:{toolchain.version|22}-alpine AS deps
WORKDIR /app
COPY package.json pnpm-lock.yaml* package-lock.json* yarn.lock* ./
RUN corepack enable && if [ -f pnpm-lock.yaml ]; then pnpm install --prod --frozen-lockfile; elif [ -f yarn.lock ]; then yarn install --production --frozen-lockfile; elif [ -f package-lock.json ]; then npm ci --omit=dev; else npm install --omit=dev; fi

FROM node:{toolchain.version|22}-alpine
WORKDIR /app
ENV NODE_ENV=production PORT={port}
COPY --from=deps --chown=node:node /app/node_modules ./node_modules
COPY --chown=node:node . .
USER node
EXPOSE {port}
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 CMD {healthcheck}
CMD ["npm", "start"]
