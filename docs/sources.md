# Sources, and how the model's results relate to them

Every citation below was checked against library and publisher records (journal, volume,
issue, pages) on 2026-11-17. The summaries come from the papers' abstracts and standard
descriptions found during that check; **the full texts have not been read**, so the
comparisons are at the level of each paper's main result. Results of this model are from
model 1.0.0 (see the README).

## How the main findings line up

| Finding in this model | What the literature says | Agreement |
| --- | --- | --- |
| More better-informed traders, more accurate prices | Prices carry what informed traders know (Grossman and Stiglitz, 1980) | Agrees |
| Gain per better-informed trader falls as their group grows | Returns to being informed fall as prices reveal more (Grossman and Stiglitz, 1980) | Echoes; the mechanism here also includes informed traders trading with each other |
| The quoted spread **narrows** as the informed share rises | Dealer models: the spread **widens** with the share of informed traders (Glosten and Milgrom, 1985). Limit-order models: a higher informed share **improves** the spread (Roşu, 2020) | Agrees with the limit-order result, opposite to the dealer result; the benchmark in this repository reproduces the dealer result exactly |
| Impact after the trade's own step rises with the informed share | Roşu (2020): a higher informed share has no effect on the price impact of orders | Differs; measures and trader behaviour differ (see below) |
| In the Glosten–Milgrom benchmark the spread is 92–95% price impact | The spread exists to cover losses to the better informed (Glosten and Milgrom, 1985) | Agrees, checked exactly |
| Stronger urgency (more impatient traders) widens spreads | The spread falls as the proportion of patient traders rises (Foucault, Kadan and Kandel, 2005) | Agrees in direction |
| Everyone uses limit orders; better-informed traders' quotes sit in the book | Informed traders use limit orders, often more than others (Bloomfield, O'Hara and Saar, 2005; Kaniel and Liu, 2006) | Consistent |
| With learning from prices, news gets into prices slowly | Cascades: following others can stop private information from getting in (Bikhchandani, Hirshleifer and Welch, 1992); a price that moves with trades prevents this unless traders are also unsure whether a shock happened (Avery and Zemsky, 1998) | Related; the slowdown here comes from a simple rule (one constant trust in the mid-quote), not rational herding |

## Information and the spread

**Glosten, L. R. and Milgrom, P. R. (1985).** Bid, ask and transaction prices in a
specialist market with heterogeneously informed traders. *Journal of Financial Economics*
14(1), 71–100. doi:10.1016/0304-405X(85)90044-3.
A risk-neutral specialist who expects to break even still sets a positive spread when some
traders know more than it does: it recovers its losses to them from its gains on liquidity
traders. *Here:* `marketsim/glosten_milgrom.py` runs this model on the exchange and matches
the exact spread, dealer profit and spread decomposition (README, theory benchmark). In
that market the spread rises with the share of informed traders; in this model's limit
order market it falls, because the informed traders are among those quoting.

**Kyle, A. S. (1985).** Continuous auctions and insider trading. *Econometrica* 53(6),
1315–1335.
One risk-neutral insider, noise traders and competitive market makers; noise trading hides
the insider's orders, and the insider trades gradually so that information reaches the
price over time. *Here:* information also reaches prices gradually, but for a different
reason: better-informed traders are not strategic; they trade only to meet their inventory
need and leave quotes that go stale. Strategic informed trading is the model's main gap
(`docs/model_rules.md`, section 8).

## Learning from prices

**Grossman, S. J. and Stiglitz, J. E. (1980).** On the impossibility of informationally
efficient markets. *American Economic Review* 70(3), 393–408.
The price passes informed traders' information on to the uninformed; if it did so
perfectly, nobody would pay to become informed, so prices cannot be fully efficient when
information is costly. *Here:* calibrated trust is a simple version of uninformed traders
reading the price. Two findings echo the paper: better-informed traders' gain per head
falls as their share rises, and when prices are trusted, private information gets into
them more slowly. Information is free in this model, so the paper's central question (how
many choose to become informed) is not asked yet.

**Bikhchandani, S., Hirshleifer, D. and Welch, I. (1992).** A theory of fads, fashion,
custom, and cultural change as informational cascades. *Journal of Political Economy*
100(5), 992–1026. doi:10.1086/261849.
An informational cascade is when it is best for someone to follow those before them
regardless of their own information; private information then stops being revealed.

**Avery, C. and Zemsky, P. (1998).** Multidimensional uncertainty and herd behavior in
financial markets. *American Economic Review* 88(4), 724–748.
With private information about only the size of a shock, a price that adjusts to trades
prevents herding. Herding appears when traders are also unsure whether a shock happened,
and with uncertainty about the quality of traders' information it can misprice the asset
in the short run. *Here:* traders trust the mid-quote equally whether or not news has just
arrived, although right after news it is far less accurate than on average. The slow news
response with learning comes from that simple rule. Rational traders who allowed for news
having arrived would lean less on the price just after it.

