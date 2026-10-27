# Production reference (not used for local development)

- Keep PostgreSQL and the FastAPI container on a private Docker network. Caddy is the only service with ports 80/443.
- EC2: t4g.micro (ARM64 images), encrypted EBS volumes for PostgreSQL/uploads, restricted security group, IMDSv2, no public SSH ingress; use AWS Systems Manager Session Manager.
- Put secrets in SSM Parameter Store/Secrets Manager, grant the instance role only read access to this application's paths, and rotate the JWT secret/passwords.
- Terminate TLS in Caddy and redirect HTTP to HTTPS. Use strict `Cache-Control: no-cache` for `index.html` and immutable hashed-cache headers for Flutter assets.
- Schedule `pg_dump`, retain encrypted backups outside the instance (S3 with least-privilege IAM), and restore-test periodically.
