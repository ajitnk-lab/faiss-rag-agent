"""
Lambda function for FAISS-based RAG queries with Nova Pro.
"""
import json
import boto3
import os
import faiss
import numpy as np
import time
from typing import List, Dict

# Global variables for caching (warm Lambda)
faiss_index = None
metadata = None
s3_client = None
bedrock_client = None

def load_index_from_s3():
    """Load FAISS index and metadata from S3 (cached in warm Lambda)."""
    global faiss_index, metadata, s3_client
    
    start_time = time.time()
    
    if faiss_index is not None:
        print(f"⚡ Using cached index (warm start)")
        return faiss_index, metadata
    
    bucket = os.environ['INDEX_BUCKET']
    index_key = os.environ['INDEX_KEY']
    metadata_key = os.environ['METADATA_KEY']
    
    if s3_client is None:
        s3_client = boto3.client('s3')
    
    print(f"📥 Loading FAISS index from s3://{bucket}/{index_key}")
    
    # Download index
    download_start = time.time()
    index_path = '/tmp/faiss_index.bin'
    s3_client.download_file(bucket, index_key, index_path)
    download_time = time.time() - download_start
    print(f"  ⏱️  S3 download: {download_time:.2f}s")
    
    # Load FAISS index
    load_start = time.time()
    faiss_index = faiss.read_index(index_path)
    load_time = time.time() - load_start
    print(f"  ⏱️  FAISS load: {load_time:.2f}s")
    
    # Download metadata
    metadata_start = time.time()
    metadata_obj = s3_client.get_object(Bucket=bucket, Key=metadata_key)
    metadata = json.loads(metadata_obj['Body'].read().decode('utf-8'))
    metadata_time = time.time() - metadata_start
    print(f"  ⏱️  Metadata load: {metadata_time:.2f}s")
    
    total_time = time.time() - start_time
    print(f"✅ Loaded index with {faiss_index.ntotal} vectors in {total_time:.2f}s")
    return faiss_index, metadata

def generate_query_embedding(query_text: str) -> np.ndarray:
    """Generate embedding for query using Bedrock Titan."""
    global bedrock_client
    
    start_time = time.time()
    
    if bedrock_client is None:
        bedrock_client = boto3.client('bedrock-runtime', region_name=os.environ.get('AWS_REGION', 'us-west-2'))
    
    model_id = os.environ['EMBEDDING_MODEL_ID']
    
    response = bedrock_client.invoke_model(
        modelId=model_id,
        body=json.dumps({
            "inputText": query_text[:8000],
            "dimensions": 1024,
            "normalize": True
        })
    )
    
    result = json.loads(response['body'].read())
    elapsed = time.time() - start_time
    print(f"  ⏱️  Embedding generation: {elapsed:.2f}s")
    return np.array([result['embedding']], dtype='float32')

def search_faiss(query_embedding: np.ndarray, k: int = 5) -> List[Dict]:
    """Search FAISS index and return top-k results."""
    start_time = time.time()
    index, meta = load_index_from_s3()
    
    search_start = time.time()
    distances, indices = index.search(query_embedding, k)
    search_time = time.time() - search_start
    print(f"  ⏱️  FAISS search: {search_time:.3f}s")
    
    results = []
    for i, idx in enumerate(indices[0]):
        if idx < len(meta):
            result = meta[idx].copy()
            result['similarity_score'] = float(1 / (1 + distances[0][i]))  # Convert distance to similarity
            results.append(result)
    
    total_time = time.time() - start_time
    print(f"  ⏱️  Total search: {total_time:.2f}s")
    return results