## Limit order markets and informed traders

**Foucault, T., Kadan, O. and Kandel, E. (2005).** Limit order book as a market for
liquidity. *Review of Financial Studies* 18(4), 1171–1217. doi:10.1093/rfs/hhi029.
Liquidity traders differ in impatience: patient ones post limit orders, impatient ones
take them. The share of patient traders and the arrival rate drive the book; the spread
falls as patient traders become more common. *Here:* the urgency margin is a mechanical
version of impatience: a trader far from its target prices to cross the spread. The
`strong_urgency` variant (more impatience) has wider spreads, in the same direction.

**Goettler, R. L., Parlour, C. A. and Rajan, U. (2009).** Informed traders and limit order
markets. *Journal of Financial Economics* 93(1), 67–87. doi:10.1016/j.jfineco.2008.08.002.
Traders choose whether to acquire information and which kind of order to send; solved
numerically, the market amplifies volatility relative to the asset's value. *Here:* a model
of the two choices this one leaves out (whether to become informed, and when to take rather
than make liquidity); the closest template for the extensions in `docs/STATUS.md`.

**Kaniel, R. and Liu, H. (2006).** So what orders do informed traders use? *Journal of
Business* 79(4), 1867–1914. doi:10.1086/503651.
Informed traders may prefer limit orders even after allowing for price impact, so limit
orders can carry more information than market orders; the paper's data support this.

**Bloomfield, R., O'Hara, M. and Saar, G. (2005).** The "make or take" decision in an
electronic market: evidence on the evolution of liquidity. *Journal of Financial Economics*
75(1), 165–199. doi:10.1016/j.jfineco.2004.07.001.
In experimental limit order markets, informed traders use more limit orders than liquidity
traders and increasingly provide liquidity as trading goes on. *Here:* every trader posts
limit orders, so better-informed traders' quotes are part of the book, and after news they
go stale until their owners return; the bounds on quote refreshing in the README show how
much that matters.

**Roşu, I. (2020).** Liquidity and information in limit order markets. *Journal of
Financial and Quantitative Analysis* 55(6), 1792–1839. doi:10.1017/S0022109019000759.
In a dynamic limit order model, a higher share of informed traders improves liquidity (the
spread and resiliency) and leaves the price impact of orders unchanged. *Here:* the spread
result agrees. Impact after the trade's own step rises with the informed share here; the
traders are rule-based rather than strategic and impact is measured over 10 steps, so the
two are not directly comparable, but the difference is worth checking.

## Inventory

**Ho, T. and Stoll, H. R. (1981).** Optimal dealer pricing under transactions and return
uncertainty. *Journal of Financial Economics* 9(1), 47–73. doi:10.1016/0304-405X(81)90020-9.
A dealer sets its quotes around the asset's value and shifts them with its inventory.
*Here:* the urgency margin makes a trader's price depend on its distance from its
inventory target, the same idea applied to every trader rather than to a dealer.

## Measures

**Huang, R. D. and Stoll, H. R. (1996).** Dealer versus auction markets: a paired comparison
of execution costs on NASDAQ and the NYSE. *Journal of Financial Economics* 41(3), 313–357.
doi:10.1016/0304-405X(95)00867-E.
Compares execution costs using, among others, the quoted spread, the effective spread
(which counts trades inside the quotes) and the realized spread (what suppliers of
immediacy earn after prices move). *Here:* `metrics.spread_decomposition` uses the same
effective and realized spread, with price impact as the difference, read 10 steps after
each trade.

## Markets of simple traders

**Gode, D. K. and Sunder, S. (1993).** Allocative efficiency of markets with
zero-intelligence traders: market as a partial substitute for individual rationality.
*Journal of Political Economy* 101(1), 119–137. doi:10.1086/261868.
Random bidders constrained not to trade at a loss reach close to full allocative efficiency
in a double auction: the efficiency comes largely from the market's rules. *Here:* need met
is a related idea (does the market get done what traders came for?), but it counts shares,
not surplus, so the numbers are not comparable.

**Farmer, J. D., Patelli, P. and Zovko, I. I. (2005).** The predictive power of zero
intelligence in financial markets. *Proceedings of the National Academy of Sciences*
102(6), 2254–2259. doi:10.1073/pnas.0409157102.
A model where orders arrive at random explains most of the variation in spreads across
London Stock Exchange stocks: for some questions the market's mechanics matter more than
traders' strategies. *Here:* a reason to expect rule-based traders to say something about
spreads and depth, and a caution: some results (such as most of the price impact being
mechanical) may come from the order book itself rather than from information.
