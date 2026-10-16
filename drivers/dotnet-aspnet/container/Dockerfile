# dotnet-aspnet release image: the `dotnet publish` output on the ASP.NET runtime, rendered at
# package time into the release ({toolchain.version} from the module, {entry} the published
# assembly, {port} the service's internal port, {healthcheck} the driver's probe). Runs as the
# image's own unprivileged `app` user.
FROM mcr.microsoft.com/dotnet/aspnet:{toolchain.version|8.0|:majorminor}
WORKDIR /app
COPY --chown=app:app . /app
ENV ASPNETCORE_URLS=http://+:{port}
USER app
EXPOSE {port}
HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=3 CMD {healthcheck}
ENTRYPOINT ["dotnet", "{entry}"]
