FROM node:24-alpine AS deps

WORKDIR /app
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:24-alpine AS builder

WORKDIR /app
ARG FREECADAI_API_BASE_URL=http://api:8000
ARG NEXT_PUBLIC_ASSET_PREFIX=
ARG NEXT_PUBLIC_API_PREFIX=
ARG NEXT_PUBLIC_ROUTE_PREFIX=
ENV FREECADAI_API_BASE_URL=${FREECADAI_API_BASE_URL}
ENV NEXT_PUBLIC_ASSET_PREFIX=${NEXT_PUBLIC_ASSET_PREFIX}
ENV NEXT_PUBLIC_API_PREFIX=${NEXT_PUBLIC_API_PREFIX}
ENV NEXT_PUBLIC_ROUTE_PREFIX=${NEXT_PUBLIC_ROUTE_PREFIX}
COPY --from=deps /app/node_modules ./node_modules
COPY web ./
RUN npm run build

FROM node:24-alpine AS runner

WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/package-lock.json ./package-lock.json
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.mjs ./next.config.mjs
COPY --from=builder /app/node_modules ./node_modules

EXPOSE 3000
CMD ["npx", "next", "start", "--hostname", "0.0.0.0", "--port", "3000"]
