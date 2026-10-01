from django.db import models


class Market(models.Model):
    """One betting market on an Event beyond the headline 1X2 prices stored on
    the Event itself — e.g. "Goals Over/Under 2.5", "Both Teams Score",
    "Asian Handicap -1". Lines that a provider groups under one bet type are
    split into one Market per line so each settles independently.

    `kind` names the settlement rule (see settlement.py); `line` carries the
    goal line / handicap it applies to, when there is one. Markets whose kind
    can't be settled from the score (corners, cards, scorers…) use MANUAL and
    are settled by an operator."""

    class Group(models.TextChoices):
        MAIN = 'main', 'Main'
        GOALS = 'goals', 'Goals'
        HALVES = 'halves', 'Halves'
        HANDICAP = 'handicap', 'Handicaps'
        SCORE = 'score', 'Correct score'
        TEAMS = 'teams', 'Team'
        CORNERS = 'corners', 'Corners'
        CARDS = 'cards', 'Cards'
        SCORERS = 'scorers', 'Goalscorers'
        SPECIALS = 'specials', 'Specials'

    class Kind(models.TextChoices):
        MATCH_RESULT = 'match_result', '1X2'
        DOUBLE_CHANCE = 'double_chance', 'Double chance'
        DRAW_NO_BET = 'draw_no_bet', 'Draw no bet'
        OVER_UNDER = 'over_under', 'Total goals over/under'
        HOME_OVER_UNDER = 'home_over_under', 'Home team goals over/under'
        AWAY_OVER_UNDER = 'away_over_under', 'Away team goals over/under'
        BTTS = 'btts', 'Both teams to score'
        ASIAN_HANDICAP = 'asian_handicap', 'Asian handicap'
        HANDICAP_RESULT = 'handicap_result', 'Handicap result (3-way)'
        CORRECT_SCORE = 'correct_score', 'Correct score'
        EXACT_GOALS = 'exact_goals', 'Exact total goals'
        ODD_EVEN = 'odd_even', 'Odd/even goals'
        HT_FT = 'ht_ft', 'Half time/full time'
        HIGHEST_SCORING_HALF = 'highest_scoring_half', 'Highest scoring half'
        CLEAN_SHEET_HOME = 'clean_sheet_home', 'Clean sheet (home)'
        CLEAN_SHEET_AWAY = 'clean_sheet_away', 'Clean sheet (away)'
        WIN_TO_NIL_HOME = 'win_to_nil_home', 'Win to nil (home)'
        WIN_TO_NIL_AWAY = 'win_to_nil_away', 'Win to nil (away)'
        WIN_TO_NIL = 'win_to_nil', 'Win to nil (either team)'
        TEAM_TO_SCORE_HOME = 'team_to_score_home', 'Home team to score'
        TEAM_TO_SCORE_AWAY = 'team_to_score_away', 'Away team to score'
        HOME_EXACT_GOALS = 'home_exact_goals', 'Home team exact goals'
        AWAY_EXACT_GOALS = 'away_exact_goals', 'Away team exact goals'
        RESULT_BTTS = 'result_btts', 'Result & both teams to score'
        RESULT_TOTAL = 'result_total', 'Result & total goals'
        WIN_BOTH_HALVES = 'win_both_halves', 'Win both halves'
        WIN_EITHER_HALF = 'win_either_half', 'Win either half'
        SCORE_BOTH_HALVES = 'score_both_halves', 'Team to score in both halves'
        FIRST_TEAM_TO_SCORE = 'first_team_to_score', 'Team to score first'
        LAST_TEAM_TO_SCORE = 'last_team_to_score', 'Team to score last'
        OWN_GOAL = 'own_goal', 'Own goal in match'
        RED_CARD = 'red_card', 'Red card in match'
        ANYTIME_SCORER = 'anytime_scorer', 'Anytime goalscorer'
        FIRST_SCORER = 'first_scorer', 'First goalscorer'
        LAST_SCORER = 'last_scorer', 'Last goalscorer'
        MANUAL = 'manual', 'Manually settled'

    class Metric(models.TextChoices):
        """What a count-based market (1X2, totals, handicaps) counts."""
        GOALS = 'goals', 'Goals'
        CORNERS = 'corners', 'Corners'
        CARDS = 'cards', 'Cards'

    class Period(models.TextChoices):
        FULL_TIME = 'ft', 'Full time'
        FIRST_HALF = '1h', '1st half'
        SECOND_HALF = '2h', '2nd half'

    event = models.ForeignKey('Event', on_delete=models.CASCADE, related_name='markets')
    # Stable identity within an event, e.g. "over_under:ft:2.5" — used to upsert
    # from provider feeds without duplicating markets.
    key = models.CharField(max_length=80)
    name = models.CharField(max_length=120)
    group = models.CharField(max_length=12, choices=Group.choices, default=Group.MAIN)
    kind = models.CharField(max_length=24, choices=Kind.choices, default=Kind.MANUAL)
    period = models.CharField(max_length=2, choices=Period.choices, default=Period.FULL_TIME)
    metric = models.CharField(max_length=8, choices=Metric.choices, default=Metric.GOALS)
    line = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    # Suspended markets stay visible but can't be bet on.
    is_open = models.BooleanField(default=True)
    settled = models.BooleanField(default=False)
    # Set when automatic settlement couldn't decide this market (missing stats,
    # ambiguous scorer name…) so it surfaces for an operator.
    needs_review = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sportsbook_market'
        ordering = ['sort_order', 'line', 'id']
        constraints = [
            models.UniqueConstraint(fields=['event', 'key'], name='unique_market_key_per_event'),
        ]

    def __str__(self) -> str:
        return f'{self.name} ({self.event_id})'


class MarketOutcome(models.Model):
    """A priced selection within a Market ("Over", "Yes", "2:1", "Home/Draw")."""

    class Result(models.TextChoices):
        PENDING = 'pending', 'Pending'
        WON = 'won', 'Won'
        LOST = 'lost', 'Lost'
        VOID = 'void', 'Void'

    market = models.ForeignKey(Market, on_delete=models.CASCADE, related_name='outcomes')
    # Normalised selection used by settlement: 'over', 'yes', 'home', '1x',
    # '2:1', 'draw/home', '3', '7+', …
    key = models.CharField(max_length=40)
    # For goalscorer markets this is the player's name as the bookmaker prints it.
    label = models.CharField(max_length=80)
    odds = models.DecimalField(max_digits=8, decimal_places=2)
    previous_odds = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_open = models.BooleanField(default=True)
    result = models.CharField(max_length=8, choices=Result.choices, default=Result.PENDING)

    class Meta:
        db_table = 'sportsbook_market_outcome'
        ordering = ['sort_order', 'id']
        constraints = [
            models.UniqueConstraint(fields=['market', 'key'], name='unique_outcome_key_per_market'),
        ]

    def __str__(self) -> str:
        return f'{self.label} @ {self.odds}'
