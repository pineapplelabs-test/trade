"""Quantitative 5-Level Market Depth & Order Book Indicators."""

from app.feed.base import OrderBookDepth


def calculate_obi(depth: OrderBookDepth) -> float:
    """Calculate 5-level Order Book Imbalance (OBI).

    OBI = (sum(bidQty) - sum(askQty)) / (sum(bidQty) + sum(askQty))
    Values range from -1.0 (pure selling pressure) to +1.0 (pure buying pressure).
    """
    total_bid_qty = sum(b.quantity for b in depth.bids[:5])
    total_ask_qty = sum(a.quantity for a in depth.asks[:5])
    total_qty = total_bid_qty + total_ask_qty

    if total_qty == 0:
        return 0.0

    raw_obi = (total_bid_qty - total_ask_qty) / float(total_qty)
    return max(-1.0, min(1.0, raw_obi))


def calculate_microprice(depth: OrderBookDepth) -> float:
    """Calculate top-of-book Microprice.

    Microprice = (Ask1 * BidQty1 + Bid1 * AskQty1) / (BidQty1 + AskQty1)
    Weights the opposite side's price by current queue depth, predicting near-term fair value.
    """
    if not depth.bids or not depth.asks:
        return depth.mid_price

    best_bid = depth.bids[0]
    best_ask = depth.asks[0]
    total_l1_qty = best_bid.quantity + best_ask.quantity

    if total_l1_qty == 0:
        return depth.mid_price

    return (best_ask.price * best_bid.quantity + best_bid.price * best_ask.quantity) / float(total_l1_qty)


def calculate_depth_pressure(depth: OrderBookDepth) -> float:
    """Calculate linearly weighted order book depth pressure across 5 levels.

    Weights top levels higher [5, 4, 3, 2, 1] to reflect immediate execution impact.
    """
    weights = [5, 4, 3, 2, 1]
    weighted_bids = sum(b.quantity * w for b, w in zip(depth.bids[:5], weights, strict=False))
    weighted_asks = sum(a.quantity * w for a, w in zip(depth.asks[:5], weights, strict=False))
    total_weighted = weighted_bids + weighted_asks

    if total_weighted == 0:
        return 0.0

    return max(-1.0, min(1.0, (weighted_bids - weighted_asks) / float(total_weighted)))
