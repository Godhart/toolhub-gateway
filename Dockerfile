ARG NGINX_IMAGE=nginx:stable-alpine
FROM ${NGINX_IMAGE}

RUN rm -f /etc/nginx/conf.d/default.conf
COPY templates/ /opt/toolhub-templates/
COPY scripts/30-certificate-watcher.sh /docker-entrypoint.d/30-certificate-watcher.sh
RUN chmod 0755 /docker-entrypoint.d/30-certificate-watcher.sh

ENV NGINX_ENVSUBST_TEMPLATE_DIR=/opt/toolhub-templates/https
ENV NGINX_ENVSUBST_FILTER="^(DOMAIN|TOOLHUB_UPSTREAM|MCP_PATH)$"

EXPOSE 80 443
# Keep the official entrypoint (envsubst) and foreground nginx command.

