%%%-------------------------------------------------------------------
%%% @doc Top-level supervisor. Holds the channel registry (a pg scope)
%%% used to broadcast messages to all sockets subscribed to a channel.
%%%-------------------------------------------------------------------
-module(slyk_realtime_sup).
-behaviour(supervisor).

-export([start_link/0, init/1]).

start_link() ->
    supervisor:start_link({local, ?MODULE}, ?MODULE, []).

init([]) ->
    SupFlags = #{strategy => one_for_one, intensity => 5, period => 10},
    %% `pg` process groups back the pub/sub fan-out for channels.
    ChildSpecs = [
        #{
            id => slyk_pg,
            start => {pg, start_link, [slyk_channels]},
            restart => permanent,
            type => worker,
            modules => [pg]
        }
    ],
    {ok, {SupFlags, ChildSpecs}}.
