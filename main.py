#!/usr/bin/env python3
"""
main.py - QuantLedger command-line interface
============================================

Usage examples:
    python main.py demo
    python main.py selftest
    python main.py loan --principal 5000000 --rate 0.12 --years 5 --schedule 6
    python main.py bond --face 1000 --coupon 0.06 --ytm 0.07 --years 10
    python main.py option --spot 100 --strike 105 --time 0.5 --rate 0.05 --vol 0.25 --type call
    python main.py portfolio [--csv prices.csv]
    python main.py backtest [--csv prices.csv] --fast 20 --slow 50
    python main.py trade --fob 12.5 --qty 4000 --freight 3500 --duty 0.20 --tax 0.18 --sell 28

CSV format: header row with ticker names, then one row of prices per period.
"""

from __future__ import annotations

import argparse
import csv
import math
import statistics
import sys
from typing import List, Tuple

import finlib as fl

LINE = "=" * 72


def banner(title: str) -> None:
    print(f"\n{LINE}\n  {title}\n{LINE}")


def money(x: float) -> str:
    return f"{x:,.2f}"


def pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def sparkline(values: List[float], width: int = 60) -> str:
    """Tiny text chart so results are visible without any plotting library."""
    blocks = "▁▂▃▄▅▆▇█"
    step = max(len(values) // width, 1)
    pts = values[::step]
    lo, hi = min(pts), max(pts)
    span = (hi - lo) or 1.0
    return "".join(blocks[min(int((v - lo) / span * (len(blocks) - 1)), len(blocks) - 1)] for v in pts)


def load_prices(path: str) -> Tuple[List[str], List[List[float]]]:
    with open(path, newline="") as fh:
        rows = list(csv.reader(fh))
    names = rows[0]
    cols = [[float(r[i]) for r in rows[1:] if r] for i in range(len(names))]
    return names, cols


# ----------------------------------------------------------------------------
# Command implementations
# ----------------------------------------------------------------------------


def cmd_loan(a) -> None:
    banner("LOAN / TIME VALUE OF MONEY")
    r = a.rate / 12
    pay = fl.loan_payment(a.principal, r, a.years * 12)
    total = pay * a.years * 12
    print(f"Principal          : {money(a.principal)}")
    print(f"Monthly payment    : {money(pay)}")
    print(f"Total paid         : {money(total)}")
    print(f"Total interest     : {money(total - a.principal)}")
    print(f"Effective annual   : {pct(fl.effective_annual_rate(a.rate, 12))}")
    if a.schedule:
        print(f"\n{'Month':>5} {'Payment':>14} {'Interest':>14} {'Principal':>14} {'Balance':>16}")
        for row in fl.amortization_schedule(a.principal, a.rate, a.years)[:a.schedule]:
            print(f"{row['period']:>5} {money(row['payment']):>14} {money(row['interest']):>14} "
                  f"{money(row['principal']):>14} {money(row['balance']):>16}")


def cmd_bond(a) -> None:
    banner("FIXED INCOME")
    price = fl.bond_price(a.face, a.coupon, a.ytm, a.years, a.freq)
    mac, mod = fl.bond_duration(a.face, a.coupon, a.ytm, a.years, a.freq)
    conv = fl.bond_convexity(a.face, a.coupon, a.ytm, a.years, a.freq)
    print(f"Price                : {money(price)}  ({'premium' if price > a.face else 'discount' if price < a.face else 'par'})")
    print(f"Yield (check)        : {pct(fl.bond_ytm(price, a.face, a.coupon, a.years, a.freq))}")
    print(f"Macaulay duration    : {mac:.4f} years")
    print(f"Modified duration    : {mod:.4f}")
    print(f"Convexity            : {conv:.4f}")
    shock = 0.01
    est = price * (-mod * shock + 0.5 * conv * shock ** 2)
    act = fl.bond_price(a.face, a.coupon, a.ytm + shock, a.years, a.freq) - price
    print(f"+100bp yield shock   : estimated {est:+.2f} | exact {act:+.2f}")


def cmd_option(a) -> None:
    banner("OPTIONS")
    g = fl.black_scholes(a.spot, a.strike, a.time, a.rate, a.vol, a.type, a.div)
    bin_eu = fl.binomial_option(a.spot, a.strike, a.time, a.rate, a.vol, a.type, 400, False, a.div)
    bin_am = fl.binomial_option(a.spot, a.strike, a.time, a.rate, a.vol, a.type, 400, True, a.div)
    mc, se = fl.monte_carlo_option(a.spot, a.strike, a.time, a.rate, a.vol, a.type, div=a.div)
    print(f"Black-Scholes price  : {g.price:.4f}")
    print(f"Binomial (European)  : {bin_eu:.4f}")
    print(f"Binomial (American)  : {bin_am:.4f}")
    print(f"Monte Carlo          : {mc:.4f}  (+/- {1.96 * se:.4f} at 95%)")
    print(f"Delta {g.delta:+.4f} | Gamma {g.gamma:.5f} | Vega {g.vega:.4f} | "
          f"Theta/day {g.theta:+.4f} | Rho {g.rho:+.4f}")
    iv = fl.implied_volatility(g.price, a.spot, a.strike, a.time, a.rate, a.type, a.div)
    print(f"Implied vol (check)  : {pct(iv)}")


def _synthetic_universe(days: int = 756):
    names = ["TECH", "BANK", "TRADE", "ENERGY"]
    params = [(0.18, 0.30), (0.10, 0.18), (0.12, 0.22), (0.08, 0.25)]
    cols = [fl.gbm_path(100, mu, sg, days, seed=11 + i) for i, (mu, sg) in enumerate(params)]
    return names, cols


def cmd_portfolio(a) -> None:
    banner("PORTFOLIO OPTIMISATION")
    names, cols = load_prices(a.csv) if a.csv else _synthetic_universe()
    if not a.csv:
        print("(using reproducible synthetic prices; pass --csv to use your own)")
    rets = [fl.pct_returns(c) for c in cols]
    mu = [statistics.fmean(r) * 252 for r in rets]
    cov = [[x * 252 for x in row] for row in fl.cov_matrix(rets)]
    rf = a.rf
    mv = fl.min_variance_weights(cov)
    ms = fl.max_sharpe_weights(mu, cov, rf)
    eq = [1 / len(names)] * len(names)
    print(f"{'Asset':<8} {'Ann.Ret':>9} {'Ann.Vol':>9} {'MinVar':>9} {'MaxSharpe':>10}")
    for i, n in enumerate(names):
        print(f"{n:<8} {pct(mu[i]):>9} {pct(math.sqrt(cov[i][i])):>9} {pct(mv[i]):>9} {pct(ms[i]):>10}")
    print()
    for label, w in (("Equal weight", eq), ("Min variance", mv), ("Max Sharpe", ms)):
        s = fl.portfolio_stats(w, mu, cov, rf)
        print(f"{label:<13} return {pct(s['return']):>8} | vol {pct(s['vol']):>7} | Sharpe {s['sharpe']:.3f}")
    port = [sum(ms[i] * rets[i][k] for i in range(len(names))) for k in range(len(rets[0]))]
    print(f"\nMax-Sharpe portfolio daily risk: 95% VaR {pct(fl.historical_var(port))} | "
          f"CVaR {pct(fl.cvar(port))} | parametric VaR {pct(fl.parametric_var(port))}")
    front = fl.efficient_frontier(mu, cov)
    print(f"Efficient frontier points found: {len(front)}")


def cmd_backtest(a) -> None:
    banner("BACKTEST: SMA CROSSOVER")
    if a.csv:
        _, cols = load_prices(a.csv)
        prices = cols[0]
    else:
        prices = fl.gbm_path(100, 0.12, 0.25, 1260, seed=5)
        print("(using reproducible synthetic prices; pass --csv to use your own)")
    res = fl.backtest_sma_crossover(prices, a.fast, a.slow, a.cost)
    print(f"Strategy return      : {pct(res['total_return'])}   (buy & hold {pct(res['buy_hold_return'])})")
    print(f"CAGR                 : {pct(res['cagr'])}")
    print(f"Sharpe ratio         : {res['sharpe']:.3f}")
    print(f"Max drawdown         : {pct(res['max_drawdown'])}")
    print(f"Trades               : {res['trades']}")
    print(f"Equity curve         : {sparkline(res['equity'])}")
    print(f"Price                : {sparkline(list(prices))}")
    rs = fl.rsi(prices)[-1]
    line, sig, hist = fl.macd(prices)
    _, up, lo = fl.bollinger(prices)
    print(f"\nLatest indicators    : RSI {rs:.1f} | MACD {line[-1]:+.3f} (signal {sig[-1]:+.3f}) | "
          f"Bollinger [{lo[-1]:.2f}, {up[-1]:.2f}] vs price {prices[-1]:.2f}")


def cmd_trade(a) -> None:
    banner("IMPORT / EXPORT TRADE COSTING")
    lc = fl.landed_cost(a.fob, a.qty, a.freight, a.insurance, a.duty, a.tax, a.other)
    for k in ("fob_value", "freight", "insurance", "cif", "duty", "tax", "other", "total"):
        print(f"{k.replace('_', ' ').title():<12}: {money(lc[k]):>16}")
    print(f"{'Per unit':<12}: {money(lc['per_unit']):>16}")
    if a.sell:
        p = fl.import_profitability(lc["total"], a.qty, a.sell, a.financing, a.days)
        print(f"\nRevenue      : {money(p['revenue'])}\nCarry cost   : {money(p['financing_cost'])}\n"
              f"Profit       : {money(p['profit'])}\nMargin       : {pct(p['margin'])}\n"
              f"Markup       : {pct(p['markup'])}\nBreak-even   : {money(p['break_even_price'])} per unit")
    if a.spot:
        f = fl.forward_fx_rate(a.spot, a.dom_rate, a.for_rate, a.fx_years)
        print(f"\nForward FX ({a.fx_years}y) : {f:.4f} (spot {a.spot:.4f}, CIP)")


def cmd_demo(_a) -> None:
    banner("QUANTLEDGER DEMO  -  every module in one run")
    pay = fl.loan_payment(1_000_000, 0.10 / 12, 60)
    print(f"[TVM]  1,000,000 loan @10% for 5y -> monthly {money(pay)} | "
          f"IRR of [-100,30,40,50,60] = {pct(fl.irr([-100, 30, 40, 50, 60]))} | "
          f"NPV@8% = {fl.npv(0.08, [-100, 30, 40, 50, 60]):.2f}")
    price = fl.bond_price(1000, 0.06, 0.07, 10)
    mac, mod = fl.bond_duration(1000, 0.06, 0.07, 10)
    print(f"[BOND] 10y 6% coupon @7% yield -> price {money(price)} | duration {mac:.3f}y | "
          f"modified {mod:.3f} | convexity {fl.bond_convexity(1000, 0.06, 0.07, 10):.2f}")
    g = fl.black_scholes(100, 105, 0.5, 0.05, 0.25, "call")
    print(f"[OPT]  call S=100 K=105 T=0.5 -> {g.price:.4f} | delta {g.delta:.3f} gamma {g.gamma:.4f} "
          f"vega {g.vega:.3f} theta/day {g.theta:.3f}")
    print(f"[OPT]  American put S=100 K=105 -> {fl.binomial_option(100, 105, 0.5, 0.05, 0.25, 'put', 300, True):.4f}")
    print(f"[RISK] Kelly(p=0.55, b=1.5) = {pct(fl.kelly_fraction(0.55, 1.5))} | "
          f"size for 1% risk on 100k, entry 50 stop 47 = {fl.position_size(100_000, 0.01, 50, 47):.0f} units")
    cmd_portfolio(argparse.Namespace(csv=None, rf=0.03))
    cmd_backtest(argparse.Namespace(csv=None, fast=20, slow=50, cost=5.0))
    cmd_trade(argparse.Namespace(fob=12.5, qty=4000, freight=3500, insurance=0.01, duty=0.20,
                                 tax=0.18, other=1200, sell=28, financing=0.15, days=45,
                                 spot=280.0, dom_rate=0.12, for_rate=0.05, fx_years=0.5))


# ----------------------------------------------------------------------------
# Self-test: checks the library against known textbook values
# ----------------------------------------------------------------------------


def cmd_selftest(_a) -> int:
    banner("SELF-TEST")
    checks = []

    def check(name: str, got: float, want: float, tol: float = 1e-3) -> None:
        ok = abs(got - want) <= tol
        checks.append(ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {name:<46} got {got:>12.4f} want {want:>12.4f}")

    check("FV of 1000 @5% for 10y", fl.future_value(1000, 0.05, 10), 1628.8946)
    check("Loan payment 200k @6%/12 x360", fl.loan_payment(200_000, 0.06 / 12, 360), 1199.1010)
    check("IRR [-100, 110]", fl.irr([-100, 110]), 0.10, 1e-6)
    check("NPV @10% of [-100, 110]", fl.npv(0.10, [-100, 110]), 0.0, 1e-9)
    check("Par bond prices at par", fl.bond_price(100, 0.05, 0.05, 10), 100.0, 1e-9)
    check("YTM round trip", fl.bond_ytm(fl.bond_price(1000, 0.06, 0.07, 10), 1000, 0.06, 10), 0.07, 1e-8)
    check("Black-Scholes call (100,100,1,5%,20%)", fl.black_scholes(100, 100, 1, 0.05, 0.2, "call").price, 10.4506)
    check("Black-Scholes put  (100,100,1,5%,20%)", fl.black_scholes(100, 100, 1, 0.05, 0.2, "put").price, 5.5735)
    c = fl.black_scholes(100, 95, 0.75, 0.04, 0.3, "call").price
    p = fl.black_scholes(100, 95, 0.75, 0.04, 0.3, "put").price
    check("Put-call parity", c - p, 100 - 95 * math.exp(-0.04 * 0.75), 1e-9)
    check("Implied vol round trip", fl.implied_volatility(10.4506, 100, 100, 1, 0.05), 0.20, 1e-4)
    check("Binomial -> BS (400 steps)", fl.binomial_option(100, 100, 1, 0.05, 0.2, "call", 400), 10.4506, 0.02)
    mc, se = fl.monte_carlo_option(100, 100, 1, 0.05, 0.2, "call", paths=100_000)
    check("Monte Carlo within 4 std errors", mc, 10.4506, 4 * se)
    check("Normal inverse CDF(0.975)", fl.norm_ppf(0.975), 1.95996, 1e-4)
    check("Solve 2x2 linear system", fl.solve_linear([[2, 1], [1, 3]], [5, 10])[0], 1.0, 1e-9)
    cov = [[0.04, 0.0], [0.0, 0.01]]
    check("Min-variance weight on low-vol asset", fl.min_variance_weights(cov)[1], 0.8, 1e-9)
    check("Max drawdown [100,120,60,90]", fl.max_drawdown([100, 120, 60, 90]), 0.5, 1e-12)
    check("Kelly p=0.6 b=1", fl.kelly_fraction(0.6, 1.0), 0.2, 1e-12)
    check("SMA(3) of 1..5 last", fl.sma([1, 2, 3, 4, 5], 3)[-1], 4.0, 1e-12)
    check("RSI of strictly rising series", fl.rsi([float(i) for i in range(1, 40)])[-1], 100.0, 1e-9)
    check("Forward FX (CIP)", fl.forward_fx_rate(280, 0.12, 0.05, 1.0), 280 * 1.12 / 1.05, 1e-9)
    lc = fl.landed_cost(10, 100, freight=100, duty_rate=0.10)
    check("Landed cost: 1000 FOB +100 freight +10% duty", lc["total"], 1210.0, 1e-9)

    failed = checks.count(False)
    print(f"\n{len(checks) - failed}/{len(checks)} checks passed")
    return 1 if failed else 0


# ----------------------------------------------------------------------------
# Argument parsing
# ----------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="quantledger", description="Financial algorithms toolkit")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("demo", help="run every module with sample data").set_defaults(fn=cmd_demo)
    sub.add_parser("selftest", help="verify algorithms against known values").set_defaults(fn=cmd_selftest)

    s = sub.add_parser("loan", help="loan payment and amortization")
    s.add_argument("--principal", type=float, required=True)
    s.add_argument("--rate", type=float, required=True, help="annual rate, e.g. 0.12")
    s.add_argument("--years", type=int, required=True)
    s.add_argument("--schedule", type=int, default=0, help="print first N schedule rows")
    s.set_defaults(fn=cmd_loan)

    s = sub.add_parser("bond", help="bond price, duration, convexity")
    s.add_argument("--face", type=float, default=1000)
    s.add_argument("--coupon", type=float, required=True)
    s.add_argument("--ytm", type=float, required=True)
    s.add_argument("--years", type=float, required=True)
    s.add_argument("--freq", type=int, default=2)
    s.set_defaults(fn=cmd_bond)

    s = sub.add_parser("option", help="option pricing and Greeks")
    s.add_argument("--spot", type=float, required=True)
    s.add_argument("--strike", type=float, required=True)
    s.add_argument("--time", type=float, required=True, help="years to expiry")
    s.add_argument("--rate", type=float, required=True)
    s.add_argument("--vol", type=float, required=True)
    s.add_argument("--div", type=float, default=0.0)
    s.add_argument("--type", choices=["call", "put"], default="call")
    s.set_defaults(fn=cmd_option)

    s = sub.add_parser("portfolio", help="min-variance / max-Sharpe optimisation")
    s.add_argument("--csv", help="CSV of prices, one column per asset")
    s.add_argument("--rf", type=float, default=0.03, help="annual risk-free rate")
    s.set_defaults(fn=cmd_portfolio)

    s = sub.add_parser("backtest", help="SMA crossover backtest and indicators")
    s.add_argument("--csv", help="CSV of prices (first column is used)")
    s.add_argument("--fast", type=int, default=20)
    s.add_argument("--slow", type=int, default=50)
    s.add_argument("--cost", type=float, default=5.0, help="cost per trade in basis points")
    s.set_defaults(fn=cmd_backtest)

    s = sub.add_parser("trade", help="landed cost, profitability, forward FX")
    s.add_argument("--fob", type=float, required=True, help="FOB price per unit")
    s.add_argument("--qty", type=float, required=True)
    s.add_argument("--freight", type=float, default=0.0)
    s.add_argument("--insurance", type=float, default=0.0, help="insurance rate, e.g. 0.01")
    s.add_argument("--duty", type=float, default=0.0)
    s.add_argument("--tax", type=float, default=0.0)
    s.add_argument("--other", type=float, default=0.0)
    s.add_argument("--sell", type=float, help="selling price per unit")
    s.add_argument("--financing", type=float, default=0.0, help="annual financing rate")
    s.add_argument("--days", type=int, default=0, help="days to sell the stock")
    s.add_argument("--spot", type=float, help="FX spot (domestic per foreign) for forward calc")
    s.add_argument("--dom-rate", dest="dom_rate", type=float, default=0.0)
    s.add_argument("--for-rate", dest="for_rate", type=float, default=0.0)
    s.add_argument("--fx-years", dest="fx_years", type=float, default=1.0)
    s.set_defaults(fn=cmd_trade)
    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "fn", None):
        parser.print_help()
        return 0
    try:
        return args.fn(args) or 0
    except (ValueError, FileNotFoundError, IndexError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
