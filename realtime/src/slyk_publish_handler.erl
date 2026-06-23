%%%-------------------------------------------------------------------
%%% @doc Internal HTTP ingest (POST /publish/<channel>).
%%%
%%% Lets the Django backend push a message into a channel without holding a
%%% WebSocket open: the request body is fanned out to every socket subscribed
%%% to <channel> via the same `pg` scope used by slyk_ws_handler. Nginx does
%%% not proxy /publish, so browsers can't reach it directly — but the docker
%%% compose network is shared by every container, so this still requires the
%%% same shared secret Django sends on every call (X-Internal-Token) to stop
%%% anything else on that network from injecting fake odds/chat/balance
%%% events into a live feed.
%%%-------------------------------------------------------------------
-module(slyk_publish_handler).
-behaviour(cowboy_handler).

-export([init/2]).

-define(SCOPE, slyk_channels).

init(Req0, State) ->
    case authorize(Req0) of
        ok ->
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
            {ok, Req, State};
        {error, Reason} ->
            Req = cowboy_req:reply(403, #{<<"content-type">> => <<"text/plain">>}, Reason, Req0),
            {ok, Req, State}
    end.

authorize(Req) ->
    Expected = list_to_binary(os:getenv("REALTIME_SHARED_SECRET", "")),
    Presented = cowboy_req:header(<<"x-internal-token">>, Req, <<>>),
    case Expected =/= <<>> andalso Presented =:= Expected of
        true -> ok;
        false -> {error, <<"forbidden">>}
    end.

%% --- helpers ---------------------------------------------------------------

channel_name([]) -> <<"lobby">>;
channel_name(Segments) ->
    iolist_to_binary(lists:join(<<":">>, Segments)).

%% Fan the message out to every socket on the channel; returns how many got it.
broadcast(Channel, Msg) ->
    Members = pg:get_members(?SCOPE, Channel),
    [Pid ! {broadcast, Msg} || Pid <- Members],
    length(Members).
