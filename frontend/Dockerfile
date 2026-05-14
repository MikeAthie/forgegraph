FROM node:20.19.5-alpine3.22 AS deps

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

FROM node:20.19.5-alpine3.22 AS builder

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# NEXT_PUBLIC_* env vars are inlined into the client bundle at build time.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_COMMUNICATION_ENABLED=true
ARG API_PROXY_TARGET=http://backend:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_COMMUNICATION_ENABLED=$NEXT_PUBLIC_COMMUNICATION_ENABLED
ENV API_PROXY_TARGET=$API_PROXY_TARGET
ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build && npm prune --omit=dev

FROM node:20.19.5-alpine3.22 AS runner

WORKDIR /app

ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_COMMUNICATION_ENABLED=true
ARG API_PROXY_TARGET=http://backend:8000
ENV NODE_ENV=production
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_COMMUNICATION_ENABLED=$NEXT_PUBLIC_COMMUNICATION_ENABLED
ENV API_PROXY_TARGET=$API_PROXY_TARGET
ENV NEXT_TELEMETRY_DISABLED=1

COPY --from=builder --chown=node:node /app/public ./public
COPY --from=builder --chown=node:node /app/.next ./.next
COPY --from=builder --chown=node:node /app/package.json ./package.json
COPY --from=builder --chown=node:node /app/node_modules ./node_modules

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD wget -q -O- http://127.0.0.1:3000/ >/dev/null 2>&1 || exit 1

USER node

CMD ["npm", "run", "start"]
