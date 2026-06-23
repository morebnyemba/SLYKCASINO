%%%-------------------------------------------------------------------
%%% @doc Cowboy WebSocket handler for /ws/<channel>.
%%%
%%% Each connection joins a `pg` process group named after its channel
%%% (e.g. "odds", "chat:lobby", "admin:bets"). Inbound text frames are
%%% fanned out to every socket in the same channel — a minimal pub/sub
%%% bus for live chat and betting feeds.
%%%
%%% `admin:*` channels carry operator-only data (live bet/chat streams), so
%%% joining one requires a short-lived `?ticket=` query param signed by
%%% Django (see common.realtime_auth.make_ws_ticket) — without it, anyone who
%%% can reach this port could eavesdrop on or inject into operator feeds.
%%%-------------------------------------------------------------------
-module(slyk_ws_handler).
-behaviour(cowboy_websocket).

-export([init/2, websocket_init/1, websocket_handle/2, websocket_info/2, terminate/3]).

-define(SCOPE, slyk_channels).

%% Upgrade the HTTP request to a WebSocket. The channel is derived from the
%% path segments after /ws/ (path_info), joined with ":". `admin:*` channels
%% are gated by a signed ticket; everything else stays open (public feeds).
init(Req, _State) ->
    Segments = cowboy_req:path_info(Req),
    Channel = channel_name(Segments),
    case authorize(Channel, Req) of
        ok ->
            {cowboy_websocket, Req, #{channel => Channel}, #{idle_timeout => 60000}};
        {error, Reason} ->
            Req2 = cowboy_req:reply(401, #{<<"content-type">> => <<"text/plain">>}, Reason, Req),
            {ok, Req2, #{channel => Channel}}
    end.

websocket_init(#{channel := Channel} = State) ->
    ok = pg:join(?SCOPE, Channel, self()),
    Welcome = iolist_to_binary([<<"connected:">>, Channel]),
    {[{text, Welcome}], State}.

%% Inbound message from this client -> broadcast to everyone on the channel.
websocket_handle({text, Msg}, #{channel := Channel} = State) ->
    broadcast(Channel, Msg),
    {ok, State};
websocket_handle({ping, Payload}, State) ->
    {[{pong, Payload}], State};
websocket_handle(_Frame, State) ->
    {ok, State}.

%% A broadcast addressed to this socket -> push it to the client.
websocket_info({broadcast, Msg}, State) ->
    {[{text, Msg}], State};
websocket_info(_Info, State) ->
    {ok, State}.

terminate(_Reason, _Req, #{channel := Channel}) ->
    catch pg:leave(?SCOPE, Channel, self()),
    ok;
terminate(_Reason, _Req, _State) ->
    ok.

%% --- helpers ---------------------------------------------------------------

channel_name([]) -> <<"lobby">>;
channel_name(Segments) ->
    iolist_to_binary(lists:join(<<":">>, Segments)).

broadcast(Channel, Msg) ->
    [Pid ! {broadcast, Msg} || Pid <- pg:get_members(?SCOPE, Channel)],
    ok.

%% Only admin:* channels are gated; everything else is a public feed.
authorize(<<"admin:", _/binary>> = Channel, Req) ->
    Qs = cowboy_req:parse_qs(Req),
    case lists:keyfind(<<"ticket">>, 1, Qs) of
        {<<"ticket">>, Ticket} -> verify_ticket(Channel, Ticket);
        _ -> {error, <<"missing ticket">>}
    end;
authorize(_Channel, _Req) ->
    ok.

verify_ticket(Channel, Ticket) ->
    case binary:split(Ticket, <<".">>, [global]) of
        [Channel, ExpiryBin, SigHex] ->
            try
                Expiry = binary_to_integer(ExpiryBin),
                Now = erlang:system_time(second),
                Secret = list_to_binary(os:getenv("REALTIME_SHARED_SECRET", "")),
                Msg = <<Channel/binary, ".", ExpiryBin/binary>>,
                Expected = binary:encode_hex(crypto:mac(hmac, sha256, Secret, Msg), lowercase),
                case Secret =/= <<>> andalso Now =< Expiry andalso Expected =:= SigHex of
                    true -> ok;
                    false -> {error, <<"invalid or expired ticket">>}
                end
            catch
                _:_ -> {error, <<"malformed ticket">>}
            end;
        _ ->
            {error, <<"invalid ticket">>}
    end.
