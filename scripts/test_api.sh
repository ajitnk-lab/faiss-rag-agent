#!/bin/bash
# Test deployed API Gateway endpoint

API_URL="https://lwemndu4dj.execute-api.us-east-1.amazonaws.com/prod/query"

echo "🔍 Testing Query: Show me Java DevOps samples"
echo "================================================"

curl -X POST "$API_URL" \
  -H "Content-Type: application/json" \
  -d '{"query": "Show me Java DevOps samples"}' \
  | python3 -m json.tool

echo -e "\n\n🔍 Testing Query: Serverless Lambda examples"
echo "================================================"

curl -X POST "$API_URL" \
  -H "Content-Type: application/json" \
  -d '{"query": "Serverless Lambda examples"}' \
  | python3 -m json.tool
