"""The 'coming soon' casino catalogue: titles shown in the lobby with a Notify me button until
each is licensed and connected (an aggregator integration replaces them with the real games,
matched by slug, and the waitlist is told).

Studio names are given only where they're well known; 'TBA' otherwise. No provider artwork is
used: tiles get generated art (web: lib/casino tileArt), so nothing copyrighted is displayed.
"""
from __future__ import annotations

from django.utils.text import slugify

TBA = 'TBA'

# (category, provider, [titles])
GROUPS: list[tuple[str, str, list[str]]] = [
    # -- fast games: crash-style rounds of a few seconds -------------------------------------
    ('fast', 'SmartSoft', ['JetX', 'JetX3', 'Balloon', 'Cappadocia']),
    ('fast', 'InOut Games', ['Chicken Road', 'Chicken Road 2']),
    ('fast', 'Pragmatic Play', ['Spaceman', 'Big Bass Crash']),
    ('fast', 'BGaming', ['Space XY']),
    ('fast', 'Turbo Games', ['Crash X', 'Limbo Rider']),
    ('fast', 'Onlyplay', ['F777 Fighter']),
    ('fast', TBA, ['Maverick', 'Navigator', 'Lucky Jet', 'Rocket X', 'Aviatrix', 'Zeppelin', 'Rocket Queen', 'Crash Duel',
                   'Tower Rush', 'Speed Crash', 'Cosmic Crash', 'Jet Lucky 2', 'Sky Liner', 'Air Racer', 'Moon Rocket',
                   'Turbo Crash', 'Pilot Coin', 'Rocket Dice', 'Space Ride', 'Bomb Crash', 'High Flyer', 'Comet Crash',
                   'Crash Royale', 'Sky Jet', 'Rocket Run', 'Flight Fortune', 'Mega Crash', 'Hot Air Balloon', 'Turbo Jet',
                   'Star Rocket', 'Jet Fighter', 'Lucky Plane', 'Rocket Man Rush', 'Crash Kings']),
    # -- mini games: quick one-tap games ---------------------------------------------------------
    ('mini', 'Spribe', ['Mines', 'Plinko', 'Dice', 'Goal', 'Hi Lo', 'Keno', 'Mini Roulette', 'Hotline']),
    ('mini', 'BGaming', ['Plinko XY', 'Dice BG']),
    ('mini', 'Turbo Games', ['Towers', 'Hamsta', 'Dice Twice']),
    ('mini', TBA, ['Coin Flip', 'Limbo', 'Wheel', 'Hilo Cards', 'Keno 80', 'Mines Pro', 'Crystal Mines', 'Tower Climb', 'Penalty Kick',
                   'Basketball Shot', 'Darts 180', 'Horse Dash', 'Rock Paper Scissors', 'Lucky Wheel', 'Ladder', 'Diamonds',
                   'Fruit Slice', 'Gem Drop', 'Cups', 'Lucky Cards', 'Thimbles', 'Number Guess', 'Color Game', 'Red or Black',
                   'Higher Lower', 'Cricket Shot', 'Pachinko', 'Treasure Dig', 'Bubble Pop', 'Mini Baccarat Flash',
                   'Space Mines', 'Snake Run', 'Lucky 7s Flip', 'Golden Chest', 'Plinko 1000', 'Mines Xtreme', 'Keno Express',
                   'Lucky Dice 3', 'Big Wheel', 'Card Flip', 'Treasure Towers', 'Goal Rush', 'Chicken Cross', 'Frog Jump',
                   'Coin Rush', 'Egg Drop', 'Gold Rush Mines']),
    # -- slots -----------------------------------------------------------------------------------
    ('slots', 'Pragmatic Play', [
        'Gates of Olympus', 'Gates of Olympus 1000', 'Sweet Bonanza', 'Sweet Bonanza 1000', 'Sugar Rush', 'Sugar Rush 1000',
        'Starlight Princess', 'Starlight Princess 1000', 'Big Bass Bonanza', 'Bigger Bass Bonanza', 'Big Bass Splash',
        'Big Bass Amazon Xtreme', 'Christmas Big Bass Bonanza', 'Bigger Bass Blizzard', 'The Dog House', 'The Dog House Megaways',
        'Wolf Gold', 'Fruit Party', 'Fruit Party 2', 'Wild West Gold', 'Wild West Gold Megaways', 'Madame Destiny Megaways',
        'Great Rhino Megaways', 'Great Rhino', 'Buffalo King', 'Buffalo King Megaways', 'Floating Dragon', 'Zeus vs Hades',
        'Gems Bonanza', 'Aztec Gems', 'Chilli Heat', 'Mustang Gold', 'John Hunter and the Tomb of the Scarab Queen',
        'Release the Kraken', 'Power of Thor Megaways', 'Hot Fiesta', "Joker's Jewels", 'Wild Booster', 'Extra Juicy',
        'Juicy Fruits', '5 Lions Megaways', 'Fire Strike', 'Book of the Fallen', 'Curse of the Werewolf Megaways',
        'Pyramid Bonanza', 'Cleocatra', 'Fire Stampede', 'Muertos Multiplier Megaways', 'Cash Bonanza', 'Hot to Burn',
        '7 Piggies', 'Wisdom of Athena', 'Zombie Carnival', 'Treasure Wild', 'Emerald King', 'Starz Megaways', 'Drill That Gold',
        'Gold Party', 'Big Juan', 'Bounty Gold', 'Ultra Hold and Spin', 'Mochimon']),
    ('slots', 'NetEnt', [
        'Starburst', 'Starburst XXXtreme', "Gonzo's Quest", "Gonzo's Quest Megaways", 'Dead or Alive', 'Dead or Alive 2', 'Twin Spin',
        'Divine Fortune', 'Mega Fortune', 'Hall of Gods', 'Blood Suckers', 'Jack Hammer', 'Jack and the Beanstalk', 'Fruit Shop',
        'Narcos', 'Vikings', 'Finn and the Swirly Spin', 'Aloha! Cluster Pays', 'Butterfly Staxx', 'Reel Rush',
        'Secrets of Atlantis', 'Steam Tower', 'Koi Princess', 'Dazzle Me', 'Space Wars', 'Lights']),
    ('slots', "Play'n GO", [
        'Book of Dead', 'Reactoonz', 'Reactoonz 2', 'Rise of Olympus', 'Legacy of Dead', 'Fire Joker', 'Moon Princess',
        'Rich Wilde and the Tome of Madness', 'Gemix', 'Sweet Alchemy', 'Viking Runecraft', 'Honey Rush', 'Golden Ticket',
        'Hugo', 'Hugo 2', 'Ankh of Anubis', 'Tower Quest', 'Pearls of India']),
    ('slots', 'Games Global', [
        'Mega Moolah', 'Immortal Romance', 'Thunderstruck II', 'Break da Bank Again', 'Avalon', '9 Masks of Fire',
        'Agent Jane Blonde Returns', 'Ancient Fortunes: Zeus', 'Lucky Leprechaun', 'Basketball Star', 'Assassin Moon', 'Book of Oz']),
    ('slots', 'Big Time Gaming', ['Bonanza Megaways', 'Extra Chilli', 'White Rabbit', 'Danger High Voltage', 'Queen of Riches',
                                  'Lil Devil', 'Star Clusters Megapays']),
    ('slots', 'Nolimit City', ['Mental', 'San Quentin xWays', 'Tombstone RIP', 'Fire in the Hole xBomb', 'Deadwood', 'Punk Rocker',
                               'Misery Mining', 'Das xBoot', 'East Coast vs West Coast', 'Book of Shadows', 'Karen Maneater']),
    ('slots', 'Hacksaw Gaming', ['Wanted Dead or a Wild', 'Chaos Crew', 'Chaos Crew 2', 'Hand of Anubis', "Stick 'Em", 'Itero',
                                 'RIP City', 'Dork Unit', 'Le Bandit', 'Le Pharaoh', 'Frutz', 'Cubes', 'Joker Bombs', "Stack 'Em"]),
    ('slots', 'Push Gaming', ["Jammin' Jars", "Jammin' Jars 2", 'Razor Shark', 'Fat Rabbit', 'Retro Tapes', 'Big Bamboo']),
    ('slots', 'Relax Gaming', ['Money Train 2', 'Money Train 3', 'Money Train 4', 'Temple Tumble', 'Snake Arena']),
    ('slots', 'Red Tiger', ["Dragon's Luck", "Pirates' Plenty", 'Mystery Reels', 'Piggy Riches Megaways', 'Rainbow Jackpots',
                            'Bounty Raid', 'Gems Gone Wild', 'Treasure Mine', "Thor's Lightning", 'Primate King']),
    ('slots', 'Playtech', ['Age of the Gods', 'Buffalo Blitz', 'Great Blue', 'Fire Blaze: Blue Wizard', 'Halloween Fortune',
                           "Leprechaun's Luck", 'Wild Lava']),
    ('slots', 'Yggdrasil', ['Valley of the Gods', 'Vikings Go Berzerk', 'Vikings Go Wild', 'Holmes and the Stolen Stones',
                            'Jungle Books', 'Cazino Zeppelin', 'Joker Millions', 'Golden Fish Tank', 'Hades: Gigablox']),
    ('slots', 'Thunderkick', ['Esqueleto Explosivo', 'Esqueleto Explosivo 2', 'Pink Elephants', 'Pink Elephants 2',
                              "Beat the Beast: Kraken's Lair"]),
    ('slots', 'Quickspin', ['Big Bad Wolf', 'Sakura Fortune', 'Sticky Bandits', 'Eastern Emeralds', 'Hot Sync', 'Second Strike']),
    ('slots', 'ELK Studios', ['Wild Toro', 'Cygnus', 'Ecuador Gold', 'Nitropolis', 'Kaiju']),
    ('slots', 'Habanero', ['Hot Hot Fruit', 'Koi Gate', 'Lantern Luck', 'Wealth Inn', 'Fa Cai Shen', 'Happy Ape',
                           'Mystic Fortune Deluxe', 'Hey Sushi']),
    ('slots', 'PG Soft', ['Fortune Tiger', 'Fortune Ox', 'Fortune Rabbit', 'Fortune Mouse', 'Mahjong Ways', 'Mahjong Ways 2',
                          'Treasures of Aztec', 'Wild Bandito', 'Lucky Neko', 'Ganesha Gold', 'Leprechaun Riches', 'Dragon Hatch',
                          'Caishen Wins', 'Wild Bounty Showdown', 'Queen of Bounty']),
    ('slots', 'Amusnet', ['40 Super Hot', '20 Super Hot', '100 Super Hot', 'Shining Crown', 'Burning Hot', 'Flaming Hot',
                          'Rise of Ra', 'Supreme Hot']),
    ('slots', 'Wazdan', ['9 Burning Stars', 'Power of Gods: Hades']),
    ('slots', 'BGaming', ['Elvis Frog in Vegas', 'Aloha King Elvis', 'Lucky Lady Moon', 'Bonanza Billion', 'Book of Cats',
                          'Gold Magnate', 'Dig Dig Digger', 'Wild Tiger', 'Merge Up']),
    ('slots', 'Endorphina', ["Satoshi's Secret", 'Lucky Streak 3', '2027 ISS', 'Fresh Fruits', 'Voodoo']),
    ('slots', TBA, ['Fruit Fiesta 5', 'Lucky 777 Deluxe', 'Diamond Strike Gold', 'Pharaoh Riches', 'Safari Spins', 'Dragon Pearls',
                    'Viking Voyage', 'Wild Buffalo Run', 'Golden Lotus', 'Mystic Moon', 'Pirate Treasure Hunt', 'Jungle Jackpots',
                    'Neon Nights', 'Cash Cow Farm', 'Lucky Clover Gold', 'Royal Crown Fruits', 'Aztec Sun', 'Inferno Hot 100',
                    'Hot Chilli Bells', 'Golden Gorilla', 'African Sunset', 'Savanna King', 'Lion Pride Gold', 'Zambezi Riches',
                    'Victoria Falls Fortune', 'Great Zimbabwe Gold', 'Baobab Bonanza', 'Kalahari Gems', 'Ubuntu Fortune',
                    'Sahara Sands', 'Kilimanjaro Cash', 'Big Five Safari']),
    # -- live casino -----------------------------------------------------------------------------
    ('live', 'Evolution', [
        'Crazy Time', 'Monopoly Live', 'Monopoly Big Baller', 'Lightning Roulette', 'XXXtreme Lightning Roulette', 'Immersive Roulette',
        'Speed Roulette', 'Auto-Roulette', 'Red Door Roulette', 'Lightning Blackjack', 'Infinite Blackjack', 'Speed Blackjack',
        'Free Bet Blackjack', 'Power Blackjack', 'Lightning Baccarat', 'Speed Baccarat', 'No Commission Baccarat', 'Dragon Tiger',
        'Lightning Dice', 'Craps Live', 'Super Sic Bo', 'Deal or No Deal', 'Dream Catcher', 'Funky Time', "Gonzo's Treasure Map",
        'Cash or Crash', 'Mega Ball', 'Football Studio', 'Fan Tan', 'Crazy Coin Flip', "Casino Hold'em", "Ultimate Texas Hold'em",
        'Three Card Poker', 'Side Bet City', 'Bac Bo', 'Stock Market', 'Golden Wealth Baccarat', 'Peek Baccarat']),
    ('live', 'Pragmatic Play Live', ['Sweet Bonanza CandyLand', 'Mega Wheel', 'Mega Roulette', 'PowerUP Roulette', 'Mega Sic Bo',
                                     'ONE Blackjack', 'Boom City', 'Snakes & Ladders Live', 'Speed Baccarat PP', 'Andar Bahar PP']),
    ('live', 'Ezugi', ['Andar Bahar', 'Teen Patti', 'Lucky 7', '32 Cards', 'Bet on Numbers', 'Ultimate Roulette']),
    # -- table games (RNG) -------------------------------------------------------------------------
    ('table', TBA, ['European Roulette', 'American Roulette', 'French Roulette', 'Classic Blackjack', 'Multihand Blackjack',
                    'Single Deck Blackjack', 'Atlantic City Blackjack', 'Vegas Strip Blackjack', 'European Blackjack', 'Spanish 21',
                    'Blackjack Surrender', 'Baccarat', 'Punto Banco', 'Mini Baccarat', "Casino Hold'em Poker", 'Three Card Poker RNG',
                    'Caribbean Stud Poker', "Texas Hold'em Bonus Poker", 'Pai Gow Poker', 'Red Dog', 'Casino War', 'Sic Bo', 'Craps',
                    'Jacks or Better', 'Deuces Wild', 'Joker Poker', 'Aces and Faces', 'Double Bonus Poker', 'Bonus Poker',
                    'Dragon Tiger RNG', 'Andar Bahar RNG', 'Teen Patti RNG', 'Zoom Roulette', 'Double Ball Roulette']),
    # -- virtual sports ------------------------------------------------------------------------------
    ('virtual', TBA, ['Virtual Football League', 'Virtual Premier Football', 'Virtual Champions Cup', 'Virtual World Cup',
                      'Virtual Africa Cup', 'Virtual Horse Racing', 'Virtual Greyhounds', 'Virtual Basketball', 'Virtual Tennis',
                      'Virtual Cycling', 'Virtual Speedway', 'Virtual Cricket', 'Virtual Penalty Shootout', 'Virtual Motor Racing',
                      'Virtual Boxing', 'Virtual Darts', 'Virtual Baseball', 'Virtual Ice Hockey', 'Virtual Rugby', 'Instant Football']),
    # -- instant win / scratch -----------------------------------------------------------------------
    ('instant', TBA, ['Scratch Gold', 'Lucky Scratch', 'Diamond Scratch', 'Cash Scratch', 'Fruit Scratch', 'Treasure Scratch',
                      'Bingo 75', 'Bingo 90', 'Lotto 6/49', 'Quick Lotto', 'Lucky Numbers', 'Instant Keno', 'Pull Tabs',
                      'Mega Scratch', 'Super Scratch 7s', 'Wheel of Wins', 'Lucky Envelope', 'Golden Ticket Scratch']),
]


def entries() -> list[dict]:
    """Every coming-soon game as Game fields; slugs are unique (provider added on a name clash)."""
    out, seen = [], set()
    for category, provider, names in GROUPS:
        for name in names:
            slug = slugify(name)[:100] or 'game'
            if slug in seen:
                slug = f'{slug}-{slugify(provider)}'[:110]
            seen.add(slug)
            out.append({'slug': slug, 'name': name, 'provider': provider, 'category': category})
    return out
