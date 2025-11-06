#!/usr/bin/env python3
"""
Generate embeddings using Bedrock and build FAISS index.
"""
import boto3
import json
import numpy as np
import faiss
import sys
import time

def generate_embeddings(texts, model_id='amazon.titan-embed-text-v2:0', region='us-west-2'):
    """Generate embeddings using Bedrock Titan."""
    bedrock = boto3.client('bedrock-runtime', region_name=region)
    embeddings = []
    
    print(f"🔄 Generating embeddings for {len(texts)} documents...")
    
    for idx, text in enumerate(texts):
        try:
            response = bedrock.invoke_model(
                modelId=model_id,
                body=json.dumps({
                    "inputText": text[:8000],  # Titan limit
                    "dimensions": 1024,
                    "normalize": True
                })
            )
            
            result = json.loads(response['body'].read())
            embedding = result['embedding']
            embeddings.append(embedding)
            
            if (idx + 1) % 10 == 0:
                print(f"  ✓ Processed {idx + 1}/{len(texts)} documents")
            
            time.sleep(0.1)  # Rate limiting
            
        except Exception as e:
            print(f"  ⚠️  Error on document {idx}: {e}")
            embeddings.append([0.0] * 1024)  # Fallback
    
    return np.array(embeddings, dtype='float32')

def build_faiss_index(embeddings):
    """Build FAISS index from embeddings."""
    dimension = embeddings.shape[1]
    print(f"🔨 Building FAISS index (dimension={dimension})...")
    
    # Use IndexFlatL2 for exact search (good for <1M vectors)
    index = faiss.IndexFlatL2(dimension)
    index.add(embeddings)
    
    print(f"✅ Index built with {index.ntotal} vectors")
    return index

def main(json_file, output_index, output_metadata):
    """Main pipeline: JSON → Embeddings → FAISS Index."""
    
    # Load documents
    print(f"📖 Loading documents from {json_file}")
    with open(json_file, 'r') as f:
        documents = json.load(f)
    
    print(f"📊 Loaded {len(documents)} documents")
    
    # Extract texts and metadata
    texts = [doc['text'] for doc in documents]
    metadata = [doc['metadata'] for doc in documents]
    
    # Generate embeddings
    embeddings = generate_embeddings(texts)
    
    # Build FAISS index
    index = build_faiss_index(embeddings)
    
    # Save index
    print(f"💾 Saving FAISS index to {output_index}")
    faiss.write_index(index, output_index)
    
    # Save metadata
    print(f"💾 Saving metadata to {output_metadata}")
    with open(output_metadata, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    # Verify
    index_size_mb = faiss.read_index(output_index).ntotal * 1024 * 4 / (1024 * 1024)
    print(f"\n✅ SUCCESS!")
    print(f"   Index size: ~{index_size_mb:.2f} MB")
    print(f"   Vectors: {index.ntotal}")
    print(f"   Dimension: {embeddings.shape[1]}")

if __name__ == '__main__':
    json_file = '/persistent/home/ubuntu/workspace/faiss-rag-agent/data/repos_mvp.json'
    output_index = '/persistent/home/ubuntu/workspace/faiss-rag-agent/data/faiss_index.bin'
    output_metadata = '/persistent/home/ubuntu/workspace/faiss-rag-agent/data/metadata.json'
    
    main(json_file, output_index, output_metadata)
