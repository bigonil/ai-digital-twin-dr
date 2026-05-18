# Database Connection Pool Management During DR

## Overview

Connection pool failures are responsible for extending actual RTO beyond predicted RTO in 60% of database DR incidents. When Aurora fails over or restarts, existing connections are dropped. Application servers holding stale connections either hang (no timeout) or storm the new primary with simultaneous reconnects. This guide covers connection pool configuration, RDS Proxy, and connection management during recovery.

---

## The Connection Storm Problem

**Scenario:** Aurora fails over. 6 application servers each hold a pool of 50 connections = 300 connections. All 300 connections are dropped simultaneously. All 300 reconnect simultaneously to new primary within 5 seconds.

**Result:** New primary receives 300 connection requests in 5 seconds. For `db.r7g.large` Aurora: `max_connections ≈ 2000`. Connection storm is handled, but:
- Each connection setup requires authentication: CPU spike on new primary
- Connection pool warm-up: 5–10 seconds of higher latency
- If using `max_connections` smaller instance: connections may queue or fail

**Mitigation options ranked by effectiveness:**
1. **RDS Proxy** (best): buffers connections; app reconnects to Proxy, Proxy reconnects to new Aurora
2. **Exponential backoff in pool config** (good): staggers reconnects over 10–30 seconds
3. **Pre-warming connection pool** (basic): keep idle connections alive, reconnect on health check

---

## RDS Proxy — Recommended for Production

RDS Proxy sits between the application and Aurora. It maintains a stable pool of connections to Aurora and handles failover transparently. Applications connect to the Proxy endpoint instead of the cluster endpoint.

### Setup RDS Proxy

```bash
aws rds create-db-proxy \
  --db-proxy-name app-postgres-proxy \
  --engine-family POSTGRESQL \
  --auth '[{
    "AuthScheme": "SECRETS",
    "SecretArn": "arn:aws:secretsmanager:us-east-1:<account>:secret:app/postgres/credentials",
    "IAMAuth": "DISABLED"
  }]' \
  --role-arn arn:aws:iam::<account>:role/rds-proxy-role \
  --vpc-subnet-ids subnet-<a> subnet-<b> \
  --vpc-security-group-ids sg-<id> \
  --no-require-tls

# Register Aurora cluster as proxy target
aws rds register-db-proxy-targets \
  --db-proxy-name app-postgres-proxy \
  --db-cluster-identifiers app-postgres

# Get proxy endpoint (update application config to use this)
aws rds describe-db-proxies \
  --db-proxy-name app-postgres-proxy \
  --query 'DBProxies[0].Endpoint'
```

**RDS Proxy benefits during DR:**
- Failover transparent to application (Proxy handles reconnect): app sees < 30 second interruption vs 60–120 seconds without Proxy
- Connection multiplexing: 300 app connections → 50 DB connections (reduces Aurora connection count)
- Automatic credential rotation (reads from Secrets Manager)
- `max_connections_percent = 90`: never exhausts Aurora connection limit

### Monitor RDS Proxy

```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name DatabaseConnectionsCurrentlyBorrowed \
  --dimensions Name=ProxyName,Value=app-postgres-proxy \
  --start-time $(date -u -d '15 min ago' +%FT%TZ) \
  --end-time $(date -u +%FT%TZ) \
  --period 60 --statistics Average
```

Key RDS Proxy metrics:
- `DatabaseConnectionsCurrentlyBorrowed` — active connections from pool
- `DatabaseConnectionsCurrentlySessionPinned` — connections that can't be multiplexed (watch for high values)
- `QueryRequests` — request rate through proxy
- `DatabaseConnectionRequests` — new DB connection attempts

---

## Application Connection Pool Configuration

### Python — SQLAlchemy (recommended settings for DR resilience)

