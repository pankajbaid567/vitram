# OpenWA (unofficial WhatsApp gateway) for a free host with no persistent disk.
# Adds one thing to the upstream image: its data folder (WhatsApp login state, API keys, database) is restored from an
# S3-compatible bucket at start and copied back every 30 seconds and on shutdown, so a restart does not log WhatsApp out.
FROM ghcr.io/rmyndharis/openwa:0.23.6
USER root
RUN apt-get update && apt-get install -y --no-install-recommends rclone ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY start.sh /usr/local/bin/vitram-openwa-start.sh
RUN chmod +x /usr/local/bin/vitram-openwa-start.sh
ENTRYPOINT ["dumb-init", "--", "/usr/local/bin/vitram-openwa-start.sh"]
CMD ["node", "dist/main"]
