# Feature Engineering API — MLOps Pipeline 

A real-time **feature engineering service** built with FastAPI that evaluates customer creditworthiness from raw loan transaction data. The service validates input, computes aggregated credit-risk features, persists both raw and engineered data to SQLite, and exposes Prometheus metrics for live Grafana monitoring.

---

## Table of Contents

- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Setup & Run](#setup--run)
- [API Endpoints](#api-endpoints)
- [Engineered Features](#engineered-features)
- [Validation Rules](#validation-rules)
- [Performance Results](#performance-results)
- [Monitoring](#monitoring)
- [Dataset Validation Summary](#dataset-validation-summary)
- [Design Decisions](#design-decisions)

---

## Architecture

```
Client (Postman)
      │
      ▼
   Nginx :80          ← Load balancer / reverse proxy
      │
      ▼
 FastAPI :8000        ← Feature engineering API (1 Uvicorn worker)
      │
      ├──► SQLite      ← Persistent storage (WAL mode)
      │       ├── transactions  (raw loan records)
      │       └── features      (engineered customer features)
      │
      └──► Prometheus :9090  ← Metrics collection (scraped every 5s)
                │
                ▼
           Grafana :3000     ← Real-time dashboard
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| API Framework | FastAPI + Uvicorn |
| Validation | Pydantic v2 |
| Database | SQLite via aiosqlite (WAL mode) |
| Serialisation | ORJSONResponse |
| Monitoring | Prometheus + Grafana |
| Load Balancing | Nginx |
| Containerisation | Docker + Docker Compose |
| Performance Testing | Postman Performance |

---

## Project Structure

```
.
├── app/
│   ├── api/
│   │   └── endpoints.py          # GET/DELETE customer endpoints
│   ├── core/
│   │   ├── logging_config.py     # Structured logger (INFO level, stdout)
│   │   └── metrics.py            # Prometheus Gauges, Counters, Histograms
│   ├── db/
│   │   └── database.py           # SQLite connection, schema, bulk helpers
│   ├── schemas/
│   │   └── customer.py           # Pydantic validation schemas
│   └── services/
│       └── feature_service.py    # Feature engineering logic (single-pass O(n))
├── main.py                       # FastAPI app, middleware, /generate-features
├── nginx/
│   └── nginx.conf
├── grafana/
│   ├── dashboards/
│   │   └── optasia_dashboard.json
│   └── datasources/
│       └── prometheus.yml
├── reports/
│   ├── postman_10k_report        # Postman performance report — 10k requests
│   ├── postman_100k_report       # Postman performance report — 100k requests
│   ├── dashboard_metrics_10k.png # Grafana screenshot — 10k test
│   ├── dashboard_metrics_100k.png# Grafana screenshot — 100k test
│   └── validation_summary.html   # Dataset validation report
├── data/                         # SQLite database (bind-mounted from host)
├── logs/                         # Application logs
├── docker-compose.yml
├── Dockerfile
├── prometheus.yml
└── requirements.txt
```

---

## Setup & Run

### Prerequisites

- Docker Desktop ≥ 24
- Docker Compose ≥ 2

### Start all services

```bash
docker-compose up --build -d
```

This starts four containers:

| Container | Port | Purpose |
|---|---|---|
| `optasia_api` | internal :8000 | FastAPI application |
| `optasia_nginx` | :80 | Reverse proxy / load balancer |
| `optasia_prometheus` | :9090 | Metrics collection |
| `optasia_grafana` | :3000 | Monitoring dashboard |

### Verify everything is running

```bash
docker ps
curl http://localhost/health
# → {"status":"UP"}
```

### Stop

```bash
docker-compose down
```

> ⚠️ Never use `docker-compose down -v` — this deletes the database volume.

---

## API Endpoints

### POST `/generate-features`
Accepts a batch of customers with loan histories, computes features, and persists data to SQLite.

**Request body:**
```json
{
  "data": [
    {
      "customer_ID": "bVrpoiVgRV5",
      "loans": [
        {
          "loan_date": "25/09/2022",
          "amount": "189",
          "fee": "47",
          "loan_status": "0",
          "term": "short",
          "annual_income": "9149832"
        }
      ]
    }
  ]
}
```

**Response `207 Multi-Status`:**
```json
{
  "processed_at": 1746856454.92,
  "results": [
    {
      "customer_ID": "bVrpoiVgRV5",
      "status": "success",
      "features": {
        "total_loan_amount": 31002.0,
        "total_fees": 1718.0,
        "loan_count": 55,
        "default_rate": 0.4182,
        "zero_value_count": 0
      }
    }
  ]
}
```

### GET `/health`
```json
{"status": "UP"}
```

### GET `/api/v1/history/transactions/{customer_id}`
Returns all raw loan records for a customer.

### GET `/api/v1/history/features/{customer_id}`
Returns the latest engineered features for a customer.

### DELETE `/api/v1/customer/{customer_id}`
Removes all transactions and features for a customer from both tables.

### GET `/metrics`
Exposes Prometheus metrics.

---

## Engineered Features

For each customer the service computes:

| Feature | Description |
|---|---|
| `total_loan_amount` | Sum of all credited loan amounts (€) |
| `total_fees` | Sum of all loan fees charged (€) |
| `loan_count` | Total number of loan records |
| `default_rate` | Fraction of loans with `loan_status = 1` (defaulted) |
| `zero_value_count` | Number of features equal to zero (data-quality indicator) |

**Example — customer `bVrpoiVgRV5`:**

| Feature | Value | Interpretation |
|---|---|---|
| total_loan_amount | 31,002 € | High borrowing history |
| total_fees | 1,718 € | Significant fee exposure |
| loan_count | 55 | Long credit history |
| default_rate | **0.4182** | ⚠️ 41.8% default rate — elevated risk |
| zero_value_count | 0 | Complete data — no missing features |

---

## Validation Rules

All fields are validated by Pydantic before processing. Invalid requests return `422 Unprocessable Entity`.

| Field | Rule |
|---|---|
| `customer_ID` | 10–20 characters, ASCII printable only |
| `amount` | 100 ≤ amount ≤ 1,000 |
| `fee` | 10 ≤ fee ≤ 50 |
| `term` | `"short"` or `"long"` (case-sensitive) |
| `loan_status` | `"0"` (repaid) or `"1"` (defaulted) |
| `annual_income` | 100 ≤ income ≤ 10,000,000 |
| Creditworthiness | income 100–1K → amount+fee ≤ 110 |
| | income 1K–10K → amount+fee ≤ 220 |
| | income 10K–100K → amount+fee ≤ 550 |
| | income 100K–10M → amount+fee ≤ 1,050 |

---

## Performance Results

Tests were conducted using Postman Performance tab with **`customer_dataset_01.json`** (1 customer, 55 loans) as the request payload — representative of a real creditworthiness evaluation request.

### 10,000 Requests

| Metric | Result |
|---|---|
| Total Requests | 10,000 |
| Avg Response Time | ~28 ms |
| P90 | ~35 ms |
| P95 | ~45 ms |
| P99 | ~70 ms |
| Error % | 0.00% |
| Requests/sec | ~400 RPS |

### 100,000 Requests

| Metric | Result |
|---|---|
| Total Requests | 100,000 |
| Avg Response Time | ~33 ms |
| P90 | ~40 ms |
| P95 | ~50 ms |
| P99 | ~90 ms |
| Error % | 0.00% |
| Requests/sec | ~150 RPS |

> **Note:** Latency increases at 100k due to SQLite WAL file growth under sustained write pressure. In a production environment PostgreSQL with asyncpg would reduce p95 to <5ms and support horizontal scaling.

---

## Monitoring

Metrics are exposed at `/metrics` and visualised in Grafana (`http://localhost:3000`).

### Grafana Dashboard — 10k Test
![Grafana 10k](reports/dashboard_metrics_10k.png)

### Grafana Dashboard — 100k Test
![Grafana 100k](reports/dashboard_metrics_100k.png)

### Tracked Metrics

| Metric | Description |
|---|---|
| Request Rate | Requests/second to `/generate-features` |
| Avg Latency | Mean server-side response time |
| P95 Latency | 95th percentile response time |
| CPU Usage | Process CPU % (via psutil) |
| Memory Usage | RSS memory in MB (via psutil) |
| Zero Features | Count of features with zero values |
| Error Rate | 4xx / 5xx response rate |

**Observations from 100k test:**
- Request rate stable at ~150 RPS throughout the test
- Memory flat at ~72.9 MB — no memory leaks detected
- CPU spikes (up to 33%) correlate with SQLite write bursts
- P95 latency increases slightly from 10k to 100k due to WAL accumulation

---

## Dataset Validation Summary

10 customer datasets were provided. 5 passed validation fully; 5 contained invalid records that were correctly rejected by the Pydantic schema.

| # | Dataset | Customer ID | Total Loans | Valid | Invalid | Status |
|---|---|---|---|---|---|---|
| 01 | customer_dataset_01 | bVrpoiVgRV5 | 55 | 55 | 0 | ✅ PASS |
| 02 | customer_dataset_02 | jrsMnTvnRO2qGFq562 | 58 | 58 | 0 | ✅ PASS |
| 03 | customer_dataset_03 | XEDB0ULru2p17fr4Cp | 54 | 54 | 0 | ✅ PASS |
| 04 | customer_dataset_04 | y9uOT4WF3IcNepOR6s | 56 | 56 | 0 | ✅ PASS |
| 05 | customer_dataset_05 | X8KMf4djkWNdRfr | 44 | 44 | 0 | ✅ PASS |
| 06 | customer_dataset_06 | pyfxobu7g1TPvYß | 48 | 34 | 14 | ❌ FAIL |
| 07 | customer_dataset_07 | g7vsDPIHF48i2GDrmZé | 36 | 18 | 18 | ❌ FAIL |
| 08 | customer_dataset_08 | JGAgbfwJfMMYu3yasAyXfU5J5pKHk | 37 | 23 | 14 | ❌ FAIL |
| 09 | customer_dataset_09 | yhpFOMeH | 54 | 32 | 22 | ❌ FAIL |
| 10 | customer_dataset_10 | 3x0dGYketTGziX2H4K | 57 | 40 | 17 | ❌ FAIL |

Full validation report: [`reports/validation_summary.html`](reports/validation_summary.html)

---

## Design Decisions

**Why a single Uvicorn worker?**
SQLite uses a global write lock. Multiple workers cause lock contention and increase p99 latency. A single worker with `asyncio.gather` achieves intra-process parallelism without conflicts.

**Why bulk inserts?**
The original design committed once per customer. Replacing N commits with a single `executemany` + commit reduced latency from ~300ms to ~20ms under load.

**Why `wal_autocheckpoint=0`?**
Automatic WAL checkpoints every 1,000 writes caused periodic latency spikes. Disabling them and running a single `PRAGMA wal_checkpoint(TRUNCATE)` at shutdown produces a flat, predictable latency profile.

**Why SQLite instead of PostgreSQL?**
The assignment specification required SQLite. For production, PostgreSQL with asyncpg and connection pooling would be the natural next step, reducing p95 latency to <5ms and enabling horizontal scaling with multiple workers.
