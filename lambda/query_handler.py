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
from datetime import datetime
from typing import List, Dict

# Global cache for multiple org indexes
index_cache = {}
metadata_cache = {}
s3_client = None
bedrock_client = None
dynamodb = None

def get_user_from_api_key(api_key: str):
    """Get user info from marketplace API key."""
    global dynamodb
    
    if dynamodb is None:
        dynamodb = boto3.resource('dynamodb')
    
    # Marketplace user table
    user_table = dynamodb.Table('MP-1759859484941-DataStackUserTableDAF10CB8-32RMTH8QZDCX')
    
    try:
        # Scan for user with this API key (in production, use GSI for better performance)
        response = user_table.scan(
            FilterExpression='awsFinderApiKey = :api_key',
            ExpressionAttributeValues={':api_key': api_key}
        )
        
        if response['Items']:
            user = response['Items'][0]
            return {
                'user_id': user['userId'],
                'email': user.get('email', 'unknown'),
                'tier': user.get('awsFinderTier', 'free'),
                'role': user.get('role', 'customer')
            }
        return None
        
    except Exception as e:
        print(f"Error looking up API key: {e}")
        return None

def get_user_id(event):
    """Generate user ID from API key or fallback to IP."""
    # Check for API key in query parameters or headers
    api_key = None
    
    # Try query parameters first
    if 'queryStringParameters' in event and event['queryStringParameters']:
        api_key = event['queryStringParameters'].get('apikey')
    
    # Try headers as fallback
    if not api_key and 'headers' in event:
        api_key = event['headers'].get('x-api-key') or event['headers'].get('Authorization', '').replace('Bearer ', '')
    
    # Try request body
    if not api_key:
        try:
            if 'body' in event:
                body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
                api_key = body.get('apikey')
        except:
            pass
    
    if api_key:
        user_info = get_user_from_api_key(api_key)
        if user_info:
            return user_info['user_id'], user_info['tier'], user_info
    
    # Fallback to IP-based identification for anonymous users
    source_ip = event.get('requestContext', {}).get('identity', {}).get('sourceIp', 'unknown')
    user_agent = event.get('headers', {}).get('User-Agent', '')
    fingerprint = f"{source_ip}_{hash(user_agent) % 10000}"
    
    return fingerprint, 'anonymous', None

def check_usage_limits(user_id: str, tier: str = 'anonymous', user_info: dict = None):
    """Check if user has exceeded usage limits."""
    global dynamodb
    
    if dynamodb is None:
        dynamodb = boto3.resource('dynamodb')
    
    table = dynamodb.Table(os.environ['USAGE_TABLE'])
    today = datetime.now().strftime('%Y-%m-%d')
    
    try:
        # Get current usage
        response = table.get_item(
            Key={'user_id': user_id, 'date': today}
        )
        
        current_count = response.get('Item', {}).get('count', 0)
        if hasattr(current_count, '__float__'):  # Handle Decimal objects
            current_count = int(current_count)
        
        # Define limits based on tier
        limits = {
            'anonymous': 3,      # Anonymous users: 3 searches total
            'free': 10,          # Registered customers: 10 searches/day
            'pro': float('inf')  # Pro customers: unlimited
        }
        
        limit = limits.get(tier, 3)
        searches_remaining = max(0, limit - current_count) if limit != float('inf') else float('inf')
        
        # Add user context for registered users
        user_context = {}
        if user_info:
            user_context = {
                'email': user_info.get('email'),
                'role': user_info.get('role')
            }
        
        return {
            'allowed': current_count < limit,
            'searches_used': current_count,
            'searches_remaining': searches_remaining if searches_remaining != float('inf') else 'unlimited',
            'tier': tier,
            'upgrade_needed': current_count >= limit,
            'user_context': user_context
        }
        
    except Exception as e:
        print(f"Error checking usage: {e}")
        # Allow on error
        return {
            'allowed': True,
            'searches_used': 0,
            'searches_remaining': 3 if tier == 'anonymous' else 10,
            'tier': tier,
            'upgrade_needed': False,
            'user_context': {}
        }

