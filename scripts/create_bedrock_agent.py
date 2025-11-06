#!/usr/bin/env python3
"""
Create Bedrock Agent with Action Group for FAISS Lambda.
"""
import boto3
import json
import time

bedrock_agent = boto3.client('bedrock-agent', region_name='us-east-1')
iam = boto3.client('iam')
lambda_client = boto3.client('lambda', region_name='us-east-1')

def create_agent_role(lambda_arn):
    """Create IAM role for Bedrock Agent."""
    role_name = 'BedrockAgentFAISSRole'
    
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "bedrock.amazonaws.com"},
            "Action": "sts:AssumeRole"
        }]
    }
    
    try:
        role = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description='Role for Bedrock Agent to invoke FAISS Lambda'
        )
        role_arn = role['Role']['Arn']
        print(f"✅ Created role: {role_arn}")
    except iam.exceptions.EntityAlreadyExistsException:
        role = iam.get_role(RoleName=role_name)
        role_arn = role['Role']['Arn']
        print(f"✅ Using existing role: {role_arn}")
    
    # Attach policies
    iam.attach_role_policy(
        RoleName=role_name,
        PolicyArn='arn:aws:iam::aws:policy/AmazonBedrockFullAccess'
    )
    
    # Add Lambda invoke permission
    policy_doc = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": "lambda:InvokeFunction",
            "Resource": lambda_arn
        }]
    }
    
    try:
        iam.put_role_policy(
            RoleName=role_name,
            PolicyName='LambdaInvokePolicy',
            PolicyDocument=json.dumps(policy_doc)
        )
    except:
        pass
    
    time.sleep(10)  # Wait for IAM propagation
    return role_arn

def create_agent(role_arn, lambda_arn):
    """Create Bedrock Agent."""
    
    agent_name = 'aws-repo-search-agent'
    
    # Check if agent exists
    try:
        agents = bedrock_agent.list_agents()
        for agent in agents.get('agentSummaries', []):
            if agent['agentName'] == agent_name:
                agent_id = agent['agentId']
                print(f"✅ Agent already exists: {agent_id}")
                
                # Get alias
                aliases = bedrock_agent.list_agent_aliases(agentId=agent_id)
                alias_id = aliases['agentAliasSummaries'][0]['agentAliasId'] if aliases['agentAliasSummaries'] else None
                
                if alias_id:
                    print(f"✅ Using existing alias: {alias_id}")
                    return agent_id, alias_id
    except:
        pass
    
    response = bedrock_agent.create_agent(
        agentName=agent_name,
        agentResourceRoleArn=role_arn,
        foundationModel='us.amazon.nova-pro-v1:0',
        instruction='You are an AWS repository search assistant. Help users find relevant AWS sample repositories. When users ask about repositories, use the search_repositories action.',
        idleSessionTTLInSeconds=600
    )
    
    agent_id = response['agent']['agentId']
    print(f"✅ Created agent: {agent_id}")
    
    # Wait for agent to be ready
    print("⏳ Waiting for agent to be ready...")
    for i in range(30):
        agent_status = bedrock_agent.get_agent(agentId=agent_id)
        if agent_status['agent']['agentStatus'] in ['NOT_PREPARED', 'PREPARED']:
            break
        time.sleep(2)
    print(f"✅ Agent ready")
    
    # Create Action Group
    api_schema = {
        "openapi": "3.0.0",
        "info": {"title": "Repository Search", "version": "1.0.0"},
        "paths": {
            "/search": {
                "post": {
                    "summary": "Search repositories",
                    "operationId": "searchRepositories",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "query": {"type": "string", "description": "Search query"}
                                    },
                                    "required": ["query"]
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "Success"}}
                }
            }
        }
    }
    
    bedrock_agent.create_agent_action_group(
        agentId=agent_id,
        agentVersion='DRAFT',
        actionGroupName='search-repositories',
        actionGroupExecutor={'lambda': lambda_arn},
        apiSchema={'payload': json.dumps(api_schema)}
    )
    
    print(f"✅ Created action group")
    
    # Prepare agent
    bedrock_agent.prepare_agent(agentId=agent_id)
    print(f"✅ Preparing agent...")
    time.sleep(5)
    
    # Create alias
    alias_response = bedrock_agent.create_agent_alias(
        agentId=agent_id,
        agentAliasName='prod'
    )
    
    alias_id = alias_response['agentAlias']['agentAliasId']
    print(f"✅ Created alias: {alias_id}")
    
    return agent_id, alias_id

if __name__ == '__main__':
    # Get Lambda ARN from CloudFormation
    cfn = boto3.client('cloudformation', region_name='us-east-1')
    stack = cfn.describe_stacks(StackName='FaissRagStack')['Stacks'][0]
    
    lambda_name = None
    for output in stack['Outputs']:
        if output['OutputKey'] == 'LambdaFunction':
            lambda_name = output['OutputValue']
            break
    
    lambda_arn = lambda_client.get_function(FunctionName=lambda_name)['Configuration']['FunctionArn']
    print(f"📦 Lambda ARN: {lambda_arn}")
    
    # Create role
    role_arn = create_agent_role(lambda_arn)
    
    # Create agent
    agent_id, alias_id = create_agent(role_arn, lambda_arn)
    
    print(f"\n🎉 SUCCESS!")
    print(f"Agent ID: {agent_id}")
    print(f"Alias ID: {alias_id}")
    print(f"\nTest in Bedrock console:")
    print(f"https://console.aws.amazon.com/bedrock/home?region=us-east-1#/agents/{agent_id}")
