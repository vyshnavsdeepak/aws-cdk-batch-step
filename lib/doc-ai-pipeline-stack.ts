import * as cdk from 'aws-cdk-lib';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as efs from 'aws-cdk-lib/aws-efs';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as batch from 'aws-cdk-lib/aws-batch';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as stepfunctions from 'aws-cdk-lib/aws-stepfunctions';
import * as tasks from 'aws-cdk-lib/aws-stepfunctions-tasks';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import { Construct } from 'constructs';

export interface DocAiPipelineStackProps extends cdk.StackProps {
  maxGpuVcpus?: number;
  maxCpuVcpus?: number;
}

export class DocAiPipelineStack extends cdk.Stack {
  public readonly sourceBucket: s3.IBucket;
  public readonly fileSystem: efs.IFileSystem;
  public readonly vpc: ec2.IVpc;
  public readonly api: apigateway.RestApi;
  public readonly stateMachine: stepfunctions.StateMachine;

  constructor(scope: Construct, id: string, props: DocAiPipelineStackProps = {}) {
    super(scope, id, {
      ...props,
      env: { region: 'us-east-1' },
    });

    // Create S3 bucket with best practices
    this.sourceBucket = new s3.Bucket(this, 'SourceBucket', {
      bucketName: `${id}-source-${this.region}`.toLowerCase(),
      removalPolicy: cdk.RemovalPolicy.DESTROY, // while testing, otherwise use cdk.RemovalPolicy.RETAIN
      autoDeleteObjects: true, // while testing
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      lifecycleRules: [
        {
          transitions: [
            {
              storageClass: s3.StorageClass.INTELLIGENT_TIERING,
              transitionAfter: cdk.Duration.days(30),
            },
          ],
        },
      ],
    });

    // Create VPC with public, private, and isolated subnets
    this.vpc = new ec2.Vpc(this, 'DocAiVPC', {
      maxAzs: 2,
      natGateways: 1,
      subnetConfiguration: [
        {
          name: 'Public',
          subnetType: ec2.SubnetType.PUBLIC,
          cidrMask: 24,
        },
        {
          name: 'Private',
          subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
          cidrMask: 24,
        },
      ],
    });

    // Create EFS file system with access point
    this.fileSystem = new efs.FileSystem(this, 'DocAiEFS', {
      vpc: this.vpc,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      lifecyclePolicy: efs.LifecyclePolicy.AFTER_14_DAYS,
      performanceMode: efs.PerformanceMode.GENERAL_PURPOSE,
      throughputMode: efs.ThroughputMode.BURSTING,
      vpcSubnets: {
        subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
      },
      securityGroup: new ec2.SecurityGroup(this, 'EfsSecurityGroup', {
        vpc: this.vpc,
        description: 'Security group for EFS access',
        allowAllOutbound: true,
      }),
    });

    const volume = batch.EcsVolume.efs({
      name: 'sharedEfs',
      fileSystem: this.fileSystem,
      containerPath: '/efs',
      useJobRole: true,
      enableTransitEncryption: true,
    })

    // Create EFS access point for each processing stage
    const processingAccessPoint = new efs.AccessPoint(this, 'ProcessingAccessPoint', {
      fileSystem: this.fileSystem,
      path: '/processing',
      createAcl: {
        ownerGid: '1000',
        ownerUid: '1000',
        permissions: '755',
      },
      posixUser: {
        gid: '1000',
        uid: '1000',
      },
    });

    // Create Batch environment for CPU workloads
    const cpuComputeEnv = new batch.ManagedEc2EcsComputeEnvironment(this, 'CpuComputeEnv', {
      vpc: this.vpc,
      vpcSubnets: {
        subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
      },
      maxvCpus: props.maxCpuVcpus ?? 2,
      instanceTypes: [
        // ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.SMALL)
        ec2.InstanceType.of(ec2.InstanceClass.C5, ec2.InstanceSize.LARGE),
        ec2.InstanceType.of(ec2.InstanceClass.C6A, ec2.InstanceSize.LARGE)
      ],
      computeEnvironmentName: 'CpuEnv',
      spot: true,
    });

    // Create Batch environment for GPU workloads
    const gpuComputeEnv = new batch.ManagedEc2EcsComputeEnvironment(this, 'GpuComputeEnv', {
      vpc: this.vpc,
      vpcSubnets: {
        subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
      },
      maxvCpus: props.maxGpuVcpus ?? 4,
      instanceTypes: [
        // ec2.InstanceType.of(ec2.InstanceClass.G4DN, ec2.InstanceSize.XLARGE)
        ec2.InstanceType.of(ec2.InstanceClass.G4DN, ec2.InstanceSize.XLARGE),
        ec2.InstanceType.of(ec2.InstanceClass.G5, ec2.InstanceSize.XLARGE)
      ],
      computeEnvironmentName: 'GpuEnv',
      spot: true,
      allocationStrategy: batch.AllocationStrategy.SPOT_CAPACITY_OPTIMIZED,
    });

    // Create job queues with proper naming and priority
    const cpuQueue = new batch.JobQueue(this, 'CpuJobQueue', {
      jobQueueName: 'CpuQueue',
      priority: 1,
      enabled: true,
      computeEnvironments: [
        {
          computeEnvironment: cpuComputeEnv,
          order: 1,
        },
      ],
    });

    const gpuQueue = new batch.JobQueue(this, 'GpuJobQueue', {
      jobQueueName: 'GpuQueue',
      priority: 1,
      enabled: true,
      computeEnvironments: [
        {
          computeEnvironment: gpuComputeEnv,
          order: 1,
        },
      ],
    });

    // Create log group
    const logGroup = new logs.LogGroup(this, 'DocAiLogGroup', {
      retention: logs.RetentionDays.ONE_MONTH,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    const preProcessingJobDefinition = new batch.EcsJobDefinition(this, 'PreprocessJobDef', {
      container: new batch.EcsEc2ContainerDefinition(this, 'PreprocessContainerDef', {
        image: ecs.ContainerImage.fromAsset('docker/preprocess'),
        cpu: 1,
        memory: cdk.Size.mebibytes(1024),
        jobRole: new iam.Role(this, 'PreprocessJobRole', {
          assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
          managedPolicies: [
            iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AmazonECSTaskExecutionRolePolicy'),
          ],
          inlinePolicies: {
            's3Access': new iam.PolicyDocument({
              statements: [
                new iam.PolicyStatement({
                  effect: iam.Effect.ALLOW,
                  actions: ['s3:GetObject', 's3:ListBucket'],
                  resources: [
                    this.sourceBucket.bucketArn,
                    `${this.sourceBucket.bucketArn}/*`
                  ],
                }),
              ],
            }),
            'efsAccess': new iam.PolicyDocument({
              statements: [
                new iam.PolicyStatement({
                  effect: iam.Effect.ALLOW,
                  actions: [
                    'elasticfilesystem:ClientMount',
                    'elasticfilesystem:ClientWrite',
                  ],
                  resources: [this.fileSystem.fileSystemArn],
                }),
              ],
            }),
          },
        }),
        environment: {
          SOURCE_BUCKET: this.sourceBucket.bucketName,
          INPUT_DIRECTORY: 'sfn.JsonPath.stringAt($.directory)',
          LOG_GROUP: logGroup.logGroupName,
        },
        volumes: [volume],
        logging: ecs.LogDriver.awsLogs({
          streamPrefix: 'preprocess',
          logGroup: logGroup,
        }),
      }),
      retryAttempts: 3,
      timeout: cdk.Duration.hours(2),
    })

    // Create Step Functions workflow with proper error handling
    const submitPreprocessJob = new tasks.BatchSubmitJob(this, 'SubmitPreprocessJob', {
      jobName: 'preprocess',
      jobQueueArn: cpuQueue.jobQueueArn,
      jobDefinitionArn: preProcessingJobDefinition.jobDefinitionArn,
      integrationPattern: stepfunctions.IntegrationPattern.RUN_JOB,
      resultPath: '$.preprocessOutput',
      resultSelector: {
        'jobId.$': '$.JobId',
        'status.$': '$.Status',
        'exitCode.$': '$.Container.ExitCode',
      },
    }).addRetry({
      maxAttempts: 3,
      backoffRate: 2,
      interval: cdk.Duration.seconds(30),
      errors: ['States.TaskFailed'],
    }).addCatch(new stepfunctions.Pass(this, 'PreprocessFailure', {
      parameters: {
        'error.$': '$.error',
        'cause.$': '$.cause',
      },
    }), {
      resultPath: '$.error',
    });

    const gpuJobDefinition = new batch.EcsJobDefinition(this, 'GpuJobDef', {
      container: new batch.EcsEc2ContainerDefinition(this, 'GpuContainerDef', {
        image: ecs.ContainerImage.fromAsset('docker/gpu'),
        cpu: 4,
        memory: cdk.Size.mebibytes(16384),
        jobRole: new iam.Role(this, 'GpuJobRole', {
          assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
          managedPolicies: [
            iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AmazonECSTaskExecutionRolePolicy'),
          ],
          inlinePolicies: {
            'efsAccess': new iam.PolicyDocument({
              statements: [
                new iam.PolicyStatement({
                  effect: iam.Effect.ALLOW,
                  actions: [
                    'elasticfilesystem:ClientMount',
                    'elasticfilesystem:ClientWrite',
                  ],
                  resources: [this.fileSystem.fileSystemArn],
                }),
              ],
            }),
          },
        }),
        environment: {
          LOG_GROUP: logGroup.logGroupName,
        },
        volumes: [volume],
        logging: ecs.LogDriver.awsLogs({
          streamPrefix: 'gpu',
          logGroup: logGroup,
        }),
      }),
    });

    const submitGpuJob = new tasks.BatchSubmitJob(this, 'SubmitGpuJob', {
      jobName: 'gpu-processing',
      jobQueueArn: gpuQueue.jobQueueArn,
      jobDefinitionArn: gpuJobDefinition.jobDefinitionArn,
      integrationPattern: stepfunctions.IntegrationPattern.RUN_JOB,
      resultPath: '$.gpuOutput',
      resultSelector: {
        'jobId.$': '$.JobId',
        'status.$': '$.Status',
        'exitCode.$': '$.Container.ExitCode',
      },
    }).addRetry({
      maxAttempts: 3,
      backoffRate: 2,
      interval: cdk.Duration.seconds(30),
      errors: ['States.TaskFailed'],
    }).addCatch(new stepfunctions.Pass(this, 'GpuFailure', {
      parameters: {
        'error.$': '$.error',
        'cause.$': '$.cause',
      },
    }), {
      resultPath: '$.error',
    });

    const postProcessJobDef = new batch.EcsJobDefinition(this, 'PostprocessJobDef', {
      container: new batch.EcsEc2ContainerDefinition(this, 'PostprocessContainerDef', {
        image: ecs.ContainerImage.fromAsset('docker/postprocess'),
        memory: cdk.Size.mebibytes(1024),
        cpu: 1,
        jobRole: new iam.Role(this, 'PostprocessJobRole', {
          assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
          managedPolicies: [
            iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AmazonECSTaskExecutionRolePolicy'),
          ],
          inlinePolicies: {
            's3Access': new iam.PolicyDocument({
              statements: [
                new iam.PolicyStatement({
                  effect: iam.Effect.ALLOW,
                  actions: ['s3:PutObject'],
                  resources: [
                    this.sourceBucket.bucketArn,
                    `${this.sourceBucket.bucketArn}/*`
                  ],
                }),
              ],
            }),
            'efsAccess': new iam.PolicyDocument({
              statements: [
                new iam.PolicyStatement({
                  effect: iam.Effect.ALLOW,
                  actions: [
                    'elasticfilesystem:ClientMount',
                    'elasticfilesystem:ClientWrite',
                  ],
                  resources: [this.fileSystem.fileSystemArn],
                }),
              ],
            }),
          },
        }),
        environment: {
          OUTPUT_BUCKET: this.sourceBucket.bucketName,
          OUTPUT_PREFIX: 'sfn.JsonPath.stringAt($.directory)',
          LOG_GROUP: logGroup.logGroupName,
        },
        volumes: [volume],
        logging: ecs.LogDriver.awsLogs({
          streamPrefix: 'postprocess',
          logGroup: logGroup,
        }),
      }),
    });

    const submitPostprocessJob = new tasks.BatchSubmitJob(this, 'SubmitPostprocessJob', {
      jobName: 'postprocess',
      jobQueueArn: cpuQueue.jobQueueArn,
      jobDefinitionArn: postProcessJobDef.jobDefinitionArn,
      integrationPattern: stepfunctions.IntegrationPattern.RUN_JOB,
      resultPath: '$.postprocessOutput',
      resultSelector: {
        'jobId.$': '$.JobId',
        'status.$': '$.Status',
        'exitCode.$': '$.Container.ExitCode',
      },
    }).addRetry({
      maxAttempts: 3,
      backoffRate: 2,
      interval: cdk.Duration.seconds(30),
      errors: ['States.TaskFailed'],
    }).addCatch(new stepfunctions.Pass(this, 'PostprocessFailure', {
      parameters: {
        'error.$': '$.error',
        'cause.$': '$.cause',
      },
    }), {
      resultPath: '$.error',
    });

    // Define workflow
    const definition = submitPreprocessJob
      .next(submitGpuJob)
      .next(submitPostprocessJob);

    this.stateMachine = new stepfunctions.StateMachine(this, 'DocAiWorkflow', {
      definitionBody: stepfunctions.DefinitionBody.fromChainable(definition),
      timeout: cdk.Duration.hours(24),
      tracingEnabled: true,
      stateMachineType: stepfunctions.StateMachineType.STANDARD,
      logs: {
        destination: logGroup,
        level: stepfunctions.LogLevel.ALL,
        includeExecutionData: true,
      },
    });

    // Create API Gateway with proper models and error responses
    this.api = new apigateway.RestApi(this, 'DocAiApi', {
      restApiName: 'Document AI Pipeline API',
      description: 'API for triggering document processing pipeline',
      deployOptions: {
        stageName: 'prod',
        loggingLevel: apigateway.MethodLoggingLevel.INFO,
        dataTraceEnabled: true,
        tracingEnabled: true,
        metricsEnabled: true,
      },
      defaultCorsPreflightOptions: {
        allowOrigins: apigateway.Cors.ALL_ORIGINS,
        allowMethods: apigateway.Cors.ALL_METHODS,
        allowHeaders: ['Content-Type', 'X-Amz-Date', 'Authorization', 'X-Api-Key'],
        maxAge: cdk.Duration.days(1),
      },
    });

    // Create IAM role for API Gateway
    const apiRole = new iam.Role(this, 'ApiRole', {
      assumedBy: new iam.ServicePrincipal('apigateway.amazonaws.com'),
    });

    // Add CloudWatch Logs permissions
    // apiRole.addToPolicy(new iam.PolicyStatement({
    //   effect: iam.Effect.ALLOW,
    //   actions: [
    //     'logs:CreateLogGroup',
    //     'logs:CreateLogStream',
    //     'logs:DescribeLogGroups',
    //     'logs:DescribeLogStreams',
    //     'logs:PutLogEvents',
    //     'logs:GetLogEvents',
    //     'logs:FilterLogEvents'
    //   ],
    //   resources: ['*']  // or scope it to specific log groups if needed
    // }));


    this.stateMachine.grantStartExecution(apiRole);

    // Add API resources and methods
    const processingResource = this.api.root.addResource('process');
    
    const integration = new apigateway.AwsIntegration({
      service: 'states',
      action: 'StartExecution',
      options: {
        credentialsRole: apiRole,
        requestTemplates: {
          'application/json': JSON.stringify({
            stateMachineArn: this.stateMachine.stateMachineArn,
            input: "$util.escapeJavaScript($input.json('$'))"
          })
        },
        integrationResponses: [
          {
            statusCode: '200',
            responseTemplates: {
              'application/json': JSON.stringify({
                executionArn: "$util.parseJson($input.json('$')).executionArn",
                startDate: "$util.parseJson($input.json('$')).startDate"
              })
            }
          }
        ]
      }
    });
    
    processingResource.addMethod('POST', integration, {
      methodResponses: [
        {
          statusCode: '200',
          responseModels: {
            'application/json': new apigateway.Model(this, 'ExecutionResponse', {
              restApi: this.api,
              contentType: 'application/json',
              modelName: 'ExecutionResponse',
              schema: {
                type: apigateway.JsonSchemaType.OBJECT,
                properties: {
                  executionArn: { type: apigateway.JsonSchemaType.STRING },
                  startDate: { type: apigateway.JsonSchemaType.STRING }
                }
              }
            })
          }
        }
      ]
    });

    // Output important resource information
    new cdk.CfnOutput(this, 'ApiEndpoint', {
      value: this.api.url,
      description: 'API Gateway endpoint URL',
    });

    new cdk.CfnOutput(this, 'SourceBucketName', {
      value: this.sourceBucket.bucketName,
      description: 'Name of the source S3 bucket',
    });
  }
}
