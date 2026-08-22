resource "aws_ecr_repository" "backend" {
  name = "clinical-ai-backend"
}

resource "aws_ecr_repository" "frontend" {
  name = "clinical-ai-frontend"
}

# Shared model/rag storage (KB volume; snapshot policy is the DR answer
# for caches - the corpus itself is rebuildable).
resource "aws_efs_file_system" "shared" {
  encrypted = true
  tags      = { Name = "${var.project}-efs" }
}

resource "aws_efs_mount_target" "shared" {
  count           = 2
  file_system_id  = aws_efs_file_system.shared.id
  subnet_id       = aws_subnet.private[count.index].id
  security_groups = [aws_security_group.services.id]
}

resource "aws_efs_access_point" "rag_store" {
  file_system_id = aws_efs_file_system.shared.id
  posix_user {
    uid = 0
    gid = 0
  }
  root_directory {
    path = "/rag_store"
    creation_info {
      owner_uid   = 0
      owner_gid   = 0
      permissions = "755"
    }
  }
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id       = "${var.project}-redis"
  description                = "Case store + job queue"
  engine                     = "redis"
  node_type                  = "cache.t4g.small"
  num_cache_clusters         = 2
  automatic_failover_enabled = true
  multi_az_enabled           = true
  subnet_group_name          = aws_elasticache_subnet_group.redis.name
  security_group_ids         = [aws_security_group.services.id]
}

resource "aws_elasticache_subnet_group" "redis" {
  name       = "${var.project}-redis"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_db_subnet_group" "cases" {
  name       = "${var.project}-cases"
  subnet_ids = aws_subnet.private[*].id
}

# Durable case timeline (decision D3).
resource "aws_db_instance" "cases" {
  identifier                = "${var.project}-cases"
  engine                    = "postgres"
  engine_version            = "16"
  instance_class            = "db.t4g.micro"
  allocated_storage         = 20
  db_name                   = "medisense"
  username                  = "medisense"
  password                  = var.db_password
  db_subnet_group_name      = aws_db_subnet_group.cases.name
  vpc_security_group_ids    = [aws_security_group.services.id]
  multi_az                  = false
  storage_encrypted         = true
  backup_retention_period   = 7
  skip_final_snapshot       = false
  final_snapshot_identifier = "${var.project}-cases-final"
}
