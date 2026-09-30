output "artifact_bucket" {
  value = aws_s3_bucket.artifacts.id
}
output "cluster_arn" {
  value = aws_ecs_cluster.lab.arn
}
output "worker_task_definition_arn" {
  value = aws_ecs_task_definition.worker.arn
}
