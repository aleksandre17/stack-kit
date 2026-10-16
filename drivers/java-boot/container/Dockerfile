# java-boot release image: the module's boot jar on a JRE, rendered at package time into the
# release ({toolchain.version|17} from the module, {artifact} the packaged jar, {port} the
# service's internal port). A module with its own recipe declares `container.dockerfile`.
FROM eclipse-temurin:{toolchain.version|17}-jre
WORKDIR /app
COPY {artifact} /app/app.jar
EXPOSE {port}
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
