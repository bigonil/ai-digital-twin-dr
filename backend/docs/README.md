# Infrastructure Documentation

Complete documentation for the AWS Disaster Recovery infrastructure setup, designed to be ingested into Qdrant (vector semantic search) and Neo4j (topology knowledge graph).

## Files Overview

### 1. **01-architecture-overview.md**
- High-level architecture describing multi-region setup (us-east-1, us-west-2)
- Regional component breakdown (public/private subnets, RDS clusters)
- CloudFront CDN integration
- Route53 failover routing
- Network isolation strategy
- Redundancy and DR procedures

**Use Case:** Understand the complete infrastructure picture, disaster recovery design, and how components interact across regions.

### 2. **02-network-topology.md**
- VPC and subnet architecture (CIDR blocks, AZ distribution)
- Subnet strategy (public vs private, security groups)
- Availability Zone spread and resilience
- Security group rules for database access
- Cross-region replication networking
- DB subnet group configuration
- Network flow diagrams and future scaling considerations

**Use Case:** Deep dive into networking, security group rules, subnet planning, and how data flows through the network.

### 3. **03-cloudfront-cdn.md**
- CloudFront distribution configuration and origins
- S3 bucket security (bucket policies, OAC)
- Caching behavior (TTL, query strings, cookies)
- Viewer protocol policy (HTTPS enforcement)
- SSL/TLS certificate configuration
- Request flow diagrams (cache hit vs miss)
- Performance metrics and cost analysis
- Security best practices and troubleshooting

**Use Case:** Understand CDN architecture, caching strategies, performance optimization, and how content is delivered globally.

### 4. **04-rds-failover.md**
- RDS Aurora PostgreSQL cluster architecture (primary + secondary)
- Cluster instance specifications (db.t4.medium, multi-AZ)
- Cross-region replication mechanism and latency
- Route53 health checks and DNS failover
- Failover timeline and recovery procedures
- Database monitoring, backups, and scaling
- Operational procedures for maintenance and emergency failover

**Use Case:** Master database replication, failover, and operational procedures. Critical for understanding DR capabilities.

### 5. **05-infrastructure-dependencies.md**
- Complete dependency graph (visual ASCII tree)
- Relationship types in Neo4j (DEPENDS_ON, REPLICATES_TO, FAILOVER_TO)
- Critical paths for deployment and failover
- Blast radius analysis (failure impact scope)
- Cascade failure scenarios
- Redundancy assessment by component
- Monitoring and validation procedures

**Use Case:** Understand infrastructure dependencies, failure impact, and how to monitor interconnected components.

---

## Integration with Digital Twin

### Neo4j (Graph Topology)

The Terraform parser (`backend/parsers/infra.py`) automatically ingests infrastructure resources into Neo4j as **InfraNode** entities with edges representing **DEPENDS_ON** relationships.

**Current Entities Extracted:**
- `aws_vpc.primary` → InfraNode (type: aws_vpc, provider: aws, region: us-east-1)
- `aws_subnet.private_a` → InfraNode (with is_redundant: false)
- `aws_subnet.private_b` → InfraNode (with is_redundant: false)
- `aws_security_group.db` → InfraNode
- `aws_rds_cluster.postgres` → InfraNode (is_redundant: true)
- `aws_rds_cluster_instance.postgres_primary` → InfraNode (is_redundant: true)
- `aws_rds_cluster.postgres_secondary` → InfraNode (is_redundant: true)
- `aws_rds_cluster_instance.postgres_secondary` → InfraNode (is_redundant: true)
- `aws_s3_bucket.origin` → InfraNode
- `aws_cloudfront_distribution.main` → InfraNode
- `aws_route53_zone.main` → InfraNode
- `aws_route53_health_check.primary_rds` → InfraNode
- `aws_route53_health_check.secondary_rds` → InfraNode
- `aws_route53_record.postgres_primary` → InfraNode
- `aws_route53_record.postgres_secondary` → InfraNode

**Relationships Created (DEPENDS_ON):**
- All explicit Terraform resource references (e.g., `aws_rds_cluster.postgres` references `aws_security_group.db`)

**Query Examples:**

