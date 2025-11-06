# AWS GitHub Research - End-to-End System Guide

Complete guide for the integrated AWS GitHub classification and RAG search system.

## 🎯 System Overview

Two interconnected projects working together:
1. **Classification System** - Classifies 7,552 AWS repositories using Nova Pro
2. **FAISS RAG Agent** - Provides intelligent search over classified repositories

**Total Cost**: ~$1/month (99.7% reduction from $345/month)

## 📊 Architecture

![End-to-End Architecture](generated-diagrams/end-to-end-architecture.png)

### Data Flow

```
GitHub API (7,552 repos)
    ↓
[1] Classification Pipeline (Run Once + Weekly Updates)
    ├─ Fetch repositories → S3
    ├─ Nova Pro classification → S3 (classification_results.csv)
    └─ Checkpoint tracking → S3 (nova_progress.json)
    ↓
[2] Index Building Pipeline (Run Weekly)
    ├─ Transform CSV → JSON
    ├─ Generate embeddings (Titan v2)
    ├─ Build FAISS index
    └─ Upload to S3 (faiss_index.bin)
    ↓
[3] Production RAG System (24/7)
    ├─ CloudFront CDN → Static UI
    ├─ API Gateway → Lambda
    ├─ FAISS vector search
    └─ Nova Pro LLM responses
```

## 🚀 Quick Start

### Prerequisites

```bash
# Required tools
- AWS CLI configured
- Python 3.10+
- Node.js 18+
- AWS CDK
- GitHub token (for classification)

# AWS Permissions needed
- S3 (read/write)
- Lambda (create/invoke)
- Bedrock (Nova Pro, Titan Embeddings)
- API Gateway, CloudFront
```

### Initial Setup (Run Once)

```bash
# 1. Clone both repositories
git clone https://github.com/ajitnk-lab/awsgithubresearch.git
git clone https://github.com/ajitnk-lab/faiss-rag-agent.git

# 2. Set up classification system
cd awsgithubresearch
export GITHUB_TOKEN="your_github_token_here"

# 3. Fetch repository list (Run Once)
python3 generic_fetch_repos.py aws-samples

# 4. Start classification (Run Once - takes ~2 hours)
python3 resumable_nova_classifier.py aws-samples --batch-size 500 --github-token $GITHUB_TOKEN
```

## 📋 Operational Commands

### 1. Classification System

#### One-Time Operations

```bash
# Fetch repository list (only when starting fresh)
cd /path/to/awsgithubresearch
python3 generic_fetch_repos.py aws-samples

# Initial classification (7,552 repos, ~2 hours)
python3 resumable_nova_classifier.py aws-samples \
  --batch-size 500 \
  --github-token $GITHUB_TOKEN
```

#### Weekly Operations

```bash
# Update repository list (captures new repos)
cd /path/to/awsgithubresearch
python3 generic_fetch_repos.py aws-samples

# Classify only new repositories (typically 10-50 new repos)
python3 resumable_nova_classifier.py aws-samples \
  --batch-size 100 \
  --github-token $GITHUB_TOKEN

# Expected time: 2-5 minutes for ~50 new repos
```

#### Monitoring Classification Progress

```bash
# Check current progress
aws s3 cp s3://aws-github-repo-classification-aws-samples/checkpoints/nova_progress.json - | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(f'Completed: {d[\"total_processed\"]}/7552 ({d[\"total_processed\"]/7552*100:.1f}%)')
print(f'Last run: {d[\"last_run\"]}')
"

# View latest results
aws s3 cp s3://aws-github-repo-classification-aws-samples/results/classification_results.csv - | head -20
```

### 2. FAISS RAG System

#### One-Time Deployment

```bash
# Deploy infrastructure (Run Once)
cd /path/to/faiss-rag-agent
./deploy.sh

# Expected time: 5-10 minutes
# Output: API Gateway URL, CloudFront URL
```

#### Weekly Index Rebuild

```bash
# Rebuild FAISS index with latest classifications
cd /path/to/faiss-rag-agent

# Step 1: Transform latest CSV data
python3 scripts/transform_data.py

# Step 2: Build new FAISS index
python3 scripts/build_faiss_index.py

# Step 3: Upload to S3
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
aws s3 cp data/faiss_index.bin s3://faiss-rag-agent-vectors-${ACCOUNT_ID}/
aws s3 cp data/metadata.json s3://faiss-rag-agent-vectors-${ACCOUNT_ID}/

# Expected time: 5-10 minutes
# Lambda will automatically use new index on next cold start
```

#### Testing Production System

```bash
# Test API endpoint
curl -X POST https://YOUR_API_GATEWAY_URL/prod/query \
  -H "Content-Type: application/json" \
  -d '{"query": "serverless API with authentication"}'

# Test via web UI
open https://awssolutionfinder.solutions.cloudnestle.com
```

## 📅 Operational Schedule

### Daily Operations
**None required** - System runs automatically

### Weekly Operations (Recommended: Every Monday)

```bash
#!/bin/bash
# weekly-update.sh

set -e

echo "🔄 Weekly Update - $(date)"

# 1. Update classifications (5-10 minutes)
echo "📊 Step 1: Updating classifications..."
cd /path/to/awsgithubresearch
python3 generic_fetch_repos.py aws-samples
python3 resumable_nova_classifier.py aws-samples --batch-size 100 --github-token $GITHUB_TOKEN

# 2. Rebuild FAISS index (5-10 minutes)
echo "🔨 Step 2: Rebuilding FAISS index..."
cd /path/to/faiss-rag-agent
python3 scripts/transform_data.py
python3 scripts/build_faiss_index.py

# 3. Upload to S3
echo "☁️  Step 3: Uploading to S3..."
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
aws s3 cp data/faiss_index.bin s3://faiss-rag-agent-vectors-${ACCOUNT_ID}/
aws s3 cp data/metadata.json s3://faiss-rag-agent-vectors-${ACCOUNT_ID}/

echo "✅ Weekly update complete!"
```

