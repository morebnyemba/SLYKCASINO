%%%-------------------------------------------------------------------
%%% @doc Internal HTTP ingest (POST /publish/<channel>).
%%%
%%% Lets the Django backend push a message into a channel without holding a
%%% WebSocket open: the request body is fanned out to every socket subscribed
%%% to <channel> via the same `pg` scope used by slyk_ws_handler. Intended for
%%% the compose-internal network only — nginx does not proxy /publish, so it is
%%% not reachable by browsers.
%%%-------------------------------------------------------------------
-module(slyk_publish_handler).
-behaviour(cowboy_handler).

-export([init/2]).

-define(SCOPE, slyk_channels).

init(Req0, State) ->
    Channel = channel_name(cowboy_req:path_info(Req0)),
    {ok, Body, Req1} = cowboy_req:read_body(Req0),
    Count = broadcast(Channel, Body),
    Reply = iolist_to_binary([<<"published:">>, integer_to_binary(Count)]),
    Req = cowboy_req:reply(
        200,
        #{<<"content-type">> => <<"text/plain">>},
        Reply,
        Req1
    ),
    {ok, Req, State}.

%% --- helpers ---------------------------------------------------------------

channel_name([]) -> <<"lobby">>;
channel_name(Segments) ->
    iolist_to_binary(lists:join(<<":">>, Segments)).

%% Fan the message out to every socket on the channel; returns how many got it.
broadcast(Channel, Msg) ->
    Members = pg:get_members(?SCOPE, Channel),
    [Pid ! {broadcast, Msg} || Pid <- Members],
    length(Members).