```python
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

engine = create_engine(
    "postgresql+psycopg2://admin:password@<rds-proxy-endpoint>:5432/appdb",
    poolclass=QueuePool,
    pool_size=20,               # Base pool size per process
    max_overflow=10,            # Burst capacity
    pool_timeout=30,            # Wait for connection before raising error
    pool_recycle=1800,          # Recycle connections after 30 min (avoid stale)
    pool_pre_ping=True,         # Test connection before use (detects Aurora failover)
    connect_args={
        "connect_timeout": 5,   # TCP connect timeout
        "application_name": "app-server",
        "options": "-c statement_timeout=30000"  # 30-second query timeout
    }
)
```

`pool_pre_ping=True` is critical: before handing a connection to the application, SQLAlchemy sends `SELECT 1`. If the connection is stale (post-failover), it's discarded and a fresh connection is made. This prevents `OperationalError: server closed the connection unexpectedly`.

### Node.js — pg-pool (recommended settings)

```javascript
const { Pool } = require('pg');

const pool = new Pool({
  host: process.env.DB_HOST,      // RDS Proxy endpoint
  port: 5432,
  database: 'appdb',
  user: process.env.DB_USER,
  password: process.env.DB_PASSWORD,
  max: 20,                        // Max connections per Node process
  idleTimeoutMillis: 30000,       // Close idle connections after 30s
  connectionTimeoutMillis: 5000,  // Fail fast if can't connect in 5s
  statement_timeout: 30000,       // Kill queries > 30 seconds
});

// Health check: validate pool connectivity
pool.on('error', (err) => {
  console.error('Unexpected pool error:', err);
  // Reconnect logic handled by pg-pool automatically
});
```

---

## Post-Failover Connection Recovery Steps

After Aurora failover (with or without RDS Proxy):

### With RDS Proxy (automated):
1. RDS Proxy detects Aurora failover (< 10 seconds via health check)
2. Proxy reconnects to new Aurora primary automatically
3. Application connections to Proxy remain stable (brief pause of < 30 seconds)
4. Verify: `aws rds describe-db-proxies --db-proxy-name app-postgres-proxy --query 'DBProxies[0].Status'` → `available`

### Without RDS Proxy (manual):
1. Detect failover: `aws rds describe-db-clusters --db-cluster-identifier app-postgres --query 'DBClusters[0].{Status:Status}'`
2. Wait for cluster endpoint DNS to update (30–90 seconds after failover)
3. Force connection pool reset on all application instances:
   ```bash
   # If using SSM Run Command on ASG instances:
   aws ssm send-command \
     --targets Key=tag:aws:autoscaling:groupName,Values=app-asg \
     --document-name AWS-RunShellScript \
     --parameters commands=["sudo systemctl restart app-service"]
   ```
4. Monitor error rate in CloudWatch — should recover within 2 minutes of pool reset

---

## Connection Limits by Instance Class

Aurora PostgreSQL `max_connections` formula: `LEAST(DBInstanceClassMemory / 9531392, 5000)`

| Instance Class | Memory | Max Connections |
|---|---|---|
| db.t3.medium | 4 GB | ~420 |
| db.r6g.large | 16 GB | ~1700 |
| db.r7g.large | 16 GB | ~1700 |
| db.r7g.xlarge | 32 GB | ~3400 |
| db.r7g.2xlarge | 64 GB | ~5000 (capped) |

**Rule:** Total application connection pool size must be < 80% of Aurora max_connections.
For `db.r7g.large` with 6 EC2 instances: max pool per instance = `(1700 × 0.8) / 6 ≈ 226 connections`.

**With RDS Proxy:** Proxy multiplexes; application can have 1000 connections to Proxy while Proxy maintains only 50 to Aurora. Effectively removes connection limit as bottleneck.

---

## Emergency: Kill Idle Connections

If Aurora is overloaded with idle connections post-failover:

```sql
-- Kill idle connections older than 5 minutes
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE state = 'idle'
  AND state_change < NOW() - INTERVAL '5 minutes'
  AND pid <> pg_backend_pid();

-- Check active connection count by application
SELECT application_name, state, COUNT(*)
FROM pg_stat_activity
WHERE pid <> pg_backend_pid()
GROUP BY application_name, state
ORDER BY COUNT(*) DESC;

-- Current max_connections setting
SHOW max_connections;
```