```cypher
# Find all RDS resources and their dependencies
MATCH (n {type: 'aws_rds_cluster'})-[r:DEPENDS_ON]->(dep)
RETURN n.name, type(r), dep.name

# Find blast radius if primary RDS fails
MATCH path = (rds {id: 'aws_rds_cluster.postgres'})<-[*]-(affected)
RETURN affected.name, LENGTH(path) AS distance
ORDER BY distance

# Check redundancy of all components
MATCH (n:InfraNode)
WHERE n.is_redundant = true
RETURN n.type, COUNT(*) AS count
```

### Qdrant (Semantic Search on Docs)

The documentation ingestion pipeline (`backend/parsers/docs.py`) processes these Markdown files as follows:

1. **Chunking:** Each file is split into 512-character chunks with 64-char overlap
2. **Embedding:** Chunks are sent to Ollama (nomic-embed-text model) for 768-dimensional vector embeddings
3. **Storage:** Vectors stored in Qdrant `dr_docs` collection with metadata:
   - `text`: Original chunk
   - `source_file`: Which markdown file (e.g., "01-architecture-overview.md")
   - `chunk_index`: Position in file
   - `title`: File stem (e.g., "architecture-overview")

4. **Search:** Use Qdrant semantic search to find relevant documentation

**Example: Semantic Search for Failover Information**

```python
# User asks: "How does the system failover during a disaster?"
query_embedding = await ollama_embed("How does the system failover during a disaster?")
results = await qdrant_client.search(query_embedding, limit=5)

# Returns top 5 chunks from:
# - 04-rds-failover.md (failover mechanism)
# - 01-architecture-overview.md (disaster recovery procedures)
# - 05-infrastructure-dependencies.md (cascade failure scenarios)
```

**Benefits:**
- Semantic understanding (not just keyword matching)
- Fast retrieval of relevant context
- Links answers to source documentation
- Enables AI agents to understand infrastructure intent

---

## How to Ingest Documentation

### Option 1: Using FastAPI Endpoint

**Start the backend:**
```bash
cd backend
python -m uvicorn main:app --reload
```

**Ingest docs:**
```bash
curl -X POST http://localhost:8000/api/graph/ingest/docs \
  -H "Content-Type: application/json" \
  -d '{"directory": "backend/docs"}'
```

**Expected Response:**
```json
{
  "status": "ok",
  "nodes": 5,
  "points": 2847
}
```

**Breakdown:**
- `nodes`: 5 Document nodes created in Neo4j (one per .md file)
- `points`: 2847 vector embeddings stored in Qdrant (avg ~570 per file)

### Option 2: Programmatic Ingestion

```python
from backend.db.qdrant_client import QdrantClient
from backend.db.neo4j_client import Neo4jClient
from backend.parsers.docs import ingest
from backend.settings import Settings

async def main():
    settings = Settings()
    
    neo4j = Neo4jClient(settings)
    await neo4j.connect()
    
    qdrant = QdrantClient(settings)
    await qdrant.connect()
    
    result = await ingest("backend/docs", qdrant, neo4j)
    print(f"Ingested: {result}")
    
    await neo4j.close()
    await qdrant.close()
```

---

## Terraform Ingestion (Infrastructure Graph)

**Start the backend and ingest Terraform:**
```bash
curl -X POST http://localhost:8000/api/graph/ingest/terraform \
  -H "Content-Type: application/json" \
  -d '{"directory": "backend/terraform"}'
```

**Expected Response:**
```json
{
  "status": "ok",
  "nodes": 15,
  "edges": 18
}
```

**Breakdown:**
- `nodes`: 15 InfraNode entities representing AWS resources
- `edges`: 18 DEPENDS_ON relationships (explicit resource references)

---

## Using Qdrant with AI Agents

### Semantic Search Example

```python
# Agent asks about DR procedures
query = "What is the timeline for automatic failover when primary database fails?"
vector = await embed_model.embed(query)

# Search Qdrant
results = await qdrant.search(vector, limit=3)

# Results return chunks from 04-rds-failover.md:
# - "Failure Detection" section (90 seconds)
# - "Failover Timeline" section (3 minutes total)
# - "RTO/RPO" section (recovery metrics)
```

### Augmented Generation (RAG) Pattern

