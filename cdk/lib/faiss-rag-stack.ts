import * as cdk from 'aws-cdk-lib';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as s3deploy from 'aws-cdk-lib/aws-s3-deployment';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as route53 from 'aws-cdk-lib/aws-route53';
import * as targets from 'aws-cdk-lib/aws-route53-targets';
import * as acm from 'aws-cdk-lib/aws-certificatemanager';
import { Construct } from 'constructs';

export class FaissRagStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Use existing S3 bucket for FAISS index
    const indexBucket = s3.Bucket.fromBucketName(
      this, 
      'FaissIndexBucket', 
      `faiss-rag-agent-vectors-${this.account}`
    );

    // Lambda function using container image for FAISS
    const queryFunction = new lambda.DockerImageFunction(this, 'QueryFunction', {
      code: lambda.DockerImageCode.fromImageAsset('../lambda'),
      timeout: cdk.Duration.seconds(30),
      memorySize: 1024,
      environment: {
        INDEX_BUCKET: indexBucket.bucketName,
        INDEX_KEY: 'faiss_index.bin',
        METADATA_KEY: 'metadata.json',
        MODEL_ID: 'us.amazon.nova-pro-v1:0',
        EMBEDDING_MODEL_ID: 'amazon.titan-embed-text-v2:0',
      },
    });

    // Grant permissions
    indexBucket.grantRead(queryFunction);
    
    queryFunction.addToRolePolicy(new iam.PolicyStatement({
      actions: ['bedrock:InvokeModel'],
      resources: [
        `arn:aws:bedrock:*::foundation-model/*`,
        `arn:aws:bedrock:*:*:inference-profile/*`,
      ],
    }));

    // API Gateway
    const api = new apigateway.RestApi(this, 'FaissRagApi', {
      restApiName: 'FAISS RAG Agent API',
      description: 'API for FAISS-based RAG agent',
      defaultCorsPreflightOptions: {
        allowOrigins: apigateway.Cors.ALL_ORIGINS,
        allowMethods: apigateway.Cors.ALL_METHODS,
      },
    });

    const queryIntegration = new apigateway.LambdaIntegration(queryFunction);
    api.root.addResource('query').addMethod('POST', queryIntegration);

    // Outputs
    new cdk.CfnOutput(this, 'ApiUrl', {
      value: api.url,
      description: 'API Gateway URL',
    });

    new cdk.CfnOutput(this, 'IndexBucket', {
      value: indexBucket.bucketName,
      description: 'S3 bucket for FAISS index',
    });

    new cdk.CfnOutput(this, 'LambdaFunction', {
      value: queryFunction.functionName,
      description: 'Lambda function name',
    });

    // S3 bucket for UI
    const uiBucket = new s3.Bucket(this, 'UIBucket', {
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    // CloudFront Origin Access Control
    const oac = new cloudfront.CfnOriginAccessControl(this, 'OAC', {
      originAccessControlConfig: {
        name: 'FAISS-RAG-UI-OAC',
        originAccessControlOriginType: 's3',
        signingBehavior: 'always',
        signingProtocol: 'sigv4',
      },
    });

    // CloudFront function for URL rewriting
    const urlRewriteFunction = new cloudfront.Function(this, 'UrlRewriteFunction', {
      code: cloudfront.FunctionCode.fromInline(`
        function handler(event) {
          var request = event.request;
          var uri = request.uri;
          
          // Handle /search route
          if (uri === '/search' || uri === '/search/') {
            request.uri = '/search.html';
          }
          // Handle root route
          else if (uri === '/' || uri === '') {
            request.uri = '/index.html';
          }
          // Handle other routes without extension
          else if (!uri.includes('.') && !uri.endsWith('/')) {
            request.uri = uri + '.html';
          }
          
          return request;
        }
      `),
    });

    // CloudFront distribution
    const distribution = new cloudfront.Distribution(this, 'UIDistribution', {
      defaultBehavior: {
        origin: new origins.S3Origin(uiBucket),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        functionAssociations: [{
          function: urlRewriteFunction,
          eventType: cloudfront.FunctionEventType.VIEWER_REQUEST,
        }],
      },
      defaultRootObject: 'index.html',
      errorResponses: [{
        httpStatus: 404,
        responseHttpStatus: 200,
        responsePagePath: '/index.html',
      }],
    });

    // Grant CloudFront access to S3
    uiBucket.addToResourcePolicy(new iam.PolicyStatement({
      actions: ['s3:GetObject'],
      resources: [uiBucket.arnForObjects('*')],
      principals: [new iam.ServicePrincipal('cloudfront.amazonaws.com')],
      conditions: {
        StringEquals: {
          'AWS:SourceArn': `arn:aws:cloudfront::${this.account}:distribution/${distribution.distributionId}`,
        },
      },
    }));

    // Deploy UI files
    new s3deploy.BucketDeployment(this, 'DeployUI', {
      sources: [s3deploy.Source.asset('../ui')],
      destinationBucket: uiBucket,
      distribution,
      distributionPaths: ['/*'],
    });

    new cdk.CfnOutput(this, 'UIUrl', {
      value: `https://${distribution.distributionDomainName}`,
      description: 'Chat UI URL',
    });
  }
}
