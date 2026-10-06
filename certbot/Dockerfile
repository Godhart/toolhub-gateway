ARG CERTBOT_IMAGE=certbot/certbot:latest
FROM ${CERTBOT_IMAGE}
COPY entrypoint.sh /usr/local/bin/toolhub-certbot
COPY notify-nginx.sh /usr/local/bin/notify-nginx
RUN chmod 0755 /usr/local/bin/toolhub-certbot /usr/local/bin/notify-nginx
ENTRYPOINT ["/usr/local/bin/toolhub-certbot"]
CMD ["renew-loop"]
