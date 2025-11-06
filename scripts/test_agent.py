#!/usr/bin/env python3
"""Test Bedrock Agent."""
import boto3
import json
import uuid

agent_runtime = boto3.client('bedrock-agent-runtime', region_name='us-east-1')

agent_id = 'XLZZZYQ9LA'
alias_id = 'TSTALIASID'
session_id = str(uuid.uuid4())

query = "Show me serverless Lambda examples with DynamoDB"

print(f"🔍 Query: {query}\n")

response = agent_runtime.invoke_agent(
    agentId=agent_id,
    agentAliasId=alias_id,
    sessionId=session_id,
    inputText=query
)

# Stream response
completion = ""
for event in response['completion']:
    if 'chunk' in event:
        chunk = event['chunk']
        if 'bytes' in chunk:
            completion += chunk['bytes'].decode('utf-8')

print(f"💬 Response:\n{completion}")
