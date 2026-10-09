# Aviator sound files (optional)

The game synthesises all of its sounds and music by default. To use your own
audio instead, put licensed files here with these exact names — each one
replaces only its own sound, missing files keep the built-in sound:

| File            | Plays                                   |
|-----------------|-----------------------------------------|
| `music.mp3`     | Background music (looped)               |
| `flying.mp3`    | While the plane is in the air (looped)  |
| `takeoff.mp3`   | When the plane takes off                |
| `flew-away.mp3` | When the plane flies away               |
| `cashout.mp3`   | When the player cashes out              |
| `bet.mp3`       | When a bet is placed or cancelled       |

Then rebuild the player site (`$COMPOSE build player_frontend && $COMPOSE up -d player_frontend`).
Only use audio you have the rights to.
