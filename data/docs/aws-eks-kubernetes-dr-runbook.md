# AWS EKS / Kubernetes — Disaster Recovery Runbook

## Resource Type: aws_eks_cluster | Strategy: stateless, backup_fallback

### Overview

Amazon EKS clusters (`aws_eks_cluster`) run Kubernetes control planes managed by AWS across multiple AZs. Worker nodes run in managed node groups (EC2 Auto Scaling Groups). Kubernetes workloads are stateless by design — pods are ephemeral. State lives in Aurora, ElastiCache, or S3. EKS control plane has 99.95% SLA and auto-recovers; DR focuses on worker node failures and cluster-level recovery.

RTO targets: 2–5 min (node replacement) | 15–30 min (cluster rebuild) | 5 min (pod rescheduling)
RPO: 0 (stateless pods) | depends on PVC backing store for stateful workloads

---

## Failure Scenario: Worker Node Failure (stateless)

**Symptoms:**
- Kubernetes: `kubectl get nodes` shows nodes in `NotReady` state
- Pods evicted and rescheduled on other nodes; some pods in `Pending` if cluster at capacity
- CloudWatch: `eks-worker/node_not_ready` alert

**Detection Commands:**
```bash
kubectl get nodes -o wide
kubectl describe node <node-name> | grep -A 10 Conditions:
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed

# Check node group health via AWS
aws eks describe-nodegroup \
  --cluster-name app-cluster \
  --nodegroup-name app-nodegroup \
  --query 'nodegroup.{Status:status,Health:health,ScalingConfig:scalingConfig}'
```

**Recovery Steps — stateless (auto):**
1. Kubernetes detects node failure via kubelet heartbeat (40-second timeout)
2. Node marked `NotReady`; pods evicted after `pod-eviction-timeout` (default 5 minutes)
3. ASG replaces failed EC2 node automatically (same as `aws_instance` stateless strategy)
4. New node joins cluster and receives rescheduled pods
5. Monitor: `kubectl get pods --all-namespaces -w` — all pods return to `Running`

**Recovery Steps — stateless (manual accelerated):**
```bash
# Cordon node to prevent new pod scheduling
kubectl cordon <node-name>

# Drain existing pods safely
kubectl drain <node-name> \
  --ignore-daemonsets \
  --delete-emptydir-data \
  --grace-period=30

# Terminate underlying EC2 instance (ASG replaces it)
NODE_INSTANCE=$(kubectl get node <node-name> -o jsonpath='{.spec.providerID}' | cut -d/ -f5)
aws ec2 terminate-instances --instance-ids $NODE_INSTANCE
```

**Verification:** All pods `Running`, all nodes `Ready`. Check: `kubectl get pods -A | grep -v Running | grep -v Completed | wc -l` → 0.

---

## Failure Scenario: Full Node Group Failure

**Symptoms:** All worker nodes `NotReady`; all pods `Pending`; services return 503.

**Recovery Steps:**
1. Check node group status:
   ```bash
   aws eks describe-nodegroup \
     --cluster-name app-cluster \
     --nodegroup-name app-nodegroup
   ```
2. Check ASG health — are replacement nodes launching?
   ```bash
   aws autoscaling describe-auto-scaling-groups \
     --auto-scaling-group-name <asg-name> \
     --query 'AutoScalingGroups[0].Instances[*].{Id:InstanceId,State:LifecycleState,Health:HealthStatus}'
   ```
3. If nodes launch but fail to join: check node IAM role and EKS auth config:
   ```bash
   kubectl -n kube-system get configmap aws-auth -o yaml
   ```
4. Force node group update to refresh all nodes:
   ```bash
   aws eks update-nodegroup-version \
     --cluster-name app-cluster \
     --nodegroup-name app-nodegroup \
     --force
   ```
5. Scale node group up temporarily if capacity is insufficient:
   ```bash
   aws eks update-nodegroup-config \
     --cluster-name app-cluster \
     --nodegroup-name app-nodegroup \
     --scaling-config minSize=3,maxSize=10,desiredSize=6
   ```

---

## Failure Scenario: EKS Control Plane Unavailable

**Symptoms:** `kubectl` commands time out; API server unreachable. Worker nodes continue running existing pods (Kubernetes graceful degradation).

**Note:** EKS control plane is AWS-managed and runs across 3 AZs. True control plane failure is rare (covered by AWS SLA). Running workloads continue without API server.

**Recovery Steps:**
1. Verify: `aws eks describe-cluster --name app-cluster --query 'cluster.{Status:status,Endpoint:endpoint}'`
2. Check AWS Health Dashboard for EKS service events in affected region
3. If control plane endpoint is unreachable, open AWS Support case (P1)
4. Existing pods continue serving traffic — do NOT restart them
5. Deploy no new changes until control plane recovers (cannot validate)
6. Expected RTO: 5–60 minutes (AWS-managed recovery); usually resolves within 15 minutes

---

## Failure Scenario: DR Region Failover (us-east-1 → eu-west-1)

**Recovery Steps:**
1. Verify eu-west-1 cluster exists and node group is healthy:
   ```bash
   aws eks describe-cluster --name app-cluster-dr --region eu-west-1
   kubectl --context=arn:aws:eks:eu-west-1:<account>:cluster/app-cluster-dr get nodes
   ```
2. Scale up DR node group to production capacity:
   ```bash
   aws eks update-nodegroup-config \
     --cluster-name app-cluster-dr \
     --nodegroup-name app-nodegroup-dr \
     --scaling-config desiredSize=6 \
     --region eu-west-1
   ```
3. Update Route53 to route traffic to eu-west-1 ALB (in front of EKS ingress)
4. Verify application deployments are running in DR cluster:
   ```bash
   kubectl --context=app-cluster-dr get deployments --all-namespaces
   ```
5. Update ConfigMaps with eu-west-1 database endpoints (Aurora, Redis)
6. Validate health endpoints return 200

---

## Kubernetes-Specific Monitoring

Key metrics via CloudWatch Container Insights:
- `container_cpu_utilization` — alert at > 80% per container
- `container_memory_utilization` — alert at > 85% per container
- `node_cpu_utilization` — alert at > 75% (cluster capacity pressure)
- `node_memory_utilization` — alert at > 80%
- `pod_number_of_container_restarts` — alert at > 5 restarts in 10 min (crash loop)
- `cluster_node_count` — alert at < min_size (nodes failing to join)
- `cluster_failed_node_count` — alert at > 0

```bash
# Enable Container Insights on EKS cluster
aws eks update-cluster-config \
  --name app-cluster \
  --logging '{"clusterLogging":[{"types":["api","audit","authenticator","controllerManager","scheduler"],"enabled":true}]}'
```

---

## Cascading Failure Risk

EKS worker failure cascades to:
1. **ALB (aws_lb)** — if all EKS pods crash, ALB ingress returns 503
2. **Aurora (aws_rds_cluster)** — pending pod restarts create connection storm on DB pool
3. **ElastiCache** — Redis connection pool recreated for each new pod launch

Mitigation: `PodDisruptionBudget` ensures minimum replicas during node drain:
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: app-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: app-server
```
