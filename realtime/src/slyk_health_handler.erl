%%%-------------------------------------------------------------------
%%% @doc Plain HTTP health endpoint (GET /health -> 200 "ok").
%%%-------------------------------------------------------------------
-module(slyk_health_handler).
-behaviour(cowboy_handler).

-export([init/2]).

init(Req0, State) ->
    Req = cowboy_req:reply(
        200,
        #{<<"content-type">> => <<"text/plain">>},
        <<"ok">>,
        Req0
    ),
    {ok, Req, State}.