### Monthly Operations
- Review cost reports in AWS Cost Explorer
- Check CloudWatch metrics for errors
- Verify classification quality (sample 10-20 repos)

## 🔍 Monitoring & Troubleshooting

### Check Classification Status

```bash
# Total repositories classified
aws s3 ls s3://aws-github-repo-classification-aws-samples/results/classification_results.csv --human-readable

# Latest checkpoint
aws s3 cp s3://aws-github-repo-classification-aws-samples/checkpoints/nova_progress.json - | jq .

# Classification errors (if any)
aws s3 cp s3://aws-github-repo-classification-aws-samples/checkpoints/nova_progress.json - | jq '.failed_repos'
```

### Check RAG System Health

```bash
# Lambda metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=FaissRagStack-QueryHandler \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Sum

# API Gateway metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/ApiGateway \
  --metric-name Count \
  --dimensions Name=ApiName,Value=FaissRagStack \
  --start-time $(date -u -d '1 day ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 86400 \
  --statistics Sum
```

### Common Issues

#### Classification Stuck
```bash
# Check if process is running
ps aux | grep resumable_nova_classifier

# Resume from checkpoint
python3 resumable_nova_classifier.py aws-samples --batch-size 100 --github-token $GITHUB_TOKEN
```

#### RAG System Not Responding
```bash
# Check Lambda logs
aws logs tail /aws/lambda/FaissRagStack-QueryHandler --follow

# Force Lambda cold start (loads new index)
aws lambda update-function-configuration \
  --function-name FaissRagStack-QueryHandler \
  --environment Variables={FORCE_RELOAD=true}
```

#### Index Out of Date
```bash
# Check index timestamp
aws s3 ls s3://faiss-rag-agent-vectors-${ACCOUNT_ID}/ --human-readable

# Rebuild immediately
cd /path/to/faiss-rag-agent
./scripts/rebuild_index.sh
```

## 💰 Cost Breakdown

### Monthly Costs

**Classification System:**
- Nova Pro: $15 (7,552 repos × $0.002)
- S3 Storage: $0.01
- **One-time cost, then $0.20/month for updates**

**FAISS RAG System:**
- S3 Storage: $0.01/month
- Lambda: $0.50/month (1000 requests)
- Nova Pro: $0.28/month (1000 requests)
- Embeddings: $0.002/month
- API Gateway: $0.01/month
- CloudFront: $0.10/month
- **Total: ~$1/month**

**Combined Monthly Cost: ~$1.20/month**

### Cost Comparison
- **Old System**: $345/month (OpenSearch Serverless)
- **New System**: $1.20/month
- **Savings**: 99.7% ($343.80/month)

## 🔐 Security Best Practices

```bash
# Rotate GitHub token quarterly
export GITHUB_TOKEN="new_token"

# Review IAM permissions
aws iam get-role-policy --role-name FaissRagStack-QueryHandlerRole --policy-name default

# Enable CloudTrail for audit
aws cloudtrail create-trail --name faiss-rag-audit --s3-bucket-name my-audit-bucket

# Enable S3 versioning
aws s3api put-bucket-versioning \
  --bucket aws-github-repo-classification-aws-samples \
  --versioning-configuration Status=Enabled
```

## 📊 Performance Metrics

### Classification System
- **Throughput**: ~1 repo/second
- **Accuracy**: 95%+ (based on manual review)
- **Cost per repo**: $0.002

### RAG System
- **Cold Start**: 7.9s
- **Warm Start**: 6-7s
- **Search Latency**: 0.001s (FAISS)
- **Availability**: 99.9%+

## 🔄 Disaster Recovery

### Backup Strategy

```bash
# Backup classification results (weekly)
aws s3 sync s3://aws-github-repo-classification-aws-samples/ \
  s3://backup-bucket/classification-$(date +%Y%m%d)/ \
  --exclude "*" --include "results/*" --include "checkpoints/*"

# Backup FAISS index (weekly)
aws s3 sync s3://faiss-rag-agent-vectors-${ACCOUNT_ID}/ \
  s3://backup-bucket/vectors-$(date +%Y%m%d)/
```

### Recovery Procedures

```bash
# Restore classification data
aws s3 sync s3://backup-bucket/classification-20251106/ \
  s3://aws-github-repo-classification-aws-samples/

# Restore FAISS index
aws s3 sync s3://backup-bucket/vectors-20251106/ \
  s3://faiss-rag-agent-vectors-${ACCOUNT_ID}/

# Redeploy infrastructure
cd /path/to/faiss-rag-agent
cdk destroy
cdk deploy
```

## 📚 Additional Resources

- **Classification Repo**: https://github.com/ajitnk-lab/awsgithubresearch
- **FAISS RAG Repo**: https://github.com/ajitnk-lab/faiss-rag-agent
- **Live Demo**: https://awssolutionfinder.solutions.cloudnestle.com
- **AWS Bedrock Docs**: https://docs.aws.amazon.com/bedrock/
- **FAISS Documentation**: https://github.com/facebookresearch/faiss

## 🤝 Support

For issues or questions:
1. Check troubleshooting section above
2. Review CloudWatch logs
3. Open GitHub issue in respective repository
4. Contact: ajit@cloudnestle.com

---

**Last Updated**: 2025-11-06
**Version**: 2.0.0
