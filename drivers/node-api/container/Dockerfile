# node-api release image: the built service and its manifest; production dependencies are
# installed from the lockfile the release carries ({toolchain.version|22}, {port}).
FROM node:{toolchain.version|22}-alpine
WORKDIR /app
COPY . /app
RUN corepack enable && if [ -f pnpm-lock.yaml ]; then pnpm install --prod --frozen-lockfile; elif [ -f yarn.lock ]; then yarn install --production --frozen-lockfile; elif [ -f package-lock.json ]; then npm ci --omit=dev; else npm install --omit=dev; fi
ENV NODE_ENV=production PORT={port}
EXPOSE {port}
CMD ["npm", "start"]
