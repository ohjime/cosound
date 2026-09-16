# Central Wagon Service

See [Live player updates](../../docs/realtime.md) for the Redis service,
development startup, WebSocket protocol, and deployment checks.

## S3 temporary-upload lifecycle

Direct browser uploads are staged under `file-form-uploads/` before accepted
files are copied to their permanent media keys. The production S3 bucket must
have a lifecycle rule filtered to that exact prefix which:

- expires completed objects after one day;
- aborts incomplete multipart uploads after one day; and
- expires noncurrent versions after one day when bucket versioning is enabled.

Configure this outside the application so its runtime credentials do not need
bucket-administration permissions. Merge the rule into any existing lifecycle
configuration: `put-bucket-lifecycle-configuration` replaces the bucket's
complete ruleset. Verify the deployed rules with:

```bash
aws s3api get-bucket-lifecycle-configuration \
  --bucket "$AWS_STORAGE_BUCKET_NAME"
```
