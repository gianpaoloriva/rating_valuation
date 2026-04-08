#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Rating & Valuation Suite — AWS ECS Express deploy script
#
# Usage:
#   ./deploy/deploy.sh              # build, push, update ECS Express, wait
#   ./deploy/deploy.sh --no-wait    # push + trigger update, don't poll
#
# Prerequisites:
#   - AWS CLI configured (aws configure) with permissions to ECR + ECS
#   - Docker running (linux/amd64 build)
#
# First-time setup (already done — reference only):
#   # ECR repository
#   aws ecr create-repository --repository-name rating-valuation --region eu-west-1
#
#   # Task execution role (ECR pull + CloudWatch logs)
#   aws iam create-role --role-name ecsTaskExecutionRole \
#     --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ecs-tasks.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
#   aws iam attach-role-policy --role-name ecsTaskExecutionRole \
#     --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
#
#   # Infrastructure role (ALB, autoscaling, security groups)
#   aws iam create-role --role-name ECSExpressInfrastructureRole \
#     --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ecs.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
#   aws iam attach-role-policy --role-name ECSExpressInfrastructureRole \
#     --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSInfrastructureRoleforExpressGatewayServices
#
#   # CloudWatch log group
#   aws logs create-log-group --log-group-name /ecs/rating-valuation --region eu-west-1
#
#   # ECS Express service (one-time creation)
#   aws ecs create-express-gateway-service \
#     --execution-role-arn arn:aws:iam::217267466515:role/ecsTaskExecutionRole \
#     --infrastructure-role-arn arn:aws:iam::217267466515:role/ECSExpressInfrastructureRole \
#     --service-name rating-valuation \
#     --health-check-path /_stcore/health \
#     --primary-container '{"image":"217267466515.dkr.ecr.eu-west-1.amazonaws.com/rating-valuation:latest","containerPort":8501,"awsLogsConfiguration":{"logGroup":"/ecs/rating-valuation","logStreamPrefix":"rating-valuation"}}' \
#     --cpu 1024 --memory 2048 \
#     --scaling-target '{"minTaskCount":1,"maxTaskCount":3,"autoScalingMetric":"AVERAGE_CPU","autoScalingTargetValue":70}' \
#     --region eu-west-1
# -----------------------------------------------------------------------------
set -euo pipefail

AWS_REGION="eu-west-1"
AWS_ACCOUNT="217267466515"
ECR_REPO="rating-valuation"
SERVICE_ARN="arn:aws:ecs:${AWS_REGION}:${AWS_ACCOUNT}:service/default/rating-valuation"
EXECUTION_ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT}:role/ecsTaskExecutionRole"
ECR_URI="${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}"
SERVICE_URL="https://ra-85a099a2598346a489373514c46923a8.ecs.eu-west-1.on.aws"
NO_WAIT="${1:-}"

echo "==> Authenticating to ECR..."
aws ecr get-login-password --region "${AWS_REGION}" | \
  docker login --username AWS --password-stdin "${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com"

echo "==> Building image (linux/amd64)..."
docker build --platform linux/amd64 -t "${ECR_REPO}:latest" .

echo "==> Tagging..."
docker tag "${ECR_REPO}:latest" "${ECR_URI}:latest"

echo "==> Pushing to ECR..."
docker push "${ECR_URI}:latest"
IMAGE_DIGEST=$(docker inspect --format='{{index .RepoDigests 0}}' "${ECR_URI}:latest" | cut -d@ -f2)
echo "    digest: ${IMAGE_DIGEST}"

echo "==> Triggering ECS Express service update..."
aws ecs update-express-gateway-service \
  --service-arn "${SERVICE_ARN}" \
  --execution-role-arn "${EXECUTION_ROLE_ARN}" \
  --primary-container "{
    \"image\": \"${ECR_URI}:latest\",
    \"containerPort\": 8501,
    \"awsLogsConfiguration\": {
      \"logGroup\": \"/ecs/rating-valuation\",
      \"logStreamPrefix\": \"rating-valuation\"
    }
  }" \
  --region "${AWS_REGION}" \
  --query "service.status.statusCode" --output text

if [[ "${NO_WAIT}" == "--no-wait" ]]; then
  echo "==> --no-wait: update triggered, skipping poll."
  echo "    URL: ${SERVICE_URL}"
  exit 0
fi

echo "==> Waiting for new task to be RUNNING (polls every 20s, max 10 min)..."
for i in $(seq 1 30); do
  TASK_ARN=$(aws ecs list-tasks \
    --cluster default \
    --service-name rating-valuation \
    --region "${AWS_REGION}" \
    --desired-status RUNNING \
    --query "taskArns[0]" --output text 2>/dev/null)

  if [[ "${TASK_ARN}" == "None" || -z "${TASK_ARN}" ]]; then
    echo "    [${i}/30] waiting for task to start..."
    sleep 20
    continue
  fi

  TASK_STATUS=$(aws ecs describe-tasks \
    --cluster default \
    --tasks "${TASK_ARN}" \
    --region "${AWS_REGION}" \
    --query "tasks[0].lastStatus" --output text 2>/dev/null)

  echo "    [${i}/30] task=${TASK_STATUS}"

  if [[ "${TASK_STATUS}" == "RUNNING" ]]; then
    echo ""
    echo "==> Deploy completed."
    echo "    URL: ${SERVICE_URL}"
    exit 0
  fi

  if [[ "${TASK_STATUS}" == "STOPPED" || "${TASK_STATUS}" == "DEPROVISIONING" ]]; then
    STOP_REASON=$(aws ecs describe-tasks \
      --cluster default \
      --tasks "${TASK_ARN}" \
      --region "${AWS_REGION}" \
      --query "tasks[0].stoppedReason" --output text 2>/dev/null)
    echo "ERROR: task stopped — ${STOP_REASON}"
    exit 1
  fi

  sleep 20
done

echo "WARNING: timed out waiting for RUNNING status. Check the AWS ECS console."
echo "    URL: ${SERVICE_URL}"
exit 1
