# Deploying Studio

Production is the same four images as `deploy/docker-compose.yml` (web, api, worker, plus a one-off `migrate`),
on any container platform (AWS ECS/Fargate, Google Cloud Run, Kubernetes), with managed services around them.

| Piece | Production choice |
|---|---|
| Web, API | 2+ containers each behind a load balancer with HTTPS; the web forwards `/api` to the API |
| Workers | Autoscaled on queue depth (`select count(*) from jobs where status='queued'`); CPU is enough to start, a GPU pool later for transcription |
| Database | Managed Postgres 16 (RDS, Cloud SQL, Neon) with daily backups and point-in-time recovery |
| Redis | Managed Redis (ElastiCache, Memorystore, Upstash); only live events, nothing durable |
| Storage | S3 or Cloudflare R2, private bucket, versioning on |
| Secrets | The platform's secret store (AWS Secrets Manager, GCP Secret Manager) injected as environment variables |

Release: build images → run `alembic upgrade head` (the `migrate` image) → roll out api, worker, web.

## 1. Storage bucket

Private bucket (block all public access). Browsers upload and play with presigned URLs, so the bucket needs a CORS rule
for the app's address:

```json
[{
  "AllowedOrigins": ["https://studio.yourcompany.com"],
  "AllowedMethods": ["GET", "PUT", "HEAD"],
  "AllowedHeaders": ["*"],
  "ExposeHeaders": ["ETag"],
  "MaxAgeSeconds": 3600
}]
```
`ETag` must be exposed: the browser sends each part's ETag back to complete a multipart upload.
Add a lifecycle rule that aborts incomplete multipart uploads after 7 days.

Least-privilege policy for the API and workers (one role or key each is better still):
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:AbortMultipartUpload",
                                   "s3:ListMultipartUploadParts"], "Resource": "arn:aws:s3:::studio-media/*"},
    {"Effect": "Allow", "Action": ["s3:ListBucket"], "Resource": "arn:aws:s3:::studio-media"}
  ]
}
```
On AWS, leave `S3_ENDPOINT_URL` empty and give the containers an IAM role instead of keys. On R2, set
`S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com`, `S3_REGION=auto` and an R2 API token's keys.

## 2. Sign-in (OIDC)

Redirect URI to register: `https://studio.yourcompany.com/api/auth/oidc/callback`

**Google Workspace**: Google Cloud console → APIs & Services → Credentials → Create OAuth client ID → Web
application; set the redirect URI; OAuth consent screen "Internal". Then:
```
AUTH_MODE=oidc
OIDC_ISSUER=https://accounts.google.com
OIDC_CLIENT_ID=...apps.googleusercontent.com
OIDC_CLIENT_SECRET=...
OIDC_ALLOWED_DOMAINS=yourcompany.com
BOOTSTRAP_ADMINS=you@yourcompany.com
```
**Microsoft Entra ID**: Entra admin center → App registrations → New registration (single tenant); Web redirect
URI as above; Certificates & secrets → new client secret; API permissions: openid, email, profile. Then
`OIDC_ISSUER=https://login.microsoftonline.com/<tenant-id>/v2.0` and the client ID and secret.

People outside `OIDC_ALLOWED_DOMAINS` can sign in only after an admin invites them (Admin → People).

## 3. Client connection secrets
Pick one:
- `SECRETS_BACKEND=aws`: keys live in AWS Secrets Manager under `studio/brand/<brand-id>/<tool>`. Give the API and
  workers `secretsmanager:CreateSecret`, `PutSecretValue`, `GetSecretValue` and `DeleteSecret` on
  `arn:aws:secretsmanager:<region>:<account>:secret:studio/brand/*` (workers need only `GetSecretValue`).
- `SECRETS_BACKEND=local`: keys are encrypted (Fernet) in the database with `SECRETS_KEY`. Keep that key in your
  platform's secret store; losing it makes stored keys unreadable (clients reconnect), leaking it with a database
  copy exposes them.

Library links are fetched by the workers. Studio refuses private and internal addresses (cloud metadata, the cluster
network, localhost) when a link is added and again before each scan; also restrict the workers' outbound network
to the internet if your platform allows it.

## 4. Required settings in production
`ENV=production`, `PUBLIC_URL=https://…`, `SECRET_KEY` (32+ random characters), `AUTH_MODE=oidc` and the OIDC values,
`DATABASE_URL`, `REDIS_URL`, the `S3_*` values, `S3_CREATE_BUCKET=false`. The API refuses to start with dev sign-in
or a placeholder secret key.

## 5. Operations
- Health: `GET /api/healthz` (process up) and `GET /api/readyz` (database, Redis and storage reachable) for the
  load balancer and alerts.
- Logs are JSON on stdout; ship them to your log store. Alert on failed jobs and on `readyz` failures.
- A worker that dies mid-job: its job is re-queued after `JOB_STALE_SECONDS` (60), up to `JOB_MAX_ATTEMPTS` (3).
- Scale workers by queue depth; each worker runs one job at a time and needs disk for its project workspaces
  (`WORKER_ROOT`, can be wiped anytime: everything is re-fetched from the bucket).
