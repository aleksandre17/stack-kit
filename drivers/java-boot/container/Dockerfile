# java-boot release image: the module's boot jar on a JRE, rendered at package time into the
# release ({toolchain.version|17} from the module, {artifact} the packaged jar, {port} the
# service's internal port, {healthcheck} the driver's probe). Runs as an unprivileged user.
# A module with its own recipe declares `container.dockerfile`.
FROM eclipse-temurin:{toolchain.version|17}-jre
RUN useradd --system --uid 10001 --home-dir /app app
WORKDIR /app
COPY --chown=10001:10001 {artifact} /app/app.jar
USER 10001
EXPOSE {port}
HEALTHCHECK --interval=10s --timeout=3s --start-period=60s --retries=3 CMD {healthcheck}
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
