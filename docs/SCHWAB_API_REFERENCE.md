# Schwab Developer API — Quick Reference

## Base URL

```
https://api.schwabapi.com/marketdata/v1/
```

---

## Rate Limits

| Limit | Value |
|---|---|
| **API calls** | 120 requests/minute |
| **Access token lifetime** | 30 minutes |
| **Refresh token lifetime** | 7 days (hard limit, then re-auth) |
| **Rate limit error** | HTTP 429, back off 60 seconds |

**No documented daily limit** — constraint is per-minute only.

---

## Endpoints We Use (Read-Only)

### 1. Options Chain — `GET /chains`

The most critical endpoint. Returns full chain with greeks.

**Key Parameters:**

| Parameter | Values | Our Usage |
|---|---|---|
| `symbol` | e.g., `SPX`, `AAPL` | Required |
| `contractType` | `ALL` | Get both calls and puts |
| `strikeCount` | integer | Omit for all strikes |
| `includeUnderlyingQuote` | `true` | Get spot price in same call |
| `strategy` | `SINGLE` | Individual contracts |
| `fromDate` / `toDate` | ISO date | DTE range filtering |
| `optionType` | `S` (standard) | Skip non-standard |

**Response includes per contract:**
- Pricing: `bid`, `ask`, `last`, `mark`, `openPrice`, `highPrice`, `lowPrice`, `closePrice`
- Greeks: `delta`, `gamma`, `theta`, `vega`, `rho`
- Analytics: `volatility` (IV), `theoreticalOptionValue`, `timeValue`
- Volume: `totalVolume`, `openInterest`
- Metadata: `strikePrice`, `expirationDate`, `daysToExpiration`, `inTheMoney`, `multiplier`

**Response structure:**
```json
{
  "symbol": "SPX",
  "status": "SUCCESS",
  "underlying": { "last": 5250.0, "bid": 5249.5, "ask": 5250.5, ... },
  "callExpDateMap": {
    "2025-03-28:3": {        // expiration:DTE
      "5200.0": [{ "gamma": 0.0045, "openInterest": 1500, ... }],
      "5250.0": [{ "gamma": 0.0089, "openInterest": 3200, ... }]
    }
  },
  "putExpDateMap": { /* same structure */ }
}
```

### 2. Quotes — `GET /quotes`

```
GET /quotes?symbols=SPX,$VIX,$VIX3M,/ES
```

Returns quote data for equities, indices, futures. Supports comma-separated symbols.

**Key fields:** `lastPrice`, `bidPrice`, `askPrice`, `openPrice`, `highPrice`, `lowPrice`, `closePrice`, `totalVolume`, `netChange`, `netPercentChange`, `mark`

### 3. Price History — `GET /pricehistory`

| Parameter | Options |
|---|---|
| `periodType` | `day`, `month`, `year`, `ytd` |
| `frequencyType` | `minute`, `daily`, `weekly`, `monthly` |
| `frequency` | 1, 5, 10, 15, 30 (for minute) |

**Lookback limits:**
- 1-minute: ~48 days
- 5-minute: ~9 months
- Daily: 15-20 years

**Note: Equities/ETFs only.** No futures or options historical bars.

### 4. Movers — `GET /movers/{index}`

Indices: `$DJI`, `$COMPX`, `$SPX`, `NYSE`, `NASDAQ`

Sort by: `VOLUME`, `TRADES`, `PERCENT_CHANGE_UP`, `PERCENT_CHANGE_DOWN`

### 5. Market Hours — `GET /markets`

Markets: `equity`, `option`, `bond`, `future`, `forex`

### 6. Instruments — `GET /instruments`

Search types: `symbol-search`, `symbol-regex`, `desc-search`, `fundamental`

### 7. Expiration Chain — `GET /expirationchain`

Returns all available expiration dates for a symbol. Lightweight alternative to full chain fetch.

---

## Futures Support

### What Works
- **Quotes** via REST: `/ES`, `/NQ`, `/CL`, `/GC`, etc. (use `/` prefix)
- **Market hours** via REST

### What Doesn't Work via REST
- No historical price bars for futures
- No futures options chains via REST
- No order entry for futures

### Streaming (Future Enhancement)
- `LEVEL_ONE_FUTURES` — 41 fields including bid/ask, volume, OI, settlement
- `LEVEL_ONE_FUTURES_OPTIONS` — 32 fields including greeks
- `CHART_FUTURES` — Real-time OHLCV minute bars

---

## Data Freshness

| Data Type | REST API | Streaming |
|---|---|---|
| Equity quotes | May be delayed (subset of exchanges) | Real-time |
| Options chains | May be 15-min delayed | Real-time via LEVEL_ONE_OPTIONS |
| Futures quotes | May be delayed | Real-time |
| Open Interest | **End-of-day only** (always stale intraday) | Same |

Check `isDelayed` field in responses to know what you're getting.

---

## Option Symbol Format (OCC)

```
{UNDERLYING(6 chars padded)}{EXPIRY(YYMMDD)}{C/P}{STRIKE(5.3 format)}
```

Example: `SPXW  260328C05200000` = SPX Weekly Mar 28 2026 $5200 Call

---

## Error Codes

| Code | Meaning |
|---|---|
| 400 | Bad request (invalid params) |
| 401 | Unauthorized (token expired/invalid) |
| 403 | Forbidden (insufficient permissions) |
| 404 | Not found |
| 429 | Rate limit exceeded (wait 60s) |
| 500 | Server error |
