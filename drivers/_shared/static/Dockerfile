# A single-page app's release image, rendered at package time into the release: the built app
# ({serve}, the module's `container.serve`) on the pinned unprivileged nginx, and its server config
# ({config}: spa.conf rendered with `container.serve` / `container.proxy` -- the same bytes `render`
# projects as server.conf). One recipe for every mode: the local stack, a dev release, prod.
FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY {serve}/ {webRoot}/
COPY {config} /etc/nginx/conf.d/default.conf
USER nginx
EXPOSE {port}
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 CMD {healthcheck}
