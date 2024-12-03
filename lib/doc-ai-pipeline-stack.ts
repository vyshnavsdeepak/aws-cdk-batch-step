import * as cdk from 'aws-cdk-lib';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as efs from 'aws-cdk-lib/aws-efs';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as batch from 'aws-cdk-lib/aws-batch';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as stepfunctions from 'aws-cdk-lib/aws-stepfunctions';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import { Construct } from 'constructs';

export class DocAiPipelineStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, {
      ...props,
      env: { region: 'us-east-1' }, // Explicitly set region as per requirements
    });

    // Create S3 bucket with removal policy retain
    const sourceBucket = new s3.Bucket(this, 'SourceBucket', {
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      versioned: true,
      encryption: s3.BucketEncryption.S3_MANAGED,
    });

    // Create VPC for compute resources
    const vpc = new ec2.Vpc(this, 'DocAiVPC', {
      maxAzs: 2,
      natGateways: 1,
    });

    // Create EFS file system
    const fileSystem = new efs.FileSystem(this, 'DocAiEFS', {
      vpc,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      lifecyclePolicy: efs.LifecyclePolicy.AFTER_14_DAYS,
      performanceMode: efs.PerformanceMode.GENERAL_PURPOSE,
      throughputMode: efs.ThroughputMode.BURSTING,
      vpcSubnets: {
        subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
      },
    });

    // Create security group for EFS access
    const efsSecurityGroup = new ec2.SecurityGroup(this, 'EfsSecurityGroup', {
      vpc,
      description: 'Security group for EFS access',
      allowAllOutbound: true,
    });

    // Allow inbound NFS traffic from within the VPC
    efsSecurityGroup.addIngressRule(
      ec2.Peer.ipv4(vpc.vpcCidrBlock),
      ec2.Port.tcp(2049),
      'Allow NFS traffic from within VPC'
    );

    // Add security group to EFS
    fileSystem.connections.addSecurityGroup(efsSecurityGroup);

    // Create log group for application logs
    const logGroup = new logs.LogGroup(this, 'DocAiLogGroup', {
      retention: logs.RetentionDays.ONE_MONTH,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });
  }
}
