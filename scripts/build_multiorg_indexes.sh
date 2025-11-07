#!/bin/bash
# Build FAISS indexes for multiple orgs and upload to S3

set -e

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
BUCKET="faiss-rag-agent-vectors-${ACCOUNT_ID}"

echo "🔨 Building Multi-Org FAISS Indexes"
echo "===================================="
echo "Bucket: s3://${BUCKET}"
echo ""

# Array of orgs to process
ORGS=("aws-samples" "awslabs")

for ORG in "${ORGS[@]}"; do
    echo "📊 Processing: $ORG"
    echo "-----------------------------------"
    
    # Step 1: Transform CSV to JSON
    echo "  1️⃣  Transforming CSV..."
    python3 scripts/transform_data.py --org $ORG
    
    # Step 2: Build FAISS index
    echo "  2️⃣  Building FAISS index..."
    python3 scripts/build_faiss_index.py --org $ORG
    
    # Step 3: Upload to S3
    echo "  3️⃣  Uploading to S3..."
    aws s3 cp data/faiss_index_${ORG}.bin s3://${BUCKET}/${ORG}/faiss_index.bin
    aws s3 cp data/metadata_${ORG}.json s3://${BUCKET}/${ORG}/metadata.json
    
    echo "  ✅ $ORG complete!"
    echo ""
done

echo "✅ All indexes built and uploaded!"
echo ""
echo "📁 S3 Structure:"
for ORG in "${ORGS[@]}"; do
    echo "  s3://${BUCKET}/${ORG}/"
    echo "    ├── faiss_index.bin"
    echo "    └── metadata.json"
done