def increment_usage(user_id: str, tier: str = 'anonymous'):
    """Increment usage count for user."""
    global dynamodb
    
    if dynamodb is None:
        dynamodb = boto3.resource('dynamodb')
    
    table = dynamodb.Table(os.environ['USAGE_TABLE'])
    today = datetime.now().strftime('%Y-%m-%d')
    timestamp = datetime.now().isoformat()
    
    try:
        table.put_item(
            Item={
                'user_id': user_id,
                'date': today,
                'count': 1,
                'tier': tier,
                'timestamp': timestamp
            },
            ConditionExpression='attribute_not_exists(user_id)'
        )
    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        # Item exists, increment count
        table.update_item(
            Key={'user_id': user_id, 'date': today},
            UpdateExpression='ADD #count :inc SET #timestamp = :timestamp',
            ExpressionAttributeNames={'#count': 'count', '#timestamp': 'timestamp'},
            ExpressionAttributeValues={':inc': 1, ':timestamp': timestamp}
        )
    except Exception as e:
        print(f"Error incrementing usage: {e}")

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
    
    # Build context with more details
    context_text = "\n\n".join([
        f"#{i+1}. {r['repository']}\n"
        f"   - Solution Type: {r.get('solution_type', 'N/A')}\n"
        f"   - Competency: {r.get('competency', 'N/A')}\n"
        f"   - AWS Services: {r.get('aws_services', 'N/A')}\n"
        f"   - Language: {r.get('primary_language', 'N/A')}\n"
        f"   - Problem Solved: {r.get('customer_problems', 'N/A')}"
        for i, r in enumerate(context[:5])
    ])
    
    prompt = f"""You are analyzing search results from a FAISS vector database of AWS sample repositories.

TOP 5 MOST RELEVANT REPOSITORIES FOR THIS QUERY:
{context_text}

User's Question: {query}

CRITICAL INSTRUCTIONS:
- Your answer MUST be based ONLY on the repositories listed above
- Start by saying "Based on the search results, here are the most relevant repositories:"
- List each repository by its EXACT name (e.g., aws-samples/aws-dynamodb-examples)
- Explain why each is relevant based on its competency and AWS services
- Do NOT suggest any repositories not in the list above
- Do NOT provide general AWS advice - focus on these specific repos

Answer:"""
    
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
    """Main Lambda handler supporting multi-org queries with usage tracking."""
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
        
        # Get user ID and check usage limits
        user_id, tier, user_info = get_user_id(event)
        usage_info = check_usage_limits(user_id, tier, user_info)
        
        print(f"🔍 Query: {query}")
        print(f"🏢 Organization: {org}")
        print(f"👤 User: {user_id}")
        print(f"🎯 Tier: {tier}")
        print(f"📊 Usage: {usage_info}")
        
        # Check if user has exceeded limits
        if not usage_info['allowed']:
            upgrade_message = "You have reached your search limit."
            if tier == 'anonymous':
                upgrade_message += " Register for 10 free searches per day!"
                upgrade_url = 'https://marketplace.cloudnestle.com/register'
            else:
                upgrade_message += " Upgrade to Pro for unlimited searches!"
                upgrade_url = 'https://marketplace.cloudnestle.com/solutions/61deb2fb-6e5e-4cda-ac5d-ff20202a8788'
            
            return {
                'statusCode': 429,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'error': 'Usage limit exceeded',
                    'message': upgrade_message,
                    'usage': usage_info,
                    'upgrade_url': upgrade_url
                })
            }
        
        # Increment usage count
        increment_usage(user_id, tier)
        
        # Update usage info after increment
        usage_info['searches_used'] = int(usage_info['searches_used']) + 1
        if usage_info['searches_remaining'] != 'unlimited':
            usage_info['searches_remaining'] = max(0, int(usage_info['searches_remaining']) - 1)
            usage_info['upgrade_needed'] = usage_info['searches_remaining'] == 0
        
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
                'usage': usage_info,
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
