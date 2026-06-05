%%%-------------------------------------------------------------------
%%% @doc Cowboy WebSocket handler for /ws/<channel>.
%%%
%%% Each connection joins a `pg` process group named after its channel
%%% (e.g. "odds", "chat:lobby", "admin:bets"). Inbound text frames are
%%% fanned out to every socket in the same channel — a minimal pub/sub
%%% bus for live chat and betting feeds.
%%%-------------------------------------------------------------------
-module(slyk_ws_handler).
-behaviour(cowboy_websocket).

-export([init/2, websocket_init/1, websocket_handle/2, websocket_info/2, terminate/3]).

-define(SCOPE, slyk_channels).

%% Upgrade the HTTP request to a WebSocket. The channel is derived from the
%% path segments after /ws/ (path_info), joined with ":".
init(Req, _State) ->
    Segments = cowboy_req:path_info(Req),
    Channel = channel_name(Segments),
    {cowboy_websocket, Req, #{channel => Channel}, #{idle_timeout => 60000}}.

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
