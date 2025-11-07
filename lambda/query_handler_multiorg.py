"""
Multi-org Lambda function for FAISS-based RAG queries with Nova Pro.
Supports dynamic loading of different organization indexes.
"""
import json
import boto3
import os
import faiss
import numpy as np
import time
from typing import List, Dict

# Global cache for multiple org indexes
index_cache = {}
metadata_cache = {}
s3_client = None
bedrock_client = None

def load_index_for_org(org: str):
    """Load FAISS index and metadata for specific org (cached)."""
    global index_cache, metadata_cache, s3_client
    
    if org in index_cache:
        print(f"⚡ Using cached index for {org}")
        return index_cache[org], metadata_cache[org]
    
    start_time = time.time()
    bucket = os.environ['INDEX_BUCKET']
    
    if s3_client is None:
        s3_client = boto3.client('s3')
    
    print(f"📥 Loading FAISS index for {org} from s3://{bucket}/{org}/")
    
    # Download index
    download_start = time.time()
    index_path = f'/tmp/faiss_index_{org}.bin'
    metadata_path = f'/tmp/metadata_{org}.json'
    
    s3_client.download_file(bucket, f'{org}/faiss_index.bin', index_path)
    s3_client.download_file(bucket, f'{org}/metadata.json', metadata_path)
    download_time = time.time() - download_start
    print(f"  ⏱️  S3 download: {download_time:.2f}s")
    
    # Load FAISS index
    load_start = time.time()
    index = faiss.read_index(index_path)
    load_time = time.time() - load_start
    print(f"  ⏱️  FAISS load: {load_time:.2f}s")
    
    # Load metadata
    with open(metadata_path, 'r') as f:
        metadata = json.load(f)
    
    # Cache it
    index_cache[org] = index
    metadata_cache[org] = metadata
    
    total_time = time.time() - start_time
    print(f"✅ Loaded {org} index in {total_time:.2f}s ({index.ntotal} vectors)")
    
    return index, metadata

def get_embedding(text: str) -> np.ndarray:
    """Generate embedding using Titan Embeddings v2."""
    global bedrock_client
    
    if bedrock_client is None:
        bedrock_client = boto3.client('bedrock-runtime', region_name='us-east-1')
    
    start_time = time.time()
    
    response = bedrock_client.invoke_model(
        modelId='amazon.titan-embed-text-v2:0',
        body=json.dumps({"inputText": text})
    )
    
    result = json.loads(response['body'].read())
    embedding = np.array(result['embedding'], dtype=np.float32)
    
    print(f"  ⏱️  Embedding: {time.time()-start_time:.2f}s")
    return embedding

def search_faiss(index, metadata: List[Dict], query_embedding: np.ndarray, k: int = 5):
    """Search FAISS index and return top-k results."""
    start_time = time.time()
    
    # Search
    distances, indices = index.search(query_embedding.reshape(1, -1), k)
    
    # Get results
    results = []
    for i, idx in enumerate(indices[0]):
        if idx < len(metadata):
            result = metadata[idx].copy()
            result['score'] = float(distances[0][i])
            results.append(result)
    
    print(f"  ⏱️  FAISS search: {time.time()-start_time:.3f}s")
    return results

def generate_response(query: str, context: List[Dict]) -> str:
    """Generate response using Nova Pro."""
    global bedrock_client
    
    if bedrock_client is None:
        bedrock_client = boto3.client('bedrock-runtime', region_name='us-east-1')
    
    start_time = time.time()
    
    # Build context
    context_text = "\n\n".join([
        f"Repository: {r['repository']}\n"
        f"Type: {r.get('solution_type', 'N/A')}\n"
        f"Description: {r.get('description', 'N/A')}\n"
        f"AWS Services: {r.get('aws_services', 'N/A')}\n"
        f"Use Case: {r.get('customer_problems', 'N/A')}"
        for r in context[:3]
    ])
    
    prompt = f"""Based on these AWS repositories, answer the question:

{context_text}

Question: {query}

Provide a helpful answer with specific repository recommendations."""
    
    response = bedrock_client.invoke_model(
        modelId='us.amazon.nova-pro-v1:0',
        body=json.dumps({
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": {"temperature": 0.7, "maxTokens": 500}
        })
    )
    
    result = json.loads(response['body'].read())
    answer = result['output']['message']['content'][0]['text']
    
    print(f"  ⏱️  Nova Pro: {time.time()-start_time:.2f}s")
    return answer

def lambda_handler(event, context):
    """Main Lambda handler supporting multi-org queries."""
    start_time = time.time()
    
    try:
        # Parse request
        if 'body' in event:
            body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
        else:
            body = event
        
        query = body.get('query', '')
        org = body.get('org', 'aws-samples')  # Default to aws-samples
        k = body.get('k', 5)
        
        if not query:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'Query parameter required'})
            }
        
        print(f"🔍 Query: {query}")
        print(f"🏢 Organization: {org}")
        
        # Load index for requested org
        index, metadata = load_index_for_org(org)
        
        # Generate embedding
        query_embedding = get_embedding(query)
        
        # Search
        results = search_faiss(index, metadata, query_embedding, k)
        
        # Generate response
        answer = generate_response(query, results)
        
        total_time = time.time() - start_time
        print(f"✅ Total time: {total_time:.2f}s")
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'answer': answer,
                'results': results,
                'org': org,
                'total_time': round(total_time, 2)
            })
        }
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)})
        }
