# dotnet-aspnet release image: the `dotnet publish` output on the ASP.NET runtime, rendered at
# package time into the release ({toolchain.version} from the module, {entry} the published
# assembly, {port} the service's internal port).
FROM mcr.microsoft.com/dotnet/aspnet:{toolchain.version|8.0|:majorminor}
WORKDIR /app
COPY . /app
ENV ASPNETCORE_URLS=http://+:{port}
EXPOSE {port}
ENTRYPOINT ["dotnet", "{entry}"]
