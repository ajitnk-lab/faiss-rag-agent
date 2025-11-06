#!/usr/bin/env python3
"""Generate architecture diagram for FAISS RAG Agent."""
from diagrams import Diagram, Cluster, Edge
from diagrams.aws.compute import Lambda
from diagrams.aws.storage import S3
from diagrams.aws.network import CloudFront, APIGateway
from diagrams.aws.ml import Bedrock
from diagrams.onprem.client import Users

with Diagram("FAISS RAG Agent Architecture", filename="architecture", direction="LR", show=False):
    users = Users("Users")
    
    with Cluster("Frontend"):
        ui = CloudFront("CloudFront\nChat UI")
        ui_bucket = S3("S3\nStatic Site")
        ui >> ui_bucket
    
    with Cluster("API Layer"):
        api = APIGateway("API Gateway\n/query")
    
    with Cluster("Backend"):
        lambda_fn = Lambda("Lambda\nDocker Container\n(FAISS + Python)")
        
        with Cluster("Data"):
            index_bucket = S3("S3\nFAISS Index\n(3.6 MB)")
        
        with Cluster("AI Models"):
            nova = Bedrock("Nova Pro\nLLM")
            titan = Bedrock("Titan v2\nEmbeddings")
    
    # Flow
    users >> Edge(label="HTTPS") >> ui
    users >> Edge(label="Query") >> api
    api >> Edge(label="Invoke") >> lambda_fn
    lambda_fn >> Edge(label="Load Index\n(cold start)") >> index_bucket
    lambda_fn >> Edge(label="Generate\nEmbedding") >> titan
    lambda_fn >> Edge(label="Generate\nResponse") >> nova
    lambda_fn >> Edge(label="Results") >> api
    api >> Edge(label="JSON") >> users

print("✅ Architecture diagram generated: architecture.png")
