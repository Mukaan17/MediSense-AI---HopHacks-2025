resource "aws_ecs_cluster" "main" {
  name = var.project
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_service_discovery_private_dns_namespace" "internal" {
  name = "${var.project}.internal"
  vpc  = aws_vpc.main.id
}

resource "aws_service_discovery_service" "backend" {
  name = "backend"
  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.internal.id
    dns_records {
      type = "A"
      ttl  = 10
    }
  }
}

resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${var.project}"
  retention_in_days = 90
}

locals {
  backend_environment = [
    { name = "APP_MODE", value = var.app_mode },
    { name = "REDIS_URL", value = "redis://${aws_elasticache_replication_group.redis.primary_endpoint_address}:6379/0" },
    { name = "CASE_DB_URL", value = "postgresql+psycopg://medisense:${var.db_password}@${aws_db_instance.cases.address}:5432/medisense" },
    { name = "FINALIZE_MODE", value = "queue" },
    { name = "CASE_RETENTION_DAYS", value = tostring(var.case_retention_days) },
    { name = "SECRETS_BACKEND", value = "aws" },
    { name = "SECRETS_PREFIX", value = "${var.project}/" },
    { name = "AWS_REGION", value = var.region },
  ]
}

resource "aws_ecs_task_definition" "backend" {
  family                   = "${var.project}-backend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.backend_cpu
  memory                   = var.backend_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  volume {
    name = "rag-store"
    efs_volume_configuration {
      file_system_id     = aws_efs_file_system.shared.id
      transit_encryption = "ENABLED"
      authorization_config {
        access_point_id = aws_efs_access_point.rag_store.id
        iam             = "ENABLED"
      }
    }
  }

  container_definitions = jsonencode([{
    name         = "backend"
    image        = var.backend_image
    essential    = true
    portMappings = [{ containerPort = 8000, protocol = "tcp" }]
    environment  = local.backend_environment
    mountPoints  = [{ sourceVolume = "rag-store", containerPath = "/app/rag_store" }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.app.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "backend"
      }
    }
    healthCheck = {
      command  = ["CMD-SHELL", "curl -sf http://localhost:8000/health || exit 1"]
      interval = 30
      timeout  = 5
      retries  = 3
    }
  }])
}

resource "aws_ecs_task_definition" "worker" {
  family                   = "${var.project}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 1024
  memory                   = 4096
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  volume {
    name = "rag-store"
    efs_volume_configuration {
      file_system_id     = aws_efs_file_system.shared.id
      transit_encryption = "ENABLED"
      authorization_config {
        access_point_id = aws_efs_access_point.rag_store.id
        iam             = "ENABLED"
      }
    }
  }

  container_definitions = jsonencode([{
    name        = "worker"
    image       = var.backend_image
    essential   = true
    command     = ["arq", "worker.settings.WorkerSettings"]
    environment = local.backend_environment
    mountPoints = [{ sourceVolume = "rag-store", containerPath = "/app/rag_store" }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.app.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "worker"
      }
    }
  }])
}

resource "aws_ecs_task_definition" "frontend" {
  family                   = "${var.project}-frontend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.execution.arn

  container_definitions = jsonencode([{
    name         = "frontend"
    image        = var.frontend_image
    essential    = true
    portMappings = [{ containerPort = 80, protocol = "tcp" }]
    environment = [
      { name = "BACKEND_HOST", value = "backend.${var.project}.internal:8000" },
      { name = "API_URL", value = "" },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.app.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "frontend"
      }
    }
  }])
}

# Rolling deploys with the circuit breaker: a bad revision that fails
# health checks rolls back automatically. (Blue/green via CodeDeploy is a
# later step once a second listener/TG pair is justified.)
resource "aws_ecs_service" "backend" {
  name                   = "backend"
  cluster                = aws_ecs_cluster.main.id
  task_definition        = aws_ecs_task_definition.backend.arn
  desired_count          = var.backend_desired_count
  launch_type            = "FARGATE"
  enable_execute_command = true

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets         = aws_subnet.private[*].id
    security_groups = [aws_security_group.services.id]
  }

  service_registries {
    registry_arn = aws_service_discovery_service.backend.arn
  }
}

resource "aws_ecs_service" "worker" {
  name            = "worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = var.worker_desired_count
  launch_type     = "FARGATE"

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets         = aws_subnet.private[*].id
    security_groups = [aws_security_group.services.id]
  }
}

resource "aws_ecs_service" "frontend" {
  name            = "frontend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.frontend.arn
  desired_count   = var.frontend_desired_count
  launch_type     = "FARGATE"

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets         = aws_subnet.private[*].id
    security_groups = [aws_security_group.services.id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.frontend.arn
    container_name   = "frontend"
    container_port   = 80
  }

  depends_on = [aws_lb_listener.http]
}
