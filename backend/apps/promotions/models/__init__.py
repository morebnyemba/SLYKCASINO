"""promotions schema — promotion catalog and per-player claims. No logic here."""
from .claim import PromotionClaim
from .promotion import Promotion

__all__ = ['Promotion', 'PromotionClaim']
