%%%-------------------------------------------------------------------
%%% @doc SLYK realtime engine — application entry point.
%%% Starts a Cowboy listener on :8080 and routes:
%%%   /ws/[...]   -> slyk_ws_handler  (WebSocket: chat + betting feeds)
%%%   /health     -> slyk_health_handler
%%% Nginx proxies /ws/ here with the Upgrade/Connection headers.
%%%-------------------------------------------------------------------
-module(slyk_realtime_app).
-behaviour(application).

-export([start/2, stop/1]).

start(_StartType, _StartArgs) ->
    %% Start the supervisor first so the `pg` channel scope exists before any
    %% WebSocket connection (handled by the listener below) tries to use it.
    {ok, SupPid} = slyk_realtime_sup:start_link(),
    Dispatch = cowboy_router:compile([
        {'_', [
            {"/health", slyk_health_handler, []},
            %% Everything under /ws/ (e.g. /ws/odds, /ws/chat:lobby) upgrades to WS.
            {"/ws/[...]", slyk_ws_handler, []}
        ]}
    ]),
    Port = list_to_integer(os:getenv("PORT", "8080")),
    {ok, _} = cowboy:start_clear(
        slyk_http_listener,
        [{port, Port}],
        #{env => #{dispatch => Dispatch}}
    ),
    {ok, SupPid}.

stop(_State) ->
    ok = cowboy:stop_listener(slyk_http_listener).
