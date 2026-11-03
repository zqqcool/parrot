# Alpine/musl avoids the clone3 seccomp incompatibility on the legacy Docker 19.03 builder.
FROM node:20-alpine AS build

ARG NPM_REGISTRY=https://registry.npmmirror.com
ARG NODE_MAX_OLD_SPACE_SIZE_MB=4096

ENV NPM_CONFIG_REGISTRY=${NPM_REGISTRY} \
    NPM_CONFIG_AUDIT=false \
    NPM_CONFIG_FUND=false \
    NODE_OPTIONS=--max-old-space-size=${NODE_MAX_OLD_SPACE_SIZE_MB}

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . ./
RUN npm run build

FROM nginx:1.28-alpine AS runtime

COPY nginx/default.conf /etc/nginx/conf.d/default.conf
COPY nginx/upgrade.conf /etc/nginx/conf.d/00-upgrade.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
