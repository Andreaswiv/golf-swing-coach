# Multi-arch: Microsoft publishes linux/arm64 and linux/amd64 images, so this builds natively on Apple Silicon.
FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY GolfCoach.Api/GolfCoach.Api.csproj GolfCoach.Api/
RUN dotnet restore GolfCoach.Api/GolfCoach.Api.csproj
COPY GolfCoach.Api/ GolfCoach.Api/
RUN dotnet publish GolfCoach.Api/GolfCoach.Api.csproj -c Release -o /out --no-restore

FROM mcr.microsoft.com/dotnet/aspnet:10.0
# Npgsql probes for GSSAPI at startup and logs an error if the library is missing.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgssapi-krb5-2 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build /out .
# The base image already listens on 8080 (ASPNETCORE_HTTP_PORTS).
ENV Storage__DataDir=/data
EXPOSE 8080
ENTRYPOINT ["dotnet", "GolfCoach.Api.dll"]
