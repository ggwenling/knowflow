FROM node:24-alpine@sha256:a34ab6d7f6f4813f4d0c5469d74685604b962fbdbf5793a7bc7b4998ecb867c8 AS dependencies
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:24-alpine@sha256:a34ab6d7f6f4813f4d0c5469d74685604b962fbdbf5793a7bc7b4998ecb867c8 AS build
WORKDIR /app
ARG NEXT_PUBLIC_PERFORMANCE_ENDPOINT
ENV NEXT_TELEMETRY_DISABLED=1 NEXT_PUBLIC_PERFORMANCE_ENDPOINT=${NEXT_PUBLIC_PERFORMANCE_ENDPOINT}
COPY --from=dependencies /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:24-alpine@sha256:a34ab6d7f6f4813f4d0c5469d74685604b962fbdbf5793a7bc7b4998ecb867c8 AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
COPY --from=build --chown=node:node /app/public ./public
COPY --from=build --chown=node:node /app/THIRD-PARTY-LICENSES.md ./THIRD-PARTY-LICENSES.md
COPY --from=build --chown=node:node /app/node_modules/@fontsource/dm-sans/LICENSE ./licenses/dm-sans.txt
COPY --from=build --chown=node:node /app/node_modules/@fontsource/dm-serif-display/LICENSE ./licenses/dm-serif-display.txt
USER node
EXPOSE 3000
CMD ["node", "server.js"]
