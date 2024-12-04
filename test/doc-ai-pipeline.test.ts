import * as cdk from 'aws-cdk-lib';
import { Template, Match } from 'aws-cdk-lib/assertions';
import * as DocAiPipeline from '../lib/doc-ai-pipeline-stack';

describe('DocAiPipeline Stack', () => {
  let app: cdk.App;
  let stack: DocAiPipeline.DocAiPipelineStack;
  let template: Template;

  beforeEach(() => {
    app = new cdk.App();
    stack = new DocAiPipeline.DocAiPipelineStack(app, 'TestStack');
    template = Template.fromStack(stack);
  });

  test('S3 Bucket Created', () => {
    template.hasResourceProperties('AWS::S3::Bucket', {
      VersioningConfiguration: {
        Status: 'Enabled'
      }
    });
  });

  test('VPC Created with Correct Subnet Configuration', () => {
    // Verify VPC exists
    template.resourceCountIs('AWS::EC2::VPC', 1);
    template.hasResourceProperties('AWS::EC2::VPC', {
      EnableDnsHostnames: true,
      EnableDnsSupport: true,
    });

    // Verify subnet configurations
    template.resourceCountIs('AWS::EC2::Subnet', 6); // 2 AZs * 3 subnet types = 6 subnets
    
    // Verify we have public subnets
    template.hasResourceProperties('AWS::EC2::Subnet', Match.objectLike({
      MapPublicIpOnLaunch: true,
    }));

    // Verify NAT Gateway
    template.resourceCountIs('AWS::EC2::NatGateway', 1);

    // Verify route tables
    template.hasResourceProperties('AWS::EC2::RouteTable', Match.objectLike({
      VpcId: Match.anyValue()
    }));
  });

  test('EFS FileSystem Created', () => {
    template.resourceCountIs('AWS::EFS::FileSystem', 1);
    template.hasResourceProperties('AWS::EFS::FileSystem', {
      LifecyclePolicies: [
        {
          TransitionToIA: 'AFTER_14_DAYS'
        }
      ]
    });
  });

  test('Step Function State Machine Created', () => {
    template.resourceCountIs('AWS::StepFunctions::StateMachine', 1);
  });

  test('API Gateway Created', () => {
    template.resourceCountIs('AWS::ApiGateway::RestApi', 1);
    template.hasResourceProperties('AWS::ApiGateway::Method', {
      HttpMethod: 'POST',
      AuthorizationType: 'NONE'
    });
  });

  test('Batch Compute Environment Created', () => {
    template.hasResourceProperties('AWS::Batch::ComputeEnvironment', {
      Type: 'MANAGED',
      ComputeResources: {
        Type: 'EC2'
      }
    });
  });

  test('IAM Roles Created', () => {
    template.hasResourceProperties('AWS::IAM::Role', {
      AssumeRolePolicyDocument: {
        Statement: [{
          Action: 'sts:AssumeRole',
          Effect: 'Allow',
          Principal: {
            Service: 'batch.amazonaws.com'
          }
        }]
      }
    });
  });
});
