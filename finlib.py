"""
finlib.py - QuantLedger core library
====================================
A zero-dependency (pure standard library) collection of financial algorithms:

  1. Time value of money   : FV, PV, loan payment, NPV, IRR, CAGR, amortization
  2. Fixed income          : bond price, YTM, duration, convexity
  3. Derivatives           : Black-Scholes + Greeks, implied vol, CRR binomial, Monte Carlo
  4. Portfolio theory      : covariance, min-variance, max-Sharpe, efficient frontier
  5. Risk metrics          : Sharpe, Sortino, max drawdown, VaR, CVaR, Kelly, position sizing
  6. Technical indicators  : SMA, EMA, RSI, MACD, Bollinger Bands
  7. Backtesting           : SMA-crossover strategy engine
  8. Trade finance         : landed cost, import profitability, forward FX (covered interest parity)

Educational software. Not financial advice.
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

__all__ = [
    "future_value", "present_value", "loan_payment", "npv", "irr", "cagr",
    "effective_annual_rate", "amortization_schedule",
    "bond_price", "bond_ytm", "bond_duration", "bond_convexity",
    "norm_cdf", "norm_pdf", "norm_ppf", "black_scholes", "implied_volatility",
    "binomial_option", "monte_carlo_option", "Greeks",
    "pct_returns", "cov_matrix", "solve_linear", "min_variance_weights",
    "max_sharpe_weights", "efficient_frontier", "portfolio_stats",
    "sharpe_ratio", "sortino_ratio", "max_drawdown", "historical_var",
    "parametric_var", "cvar", "kelly_fraction", "position_size",
    "sma", "ema", "rsi", "macd", "bollinger",
    "backtest_sma_crossover", "gbm_path",
    "landed_cost", "import_profitability", "forward_fx_rate",
]

# ----------------------------------------------------------------------------
# 1. Time value of money
# ----------------------------------------------------------------------------


def future_value(pv: float, rate: float, n: int, payment: float = 0.0) -> float:
    """Future value of a lump sum plus an end-of-period annuity."""
    if rate == 0:
        return pv + payment * n
    growth = (1 + rate) ** n
    return pv * growth + payment * (growth - 1) / rate


def present_value(fv: float, rate: float, n: int) -> float:
    """Discount a single future amount back to today."""
    return fv / (1 + rate) ** n


def loan_payment(principal: float, rate: float, n: int) -> float:
    """Level payment per period for a fully-amortizing loan."""
    if n <= 0:
        raise ValueError("n must be positive")
    if rate == 0:
        return principal / n
    return principal * rate / (1 - (1 + rate) ** -n)


def npv(rate: float, cashflows: Sequence[float]) -> float:
    """Net present value. cashflows[0] occurs at t=0."""
    return sum(cf / (1 + rate) ** t for t, cf in enumerate(cashflows))


def irr(cashflows: Sequence[float], tol: float = 1e-10, max_iter: int = 500) -> float:
    """Internal rate of return via bisection (robust, needs a sign change)."""
    lo, hi = -0.99, 10.0
    f_lo = npv(lo, cashflows)
    while npv(hi, cashflows) * f_lo > 0 and hi < 1e6:
        hi *= 2
    f_hi = npv(hi, cashflows)
    if f_lo * f_hi > 0:
        raise ValueError("IRR undefined: cashflows need at least one sign change")
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        f_mid = npv(mid, cashflows)
        if abs(f_mid) < tol or (hi - lo) / 2 < tol:
            return mid
        if f_lo * f_mid < 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2


def cagr(start_value: float, end_value: float, years: float) -> float:
    """Compound annual growth rate."""
    return (end_value / start_value) ** (1 / years) - 1


def effective_annual_rate(nominal: float, periods_per_year: int) -> float:
    """Convert a nominal rate with compounding into an effective annual rate."""
    return (1 + nominal / periods_per_year) ** periods_per_year - 1


def amortization_schedule(principal: float, annual_rate: float, years: int,
                          periods_per_year: int = 12) -> List[Dict[str, float]]:
    """Full amortization table: payment, interest, principal, balance."""
    n = years * periods_per_year
    r = annual_rate / periods_per_year
    pay = loan_payment(principal, r, n)
    balance, rows = principal, []
    for k in range(1, n + 1):
        interest = balance * r
        princ = pay - interest
        balance = max(balance - princ, 0.0)
        rows.append({"period": k, "payment": pay, "interest": interest,
                     "principal": princ, "balance": balance})
    return rows


# ----------------------------------------------------------------------------
# 2. Fixed income
# ----------------------------------------------------------------------------


def _bond_flows(face: float, coupon_rate: float, years: float, freq: int):
    n = int(round(years * freq))
    c = face * coupon_rate / freq
    return [(t, c + (face if t == n else 0.0)) for t in range(1, n + 1)]


def bond_price(face: float, coupon_rate: float, ytm: float, years: float, freq: int = 2) -> float:
    """Price of a plain-vanilla coupon bond."""
    y = ytm / freq
    return sum(cf / (1 + y) ** t for t, cf in _bond_flows(face, coupon_rate, years, freq))


def bond_ytm(price: float, face: float, coupon_rate: float, years: float, freq: int = 2) -> float:
    """Yield to maturity by bisection (price is monotone decreasing in yield)."""
    lo, hi = -0.5, 1.0
    while bond_price(face, coupon_rate, hi, years, freq) > price and hi < 100:
        hi *= 2
    for _ in range(300):
        mid = (lo + hi) / 2
        if bond_price(face, coupon_rate, mid, years, freq) > price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def bond_duration(face: float, coupon_rate: float, ytm: float, years: float,
                  freq: int = 2) -> Tuple[float, float]:
    """Return (Macaulay duration in years, modified duration)."""
    y = ytm / freq
    price = bond_price(face, coupon_rate, ytm, years, freq)
    mac = sum((t / freq) * cf / (1 + y) ** t
              for t, cf in _bond_flows(face, coupon_rate, years, freq)) / price
    return mac, mac / (1 + y)


def bond_convexity(face: float, coupon_rate: float, ytm: float, years: float, freq: int = 2) -> float:
    """Convexity in years^2."""
    y = ytm / freq
    price = bond_price(face, coupon_rate, ytm, years, freq)
    total = sum(cf * t * (t + 1) / (1 + y) ** (t + 2)
                for t, cf in _bond_flows(face, coupon_rate, years, freq))
    return total / (price * freq ** 2)


# ----------------------------------------------------------------------------
# 3. Derivatives
# ----------------------------------------------------------------------------


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def norm_ppf(p: float) -> float:
    """Inverse standard normal CDF by bisection."""
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0, 1)")
    lo, hi = -10.0, 10.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if norm_cdf(mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


@dataclass
class Greeks:
    price: float
    delta: float
    gamma: float
    vega: float   # per 1 percentage-point change in volatility
    theta: float  # per calendar day
    rho: float    # per 1 percentage-point change in rate


def black_scholes(spot: float, strike: float, t: float, rate: float, vol: float,
                  kind: str = "call", div: float = 0.0) -> Greeks:
    """European option price and Greeks (Black-Scholes-Merton with dividend yield)."""
    kind = kind.lower()
    if kind not in ("call", "put"):
        raise ValueError("kind must be 'call' or 'put'")
    if t <= 0 or vol <= 0:
        intrinsic = max(spot - strike, 0.0) if kind == "call" else max(strike - spot, 0.0)
        return Greeks(intrinsic, 0.0, 0.0, 0.0, 0.0, 0.0)
    sq = vol * math.sqrt(t)
    d1 = (math.log(spot / strike) + (rate - div + 0.5 * vol * vol) * t) / sq
    d2 = d1 - sq
    disc_r, disc_q = math.exp(-rate * t), math.exp(-div * t)
    pdf1 = norm_pdf(d1)
    gamma = disc_q * pdf1 / (spot * sq)
    vega = spot * disc_q * pdf1 * math.sqrt(t)
    if kind == "call":
        price = spot * disc_q * norm_cdf(d1) - strike * disc_r * norm_cdf(d2)
        delta = disc_q * norm_cdf(d1)
        theta = (-spot * disc_q * pdf1 * vol / (2 * math.sqrt(t))
                 - rate * strike * disc_r * norm_cdf(d2) + div * spot * disc_q * norm_cdf(d1))
        rho = strike * t * disc_r * norm_cdf(d2)
    else:
        price = strike * disc_r * norm_cdf(-d2) - spot * disc_q * norm_cdf(-d1)
        delta = disc_q * (norm_cdf(d1) - 1)
        theta = (-spot * disc_q * pdf1 * vol / (2 * math.sqrt(t))
                 + rate * strike * disc_r * norm_cdf(-d2) - div * spot * disc_q * norm_cdf(-d1))
        rho = -strike * t * disc_r * norm_cdf(-d2)
    return Greeks(price, delta, gamma, vega / 100, theta / 365, rho / 100)


def implied_volatility(market_price: float, spot: float, strike: float, t: float,
                       rate: float, kind: str = "call", div: float = 0.0) -> float:
    """Solve for the volatility that reproduces a market option price (bisection)."""
    lo, hi = 1e-6, 5.0
    if not black_scholes(spot, strike, t, rate, lo, kind, div).price <= market_price <= \
            black_scholes(spot, strike, t, rate, hi, kind, div).price:
        raise ValueError("market price outside the attainable Black-Scholes range")
    for _ in range(200):
        mid = (lo + hi) / 2
        if black_scholes(spot, strike, t, rate, mid, kind, div).price < market_price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def binomial_option(spot: float, strike: float, t: float, rate: float, vol: float,
                    kind: str = "call", steps: int = 500, american: bool = False,
                    div: float = 0.0) -> float:
    """Cox-Ross-Rubinstein binomial tree; supports American early exercise."""
    dt = t / steps
    u = math.exp(vol * math.sqrt(dt))
    d = 1 / u
    p = (math.exp((rate - div) * dt) - d) / (u - d)
    disc = math.exp(-rate * dt)
    sign = 1 if kind == "call" else -1
    values = [max(sign * (spot * u ** j * d ** (steps - j) - strike), 0.0)
              for j in range(steps + 1)]
    for i in range(steps - 1, -1, -1):
        for j in range(i + 1):
            cont = disc * (p * values[j + 1] + (1 - p) * values[j])
            if american:
                cont = max(cont, sign * (spot * u ** j * d ** (i - j) - strike))
            values[j] = cont
    return values[0]


def monte_carlo_option(spot: float, strike: float, t: float, rate: float, vol: float,
                       kind: str = "call", paths: int = 50_000, seed: Optional[int] = 42,
                       div: float = 0.0) -> Tuple[float, float]:
    """Monte Carlo price with antithetic variates. Returns (price, standard error)."""
    rng = random.Random(seed)
    drift = (rate - div - 0.5 * vol * vol) * t
    diff = vol * math.sqrt(t)
    sign = 1 if kind == "call" else -1
    payoffs = []
    for _ in range(paths // 2):
        z = rng.gauss(0, 1)
        for zz in (z, -z):
            st = spot * math.exp(drift + diff * zz)
            payoffs.append(max(sign * (st - strike), 0.0))
    disc = math.exp(-rate * t)
    mean = statistics.fmean(payoffs)
    se = statistics.stdev(payoffs) / math.sqrt(len(payoffs))
    return disc * mean, disc * se


# ----------------------------------------------------------------------------
# 4. Portfolio theory
# ----------------------------------------------------------------------------


def pct_returns(prices: Sequence[float]) -> List[float]:
    """Simple period-over-period returns."""
    return [prices[i] / prices[i - 1] - 1 for i in range(1, len(prices))]


def cov_matrix(returns_by_asset: Sequence[Sequence[float]]) -> List[List[float]]:
    """Sample covariance matrix from per-asset return series."""
    n = len(returns_by_asset)
    means = [statistics.fmean(r) for r in returns_by_asset]
    m = len(returns_by_asset[0])
    return [[sum((returns_by_asset[i][k] - means[i]) * (returns_by_asset[j][k] - means[j])
                 for k in range(m)) / (m - 1) for j in range(n)] for i in range(n)]


def solve_linear(a: List[List[float]], b: List[float]) -> List[float]:
    """Solve A x = b by Gaussian elimination with partial pivoting."""
    n = len(a)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) < 1e-14:
            raise ValueError("singular matrix")
        m[col], m[pivot] = m[pivot], m[col]
        for r in range(col + 1, n):
            f = m[r][col] / m[col][col]
            for c in range(col, n + 1):
                m[r][c] -= f * m[col][c]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (m[i][n] - sum(m[i][j] * x[j] for j in range(i + 1, n))) / m[i][i]
    return x


def _weights_from_direction(cov: List[List[float]], vec: List[float], allow_short: bool) -> List[float]:
    """w proportional to inv(cov) @ vec. Long-only uses an active-set heuristic:
    repeatedly drop the most negative asset and re-solve."""
    n = len(cov)
    active = list(range(n))
    while True:
        sub = [[cov[i][j] for j in active] for i in active]
        x = solve_linear(sub, [vec[i] for i in active])
        total = sum(x)
        if total <= 0:
            raise ValueError("no feasible portfolio (all excess returns non-positive)")
        w = [xi / total for xi in x]
        if allow_short or min(w) >= -1e-12 or len(active) == 1:
            break
        active.pop(min(range(len(w)), key=lambda k: w[k]))
    full = [0.0] * n
    for k, i in enumerate(active):
        full[i] = max(w[k], 0.0) if not allow_short else w[k]
    s = sum(full)
    return [x / s for x in full]


def min_variance_weights(cov: List[List[float]], allow_short: bool = False) -> List[float]:
    """Global minimum-variance portfolio."""
    return _weights_from_direction(cov, [1.0] * len(cov), allow_short)


def max_sharpe_weights(mu: Sequence[float], cov: List[List[float]], rf: float = 0.0,
                       allow_short: bool = False) -> List[float]:
    """Tangency (maximum Sharpe ratio) portfolio."""
    return _weights_from_direction(cov, [m - rf for m in mu], allow_short)


def portfolio_stats(weights: Sequence[float], mu: Sequence[float],
                    cov: List[List[float]], rf: float = 0.0) -> Dict[str, float]:
    """Expected return, volatility and Sharpe for given weights (same time unit as mu/cov)."""
    n = len(weights)
    ret = sum(weights[i] * mu[i] for i in range(n))
    var = sum(weights[i] * weights[j] * cov[i][j] for i in range(n) for j in range(n))
    vol = math.sqrt(max(var, 0.0))
    return {"return": ret, "vol": vol, "sharpe": (ret - rf) / vol if vol > 0 else 0.0}


def efficient_frontier(mu: Sequence[float], cov: List[List[float]], points: int = 2000,
                       seed: int = 7) -> List[Tuple[float, float]]:
    """Random long-only portfolios reduced to the upper (efficient) envelope.
    Returns (volatility, return) pairs sorted by volatility."""
    rng = random.Random(seed)
    n = len(mu)
    cloud = []
    for _ in range(points):
        raw = [rng.expovariate(1.0) for _ in range(n)]
        s = sum(raw)
        w = [x / s for x in raw]
        st = portfolio_stats(w, mu, cov)
        cloud.append((st["vol"], st["return"]))
    cloud.sort()
    frontier, best = [], -math.inf
    for vol, ret in cloud:
        if ret > best:
            frontier.append((vol, ret))
            best = ret
    return frontier


# ----------------------------------------------------------------------------
# 5. Risk metrics
# ----------------------------------------------------------------------------


def sharpe_ratio(returns: Sequence[float], rf_per_period: float = 0.0, periods: int = 252) -> float:
    ex = [r - rf_per_period for r in returns]
    sd = statistics.stdev(ex)
    return statistics.fmean(ex) / sd * math.sqrt(periods) if sd > 0 else 0.0


def sortino_ratio(returns: Sequence[float], rf_per_period: float = 0.0, periods: int = 252) -> float:
    ex = [r - rf_per_period for r in returns]
    downside = math.sqrt(sum(min(x, 0.0) ** 2 for x in ex) / len(ex))
    return statistics.fmean(ex) / downside * math.sqrt(periods) if downside > 0 else 0.0


def max_drawdown(series: Sequence[float]) -> float:
    """Largest peak-to-trough decline, as a positive fraction."""
    peak, worst = series[0], 0.0
    for v in series:
        peak = max(peak, v)
        worst = max(worst, (peak - v) / peak)
    return worst


def historical_var(returns: Sequence[float], confidence: float = 0.95) -> float:
    """Historical Value-at-Risk as a positive loss fraction."""
    ordered = sorted(returns)
    idx = max(int((1 - confidence) * len(ordered)) - 1, 0)
    return -ordered[idx]


def parametric_var(returns: Sequence[float], confidence: float = 0.95) -> float:
    """Gaussian (variance-covariance) VaR."""
    mu, sd = statistics.fmean(returns), statistics.stdev(returns)
    return -(mu + norm_ppf(1 - confidence) * sd)


def cvar(returns: Sequence[float], confidence: float = 0.95) -> float:
    """Expected shortfall: average loss beyond the VaR threshold."""
    ordered = sorted(returns)
    k = max(int((1 - confidence) * len(ordered)), 1)
    return -statistics.fmean(ordered[:k])


def kelly_fraction(win_prob: float, win_loss_ratio: float) -> float:
    """Kelly criterion: optimal fraction of capital to risk per bet."""
    return win_prob - (1 - win_prob) / win_loss_ratio


def position_size(capital: float, risk_pct: float, entry: float, stop: float) -> float:
    """Units to buy so that hitting the stop loses exactly risk_pct of capital."""
    per_unit = abs(entry - stop)
    if per_unit == 0:
        raise ValueError("entry and stop must differ")
    return capital * risk_pct / per_unit


# ----------------------------------------------------------------------------
# 6. Technical indicators (None-padded so they align with the input series)
# ----------------------------------------------------------------------------


def sma(values: Sequence[float], n: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(values)
    window = 0.0
    for i, v in enumerate(values):
        window += v
        if i >= n:
            window -= values[i - n]
        if i >= n - 1:
            out[i] = window / n
    return out


def ema(values: Sequence[float], n: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(values)
    if len(values) < n:
        return out
    alpha = 2 / (n + 1)
    prev = sum(values[:n]) / n
    out[n - 1] = prev
    for i in range(n, len(values)):
        prev = alpha * values[i] + (1 - alpha) * prev
        out[i] = prev
    return out


def rsi(values: Sequence[float], n: int = 14) -> List[Optional[float]]:
    """Relative Strength Index with Wilder smoothing."""
    out: List[Optional[float]] = [None] * len(values)
    if len(values) <= n:
        return out
    gains = [max(values[i] - values[i - 1], 0.0) for i in range(1, len(values))]
    losses = [max(values[i - 1] - values[i], 0.0) for i in range(1, len(values))]
    avg_g, avg_l = sum(gains[:n]) / n, sum(losses[:n]) / n
    for i in range(n, len(values)):
        if i > n:
            avg_g = (avg_g * (n - 1) + gains[i - 1]) / n
            avg_l = (avg_l * (n - 1) + losses[i - 1]) / n
        out[i] = 100.0 if avg_l == 0 else 100 - 100 / (1 + avg_g / avg_l)
    return out


def macd(values: Sequence[float], fast: int = 12, slow: int = 26, signal: int = 9):
    """Returns (macd_line, signal_line, histogram), each aligned to the input."""
    ef, es = ema(values, fast), ema(values, slow)
    line: List[Optional[float]] = [a - b if a is not None and b is not None else None
                                   for a, b in zip(ef, es)]
    first = next((i for i, v in enumerate(line) if v is not None), None)
    sig: List[Optional[float]] = [None] * len(values)
    if first is not None:
        tail = ema([v for v in line[first:]], signal)
        for k, v in enumerate(tail):
            sig[first + k] = v
    hist = [a - b if a is not None and b is not None else None for a, b in zip(line, sig)]
    return line, sig, hist


def bollinger(values: Sequence[float], n: int = 20, k: float = 2.0):
    """Returns (middle, upper, lower) bands using population standard deviation."""
    mid = sma(values, n)
    up: List[Optional[float]] = [None] * len(values)
    lo: List[Optional[float]] = [None] * len(values)
    for i in range(n - 1, len(values)):
        sd = statistics.pstdev(values[i - n + 1:i + 1])
        up[i], lo[i] = mid[i] + k * sd, mid[i] - k * sd
    return mid, up, lo


# ----------------------------------------------------------------------------
# 7. Backtesting and synthetic data
# ----------------------------------------------------------------------------


def gbm_path(s0: float, mu: float, sigma: float, steps: int, dt: float = 1 / 252,
             seed: Optional[int] = 1) -> List[float]:
    """Geometric Brownian Motion price path (reproducible via seed)."""
    rng = random.Random(seed)
    path = [s0]
    for _ in range(steps):
        z = rng.gauss(0, 1)
        path.append(path[-1] * math.exp((mu - 0.5 * sigma ** 2) * dt + sigma * math.sqrt(dt) * z))
    return path


def backtest_sma_crossover(prices: Sequence[float], fast: int = 20, slow: int = 50,
                           cost_bps: float = 5.0, periods: int = 252) -> Dict[str, object]:
    """Long when fast SMA > slow SMA, otherwise cash. Signals use the prior bar
    (no look-ahead). Transaction cost is charged on every position change."""
    if fast >= slow:
        raise ValueError("fast window must be smaller than slow window")
    f, s = sma(prices, fast), sma(prices, slow)
    equity, pos, trades = [1.0], 0, 0
    rets = []
    for i in range(1, len(prices)):
        want = 1 if (f[i - 1] is not None and s[i - 1] is not None and f[i - 1] > s[i - 1]) else 0
        r = pos * (prices[i] / prices[i - 1] - 1)
        if want != pos:
            r -= cost_bps / 10_000
            trades += 1
            pos = want
        rets.append(r)
        equity.append(equity[-1] * (1 + r))
    years = len(rets) / periods
    return {
        "equity": equity,
        "total_return": equity[-1] - 1,
        "cagr": equity[-1] ** (1 / years) - 1 if years > 0 and equity[-1] > 0 else float("nan"),
        "sharpe": sharpe_ratio(rets, periods=periods),
        "max_drawdown": max_drawdown(equity),
        "trades": trades,
        "buy_hold_return": prices[-1] / prices[0] - 1,
    }


# ----------------------------------------------------------------------------
# 8. Trade finance
# ----------------------------------------------------------------------------


def landed_cost(fob_price: float, quantity: float, freight: float = 0.0,
                insurance_rate: float = 0.0, duty_rate: float = 0.0,
                tax_rate: float = 0.0, other_costs: float = 0.0) -> Dict[str, float]:
    """Total cost of importing goods, all in one currency.
    CIF = FOB value + freight + insurance; duty on CIF; sales tax on (CIF + duty)."""
    fob_value = fob_price * quantity
    insurance = insurance_rate * (fob_value + freight)
    cif = fob_value + freight + insurance
    duty = duty_rate * cif
    tax = tax_rate * (cif + duty)
    total = cif + duty + tax + other_costs
    return {"fob_value": fob_value, "freight": freight, "insurance": insurance, "cif": cif,
            "duty": duty, "tax": tax, "other": other_costs, "total": total,
            "per_unit": total / quantity}


def import_profitability(landed_total: float, quantity: float, selling_price_per_unit: float,
                         financing_rate: float = 0.0, days_to_sell: int = 0) -> Dict[str, float]:
    """Profit, margin, markup and break-even price including cost of carrying inventory."""
    carry = landed_total * financing_rate * days_to_sell / 365
    cost = landed_total + carry
    revenue = selling_price_per_unit * quantity
    profit = revenue - cost
    return {"revenue": revenue, "financing_cost": carry, "total_cost": cost, "profit": profit,
            "margin": profit / revenue if revenue else 0.0,
            "markup": profit / cost if cost else 0.0,
            "break_even_price": cost / quantity}


def forward_fx_rate(spot: float, domestic_rate: float, foreign_rate: float, years: float) -> float:
    """Covered interest parity. spot is quoted as domestic currency per 1 foreign unit."""
    return spot * (1 + domestic_rate * years) / (1 + foreign_rate * years)
