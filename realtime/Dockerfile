# =============================================================================
#  SLYK CASINO — Erlang realtime engine (Cowboy WebSocket on :8080)
#  Multi-stage: build a self-contained OTP release, run it on a slim base.
#  Reached via nginx /ws/ (with Upgrade/Connection headers).
# =============================================================================

# ---- Build stage: compile + assemble the release with ERTS bundled ----------
FROM erlang:27-alpine AS build
WORKDIR /src

# Fetch deps first for layer caching.
COPY rebar.config rebar.lock* ./
RUN rebar3 get-deps || true

COPY . .
RUN rebar3 as prod release

# ---- Runtime stage: minimal image, just the release ------------------------
FROM alpine:3.20 AS runtime
# OTP release bundles ERTS but still needs libstdc++/ncurses at runtime.
RUN apk add --no-cache libstdc++ ncurses-libs openssl \
 && addgroup -S slyk && adduser -S slyk -G slyk
WORKDIR /opt/slyk

COPY --from=build /src/_build/prod/rel/slyk_realtime ./
RUN chown -R slyk:slyk /opt/slyk
USER slyk

ENV PORT=8080
EXPOSE 8080

# Foreground the release so the container lifecycle tracks the VM.
CMD ["/opt/slyk/bin/slyk_realtime", "foreground"]
