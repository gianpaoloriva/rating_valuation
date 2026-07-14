#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Rating & Valuation Suite — stop the on-demand Fargate task
#
# Usage:
#   ./deploy/stop.sh        # stop all running rating-valuation-ondemand tasks
#                           # and close the security-group ingress
# -----------------------------------------------------------------------------
set -euo pipefail

AWS_REGION="eu-west-1"
CLUSTER="default"
TASK_FAMILY="rating-valuation-ondemand"
SECURITY_GROUP="sg-040737eb6164b6ec9"   # rating-valuation-ondemand (default VPC)

TASKS=$(aws ecs list-tasks --cluster "${CLUSTER}" --family "${TASK_FAMILY}" \
  --desired-status RUNNING --region "${AWS_REGION}" --query 'taskArns' --output text)

if [[ -z "${TASKS}" || "${TASKS}" == "None" ]]; then
  echo "No running task found."
else
  for TASK in ${TASKS}; do
    echo "==> Stopping ${TASK##*/}..."
    aws ecs stop-task --cluster "${CLUSTER}" --task "${TASK}" \
      --reason "manual stop via deploy/stop.sh" --region "${AWS_REGION}" > /dev/null
  done
  echo "==> Stopped. Billing for the task has ended."
fi

# Close the ingress opened by start.sh
EXISTING=$(aws ec2 describe-security-groups --group-ids "${SECURITY_GROUP}" \
  --region "${AWS_REGION}" --query 'SecurityGroups[0].IpPermissions' --output json)
if [[ "${EXISTING}" != "[]" ]]; then
  aws ec2 revoke-security-group-ingress --group-id "${SECURITY_GROUP}" \
    --region "${AWS_REGION}" --ip-permissions "${EXISTING}" > /dev/null
  echo "==> Security group ingress closed."
fi