def generate_response_with_nova(query: str, context_repos: List[Dict]) -> str:
    """Generate response using Nova Pro with retrieved context."""
    global bedrock_client
    
    start_time = time.time()
    
    if bedrock_client is None:
        bedrock_client = boto3.client('bedrock-runtime', region_name=os.environ.get('AWS_REGION', 'us-west-2'))
    
    # Build context from retrieved repos
    context_text = "\n\n".join([
        f"Repository: {repo['repository']}\n"
        f"Description: {repo['description']}\n"
        f"Solution Type: {repo['solution_type']}\n"
        f"Competency: {repo['competency']}\n"
        f"AWS Services: {repo['aws_services']}\n"
        f"Primary Language: {repo['primary_language']}"
        for repo in context_repos[:3]  # Top 3 repos
    ])
    
    prompt = f"""You are an AWS solutions expert. Based on the following AWS sample repositories, answer the user's question.

Retrieved Repositories:
{context_text}

User Question: {query}

Provide a helpful answer based ONLY on the repositories above. Include repository names and relevant details."""
    
    # Use inference profile for Nova Pro
    model_id = os.environ.get('MODEL_ID', 'us.amazon.nova-pro-v1:0')
    
    response = bedrock_client.invoke_model(
        modelId=model_id,
        body=json.dumps({
            "messages": [
                {
                    "role": "user",
                    "content": [{"text": prompt}]
                }
            ],
            "inferenceConfig": {
                "maxTokens": 500,
                "temperature": 0.7
            }
        })
    )
    
    result = json.loads(response['body'].read())
    elapsed = time.time() - start_time
    print(f"  ⏱️  Nova Pro generation: {elapsed:.2f}s")
    return result['output']['message']['content'][0]['text']

def lambda_handler(event, context):
    """Main Lambda handler - supports both API Gateway and Bedrock Agent."""
    handler_start = time.time()
    
    try:
        print(f"📥 Event: {json.dumps(event)[:500]}")
        
        # Detect if this is from Bedrock Agent
        if 'agent' in event or 'actionGroup' in event:
            return handle_bedrock_agent(event, handler_start)
        
        # API Gateway format
        body = json.loads(event.get('body', '{}'))
        query = body.get('query', '')
        
        if not query:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'Query parameter required'})
            }
        
        print(f"🔍 Query: {query}")
        
        # Generate query embedding
        embedding_start = time.time()
        query_embedding = generate_query_embedding(query)
        
        # Search FAISS
        search_start = time.time()
        results = search_faiss(query_embedding, k=5)
        
        # Generate response with Nova Pro
        llm_start = time.time()
        response_text = generate_response_with_nova(query, results)
        
        total_time = time.time() - handler_start
        print(f"⏱️  TOTAL EXECUTION TIME: {total_time:.2f}s")
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'answer': response_text,
                'repositories': results,
                'query': query,
                'execution_time_seconds': round(total_time, 2)
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

def handle_bedrock_agent(event, start_time):
    """Handle Bedrock Agent action group invocation."""
    print("🤖 Bedrock Agent request")
    
    # Extract parameters from agent event
    api_path = event.get('apiPath', '')
    parameters = event.get('parameters', [])
    
    query = None
    for param in parameters:
        if param.get('name') == 'query':
            query = param.get('value')
            break
    
    if not query:
        return {
            'messageVersion': '1.0',
            'response': {
                'actionGroup': event.get('actionGroup'),
                'apiPath': api_path,
                'httpMethod': event.get('httpMethod'),
                'httpStatusCode': 400,
                'responseBody': {
                    'application/json': {
                        'body': json.dumps({'error': 'Query parameter required'})
                    }
                }
            }
        }
    
    print(f"🔍 Agent Query: {query}")
    
    # Search repositories
    query_embedding = generate_query_embedding(query)
    results = search_faiss(query_embedding, k=5)
    
    total_time = time.time() - start_time
    print(f"⏱️  TOTAL EXECUTION TIME: {total_time:.2f}s")
    
    # Return in Bedrock Agent format
    return {
        'messageVersion': '1.0',
        'response': {
            'actionGroup': event.get('actionGroup'),
            'apiPath': api_path,
            'httpMethod': event.get('httpMethod'),
            'httpStatusCode': 200,
            'responseBody': {
                'application/json': {
                    'body': json.dumps({
                        'repositories': results,
                        'query': query,
                        'execution_time_seconds': round(total_time, 2)
                    })
                }
            }
        }
    }
