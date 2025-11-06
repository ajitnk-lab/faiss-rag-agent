#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { FaissRagStack } from '../lib/faiss-rag-stack';

const app = new cdk.App();
const stack = new FaissRagStack(app, 'FaissRagStack', {
  env: { 
    account: process.env.CDK_DEFAULT_ACCOUNT, 
    region: process.env.CDK_DEFAULT_REGION || 'us-west-2'
  },
});

// Add tags to all resources
cdk.Tags.of(stack).add('Name', 'https://awssolutionfinder.solutions.cloudnestle.com');
cdk.Tags.of(stack).add('Application', 'FAISS-RAG-Agent');
cdk.Tags.of(stack).add('ManagedBy', 'CDK');
