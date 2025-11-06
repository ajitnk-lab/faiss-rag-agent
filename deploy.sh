#!/bin/bash
set -e

echo "🚀 FAISS RAG Agent - Quick Deploy Script"
echo "========================================"

# Get AWS account info
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=${AWS_REGION:-us-east-1}

echo "📋 Account: $ACCOUNT_ID"
echo "📋 Region: $REGION"
echo ""

# Check prerequisites
echo "✓ Checking prerequisites..."
command -v aws >/dev/null 2>&1 || { echo "❌ AWS CLI not found"; exit 1; }
command -v node >/dev/null 2>&1 || { echo "❌ Node.js not found"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "❌ Python3 not found"; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "❌ Docker not found"; exit 1; }
echo "✅ All prerequisites met"
echo ""

# Step 1: Create S3 bucket
echo "📦 Step 1: Creating S3 bucket for FAISS index..."
BUCKET_NAME="faiss-rag-agent-vectors-${ACCOUNT_ID}"
aws s3 mb s3://${BUCKET_NAME} --region ${REGION} 2>/dev/null || echo "Bucket already exists"
echo "✅ Bucket ready: ${BUCKET_NAME}"
echo ""

# Step 2: Check if index files exist
echo "📊 Step 2: Checking FAISS index files..."
if [ ! -f "data/faiss_index.bin" ] || [ ! -f "data/metadata.json" ]; then
    echo "⚠️  Index files not found. Please run:"
    echo "   python3 scripts/transform_data.py 925"
    echo "   python3 scripts/build_faiss_index.py"
    exit 1
fi
echo "✅ Index files found"
echo ""

# Step 3: Upload index to S3
echo "☁️  Step 3: Uploading index to S3..."
aws s3 cp data/faiss_index.bin s3://${BUCKET_NAME}/faiss_index.bin
aws s3 cp data/metadata.json s3://${BUCKET_NAME}/metadata.json
echo "✅ Index uploaded"
echo ""

# Step 4: Deploy CDK stack
echo "🏗️  Step 4: Deploying CDK stack..."
cd cdk
npm install --silent
npm run build
npx cdk bootstrap aws://${ACCOUNT_ID}/${REGION} 2>/dev/null || true
npx cdk deploy --require-approval never
cd ..
echo "✅ Stack deployed"
echo ""

# Step 5: Get outputs
echo "📋 Step 5: Deployment Complete!"
echo "================================"
aws cloudformation describe-stacks \
  --stack-name FaissRagStack \
  --region ${REGION} \
  --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue]' \
  --output table

echo ""
echo "🧪 Test your deployment:"
API_URL=$(aws cloudformation describe-stacks \
  --stack-name FaissRagStack \
  --region ${REGION} \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiUrl`].OutputValue' \
  --output text)

echo "curl -X POST '${API_URL}query' \\"
echo "  -H 'Content-Type: application/json' \\"
echo "  -d '{\"query\": \"serverless Lambda with DynamoDB\"}'"
echo ""

UI_URL=$(aws cloudformation describe-stacks \
  --stack-name FaissRagStack \
  --region ${REGION} \
  --query 'Stacks[0].Outputs[?OutputKey==`UIUrl`].OutputValue' \
  --output text)

echo "🌐 Chat UI: ${UI_URL}"
echo ""
echo "✅ Deployment successful!"
