#!/usr/bin/env python3
"""
Resumable FAISS index builder with rate limit handling and checkpoints.
"""
import boto3
import json
import numpy as np
import faiss
import time
import argparse
from pathlib import Path

def load_checkpoint(org):
    """Load checkpoint from S3"""
    s3 = boto3.client('s3')
    bucket = f'faiss-rag-agent-vectors-039920874011'
    key = f'{org}/checkpoint.json'
    
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
        checkpoint = json.loads(response['Body'].read())
        print(f"📂 Loaded checkpoint: {checkpoint['processed']}/{checkpoint['total']} embeddings")
        return checkpoint
    except:
        return {'processed': 0, 'embeddings': [], 'metadata': []}

def save_checkpoint(org, checkpoint):
    """Save checkpoint to S3"""
    s3 = boto3.client('s3')
    bucket = f'faiss-rag-agent-vectors-039920874011'
    key = f'{org}/checkpoint.json'
    
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(checkpoint),
        ContentType='application/json'
    )

def generate_embedding(text, bedrock, retries=5):
    """Generate embedding with retry logic"""
    for attempt in range(retries):
        try:
            response = bedrock.invoke_model(
                modelId='amazon.titan-embed-text-v2:0',
                body=json.dumps({
                    "inputText": text[:8000],
                    "dimensions": 1024,
                    "normalize": True
                })
            )
            result = json.loads(response['body'].read())
            return result['embedding']
        except Exception as e:
            if 'ThrottlingException' in str(e) or 'Too many requests' in str(e):
                wait_time = (2 ** attempt) * 5  # Exponential backoff: 5, 10, 20, 40, 80 seconds
                print(f"⚠️  Rate limited. Waiting {wait_time}s (attempt {attempt+1}/{retries})...")
                time.sleep(wait_time)
            else:
                print(f"❌ Error: {e}")
                return None
    
    print(f"❌ Failed after {retries} retries")
    return None

def build_faiss_index_resumable(org, batch_size=10):
    """Build FAISS index with resumable checkpoints"""
    
    # Load documents
    data_file = Path(f'/persistent/home/ubuntu/workspace/faiss-rag-agent/data/repos_{org}.json')
    with open(data_file) as f:
        documents = json.load(f)
    
    total = len(documents)
    print(f"📊 Total documents: {total}")
    
    # Load checkpoint
    checkpoint = load_checkpoint(org)
    start_idx = checkpoint.get('processed', 0)
    embeddings = checkpoint.get('embeddings', [])
    metadata = checkpoint.get('metadata', [])
    
    if start_idx > 0:
        print(f"🔄 Resuming from document {start_idx}/{total}")
    
    # Initialize Bedrock
    bedrock = boto3.client('bedrock-runtime', region_name='us-west-2')
    
    # Process batch
    end_idx = min(start_idx + batch_size, total)
    print(f"\n🔨 Processing batch: {start_idx} to {end_idx}")
    
    for idx in range(start_idx, end_idx):
        doc = documents[idx]
        text = doc['text']
        
        print(f"  [{idx+1}/{total}] {doc['metadata']['repository'][:50]}...")
        
        embedding = generate_embedding(text, bedrock)
        
        if embedding:
            embeddings.append(embedding)
            metadata.append(doc['metadata'])
        else:
            # Use zero vector as fallback
            embeddings.append([0.0] * 1024)
            metadata.append(doc['metadata'])
        
        time.sleep(0.2)  # Rate limiting
    
    # Save checkpoint
    checkpoint = {
        'processed': end_idx,
        'total': total,
        'embeddings': embeddings,
        'metadata': metadata
    }
    save_checkpoint(org, checkpoint)
    print(f"\n💾 Checkpoint saved: {end_idx}/{total} ({int(end_idx/total*100)}%)")
    
    # If complete, build final index
    if end_idx >= total:
        print(f"\n✅ All embeddings generated! Building final FAISS index...")
        
        # Convert to numpy array
        embeddings_array = np.array(embeddings, dtype='float32')
        
        # Build FAISS index
        dimension = 1024
        index = faiss.IndexFlatL2(dimension)
        index.add(embeddings_array)
        
        # Save to S3
        s3 = boto3.client('s3')
        bucket = 'faiss-rag-agent-vectors-039920874011'
        
        # Save index
        index_path = f'/tmp/faiss_index_{org}.bin'
        faiss.write_index(index, index_path)
        with open(index_path, 'rb') as f:
            s3.put_object(Bucket=bucket, Key=f'{org}/faiss_index.bin', Body=f)
        
        # Save metadata
        metadata_path = f'/tmp/metadata_{org}.json'
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f)
        with open(metadata_path, 'rb') as f:
            s3.put_object(Bucket=bucket, Key=f'{org}/metadata.json', Body=f)
        
        print(f"✅ FAISS index uploaded to s3://{bucket}/{org}/")
        print(f"   - faiss_index.bin ({len(embeddings)} vectors)")
        print(f"   - metadata.json")
        
        # Clean up checkpoint
        s3.delete_object(Bucket=bucket, Key=f'{org}/checkpoint.json')
        print(f"🧹 Checkpoint cleaned up")
        
        return True
    
    return False

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('org', help='Organization name (awslabs or aws-samples)')
    parser.add_argument('--batch-size', type=int, default=10, help='Batch size')
    args = parser.parse_args()
    
    completed = build_faiss_index_resumable(args.org, args.batch_size)
    
    if completed:
        print(f"\n🎉 FAISS index build complete for {args.org}!")
    else:
        print(f"\n⏸️  Batch complete. Run again to continue.")