```python
# 1. Semantic search on docs
docs_context = await qdrant.search(user_question, limit=5)

# 2. Build context from Neo4j
infra_context = await neo4j.run(
  "MATCH (n:InfraNode)-[r:DEPENDS_ON]->(m) RETURN n.name, m.name"
)

# 3. Generate answer using both contexts
answer = await llm.generate(
  f"Question: {user_question}\n"
  f"Documentation: {docs_context}\n"
  f"Infrastructure Graph: {infra_context}"
)
```

---

## Documentation Structure

### Logical Progression

1. **Start with 01-architecture-overview.md** — Understand big picture
2. **Then 02-network-topology.md** — Learn networking details
3. **Then 03-cloudfront-cdn.md** — Understand content delivery
4. **Then 04-rds-failover.md** — Master database failover
5. **Finally 05-infrastructure-dependencies.md** — Understand all interconnections

### Cross-References

Each document references others:
- Overview → links to specific components
- Network Topology → references VPC from architecture
- CloudFront → references S3 bucket from architecture
- RDS Failover → references Route53 and health checks
- Dependencies → synthesizes concepts from all previous docs

---

## Updating Documentation

When infrastructure changes:

1. **Update Terraform** (`backend/terraform/main.tf`)
2. **Update relevant markdown file**
3. **Re-ingest:**
   ```bash
   # Terraform parser automatically picks up new resources
   curl -X POST http://localhost:8000/api/graph/ingest/terraform \
     -d '{"directory": "backend/terraform"}'
   
   # Re-ingest docs to update Qdrant vectors
   curl -X POST http://localhost:8000/api/graph/ingest/docs \
     -d '{"directory": "backend/docs"}'
   ```

---

## Monitoring & Validation

### Check Neo4j Topology

```cypher
# Verify all resources imported
MATCH (n:InfraNode) RETURN n.type, COUNT(*) AS count
```

Expected counts:
- aws_vpc: 2
- aws_subnet: 4 (2 in primary, 2 in secondary)
- aws_security_group: 2
- aws_rds_cluster: 2
- aws_rds_cluster_instance: 2
- aws_s3_bucket: 1
- aws_cloudfront_distribution: 1
- aws_route53_*: 5 (1 zone, 2 health checks, 2 records)

### Check Qdrant Collection

```bash
curl http://localhost:6333/collections/dr_docs/points?limit=10
```

Should return ~2800 points with source_file metadata pointing to backend/docs/*.md

---

## Performance Tuning

### Qdrant Vector Search

- Collection: `dr_docs`
- Vector size: 768 (nomic-embed-text output)
- Distance metric: COSINE
- Search limit: Default 5 results (configurable)

**Optimization Tips:**
- Increase `limit` for broader searches (slower, more results)
- Lower `similarity_threshold` to include less relevant documents
- Re-embed chunks if Ollama model changes

### Neo4j Query Performance

- Index on `node.type` (defined in schema)
- Index on `node.region` (for regional queries)
- Index on `node.status` (for health monitoring)
- Unique constraint on `node.id` (for lookups)

---

## Troubleshooting

### Qdrant Ingest Fails

**Error:** `No such module: 'ollama'`

**Solution:** Start Ollama service
```bash
ollama serve
ollama pull nomic-embed-text
```

### Neo4j Ingest Fails

**Error:** `Disallowed relationship type`

**Solution:** Check `_ALLOWED_REL_TYPES` in `db/neo4j_client.py`

Only `DEPENDS_ON`, `INTERACTS_WITH`, `DOCUMENTED_BY`, etc. are allowed.

### Semantic Search Returns Irrelevant Results

**Solution:** 
1. Check embedding model is loaded correctly
2. Verify chunk text is meaningful (not too small)
3. Try rephrasing query in more specific terms

---

## Related Files

- **Terraform:** `backend/terraform/main.tf`
- **Parser:** `backend/parsers/infra.py`, `backend/parsers/docs.py`
- **API:** `backend/api/graph.py`
- **Database Clients:** `backend/db/neo4j_client.py`, `backend/db/qdrant_client.py`

---

## Next Steps

After ingesting:

1. **Query Neo4j** to validate infrastructure topology
2. **Search Qdrant** to retrieve relevant documentation
3. **Use in Agent** to provide context-aware DR recommendations
4. **Monitor** both databases for performance and consistency
