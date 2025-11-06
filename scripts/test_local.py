#!/usr/bin/env python3
"""
Local test of Lambda function before deployment.
"""
import sys
import os
import json

# Set environment variables
os.environ['INDEX_BUCKET'] = 'faiss-rag-agent-vectors-039920874011'
os.environ['INDEX_KEY'] = 'faiss_index.bin'
os.environ['METADATA_KEY'] = 'metadata.json'
os.environ['MODEL_ID'] = 'us.amazon.nova-pro-v1:0'
os.environ['EMBEDDING_MODEL_ID'] = 'amazon.titan-embed-text-v2:0'
os.environ['AWS_REGION'] = 'us-west-2'

# Add lambda directory to path
sys.path.insert(0, '/persistent/home/ubuntu/workspace/faiss-rag-agent/lambda')

from query_handler import lambda_handler

def test_query(query_text):
    """Test a query locally."""
    print(f"\n{'='*60}")
    print(f"🔍 Testing Query: {query_text}")
    print(f"{'='*60}\n")
    
    event = {
        'body': json.dumps({'query': query_text})
    }
    
    response = lambda_handler(event, None)
    
    print(f"Status Code: {response['statusCode']}")
    
    if response['statusCode'] == 200:
        body = json.loads(response['body'])
        print(f"\n💬 Answer:\n{body['answer']}\n")
        print(f"📚 Top Repositories:")
        for i, repo in enumerate(body['repositories'][:3], 1):
            print(f"  {i}. {repo['repository']}")
            print(f"     Similarity: {repo['similarity_score']:.3f}")
            print(f"     Language: {repo['primary_language']}")
            print(f"     AWS Services: {repo['aws_services']}")
    else:
        print(f"❌ Error: {response['body']}")

if __name__ == '__main__':
    # Test queries
    test_query("Show me serverless examples with Lambda")
    test_query("I need Java samples for DevOps")
