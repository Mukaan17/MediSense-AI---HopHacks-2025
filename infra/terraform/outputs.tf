output "alb_dns_name" {
  value = aws_lb.main.dns_name
}

output "ecr_backend" {
  value = aws_ecr_repository.backend.repository_url
}

output "ecr_frontend" {
  value = aws_ecr_repository.frontend.repository_url
}

output "redis_endpoint" {
  value = aws_elasticache_replication_group.redis.primary_endpoint_address
}

output "cases_db_address" {
  value = aws_db_instance.cases.address
}
