# FAISS RAG Agent - Deployment Guide

## Prerequisites

1. **AWS Account** with:
   - Bedrock access (Nova Pro model enabled)
   - Sufficient permissions (Administrator or equivalent)
   
2. **Local Environment**:
   - AWS CLI configured (`aws configure`)
   - Node.js 18+ and npm
   - Python 3.10+
   - Docker (for Lambda container builds)

3. **Required Python packages**:
   ```bash
   pip3 install boto3 faiss-cpu numpy
   ```

## Step 1: Prepare Data

### Option A: Use Existing Classification Data
```bash
# If you have the classifier project, use its output
# The classifier CSV should be at:
# s3://aws-github-repo-classification-aws-samples/results/classification_results.csv
```

### Option B: Run Classifier (if starting fresh)
```bash
cd /path/to/classifier-project
python3 smart_rate_limit_classifier.py aws-samples --github-token YOUR_TOKEN
```

## Step 2: Generate FAISS Index

```bash
cd faiss-rag-agent

# Transform CSV to JSON (adjust limit for your dataset size)
python3 scripts/transform_data.py 925

# Generate embeddings and build FAISS index
python3 scripts/build_faiss_index.py

# Output: 
# - data/faiss_index.bin
# - data/metadata.json
```

## Step 3: Create S3 Bucket for Index

```bash
# Replace with your account ID and region
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=us-east-1

aws s3 mb s3://faiss-rag-agent-vectors-${ACCOUNT_ID} --region ${REGION}

# Upload index files
aws s3 cp data/faiss_index.bin s3://faiss-rag-agent-vectors-${ACCOUNT_ID}/
aws s3 cp data/metadata.json s3://faiss-rag-agent-vectors-${ACCOUNT_ID}/
```

## Step 4: Deploy CDK Stack

```bash
cd cdk

# Install dependencies
npm install

# Bootstrap CDK (first time only)
npx cdk bootstrap

# Build TypeScript
npm run build

# Deploy
npx cdk deploy --require-approval never
```

**Deployment takes ~5-10 minutes** (Lambda container build is the longest part)

## Step 5: Get Outputs

```bash
aws cloudformation describe-stacks \
  --stack-name FaissRagStack \
  --region ${REGION} \
  --query 'Stacks[0].Outputs' \
  --output table
```

You'll get:
- **ApiUrl**: API Gateway endpoint
- **UIUrl**: CloudFront URL for chat interface
- **LambdaFunction**: Lambda function name
- **IndexBucket**: S3 bucket name

## Step 6: Test

### Test API Gateway
```bash
API_URL=$(aws cloudformation describe-stacks \
  --stack-name FaissRagStack \
  --region ${REGION} \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiUrl`].OutputValue' \
  --output text)

curl -X POST "${API_URL}query" \
  -H "Content-Type: application/json" \
  -d '{"query": "serverless Lambda with DynamoDB"}'
```

### Test UI
```bash
UI_URL=$(aws cloudformation describe-stacks \
  --stack-name FaissRagStack \
  --region ${REGION} \
  --query 'Stacks[0].Outputs[?OutputKey==`UIUrl`].OutputValue' \
  --output text)

echo "Open: ${UI_URL}"
```

## Step 7: (Optional) Create Bedrock Agent

```bash
cd ..
python3 scripts/create_bedrock_agent.py
```

This creates:
- Bedrock Agent with Nova Pro
- Action Group linked to Lambda
- IAM role with permissions

## Troubleshooting

### Issue: Lambda timeout
**Solution**: Increase memory (more memory = faster CPU)
```bash
aws lambda update-function-configuration \
  --function-name <LAMBDA_NAME> \
  --memory-size 2048 \
  --region ${REGION}
```

### Issue: CloudFront 403 error
**Solution**: Wait 2-3 minutes for distribution to deploy, then invalidate cache
```bash
DIST_ID=$(aws cloudfront list-distributions \
  --query "DistributionList.Items[?Origins.Items[0].DomainName contains 'uibucket'].Id" \
  --output text)

aws cloudfront create-invalidation \
  --distribution-id ${DIST_ID} \
  --paths "/*"
```

### Issue: Bedrock model not available
**Solution**: Enable Nova Pro in Bedrock console
```
https://console.aws.amazon.com/bedrock/home?region=us-east-1#/modelaccess
```

## Cost Estimate

**Monthly costs (925 repositories, 1000 queries/month):**
- S3 storage: $0.01 (4MB index)
- Lambda: $0.50 (1000 invocations × 7s × 1024MB)
- Bedrock Nova Pro: $0.28 (1000 queries)
- Bedrock Embeddings: $0.002 (1000 queries)
- API Gateway: $0.01 (1000 requests)
- CloudFront: $0.10 (minimal traffic)

**Total: ~$1/month** (vs $345/month with OpenSearch)

## Cleanup

```bash
# Delete stack
npx cdk destroy

# Delete S3 bucket (if needed)
aws s3 rm s3://faiss-rag-agent-vectors-${ACCOUNT_ID} --recursive
aws s3 rb s3://faiss-rag-agent-vectors-${ACCOUNT_ID}

# Delete Bedrock Agent (if created)
aws bedrock-agent delete-agent --agent-id <AGENT_ID> --region ${REGION}
```

## Multi-Region Deployment

To deploy in a different region:

```bash
export AWS_REGION=us-west-2

# Update CDK app.ts if needed
cd cdk
npx cdk deploy --require-approval never
```

## Production Checklist

- [ ] Enable CloudWatch alarms for Lambda errors
- [ ] Set up API Gateway throttling/rate limits
- [ ] Enable CloudFront access logs
- [ ] Configure custom domain for UI (optional)
- [ ] Set up CI/CD pipeline (optional)
- [ ] Enable AWS WAF for API Gateway (optional)
- [ ] Configure backup for S3 index bucket
- [ ] Document API endpoints for users
- [ ] Set up monitoring dashboard

## Support

For issues or questions:
1. Check CloudWatch logs: `/aws/lambda/<LAMBDA_NAME>`
2. Review CDK deployment logs
3. Verify Bedrock model access in console
