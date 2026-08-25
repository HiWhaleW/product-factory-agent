# syntax=docker/dockerfile:1.7
FROM node:24.19.0-alpine AS build

ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app

RUN corepack enable && corepack prepare pnpm@11.19.0 --activate

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json ./apps/web/package.json
RUN pnpm install --frozen-lockfile

COPY apps/web ./apps/web
COPY packages ./packages
RUN pnpm --filter @product-factory/web build

FROM node:24.19.0-alpine AS runtime

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000

WORKDIR /app
COPY --from=build --chown=10001:10001 /app/apps/web/.next/standalone ./
COPY --from=build --chown=10001:10001 /app/apps/web/.next/static ./apps/web/.next/static
COPY --from=build --chown=10001:10001 /app/apps/web/public ./apps/web/public
RUN mkdir -p /data/logs /app/apps/web/.next/cache && chown -R 10001:10001 /data /app/apps/web/.next/cache

USER 10001:10001
WORKDIR /app/apps/web
EXPOSE 3000

CMD ["node", "server.js"]
