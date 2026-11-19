# Studio web app (Next.js standalone output).
#   docker build -f webapp/deploy/web.Dockerfile --build-arg API_URL=http://api:8000 -t studio-web .
FROM node:22-alpine AS build
WORKDIR /app
COPY webapp/web/package.json webapp/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY webapp/web ./
# /api rewrites are fixed at build time: point them at the API service
ARG API_URL=http://api:8000
ENV API_URL=$API_URL NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine AS run
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -S studio && adduser -S studio -G studio
COPY --from=build --chown=studio /app/.next/standalone ./
COPY --from=build --chown=studio /app/.next/static ./.next/static
USER studio
EXPOSE 3000
CMD ["node", "server.js"]
