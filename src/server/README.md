# Central Wagon Service

See [Live player updates](../../docs/realtime.md) for the Redis service,
development startup, WebSocket protocol, and deployment checks.

## Upload routes

Admin file fields take one of two routes, and the difference is deliberate:

- **Sounds and avatars** upload straight from the browser to S3 (the form
  passes `s3_upload_dir`). This keeps large audio off the web container, but it
  needs the bucket to grant CORS to the uploading origin — including
  `https://admin.cosound.ca`, where the admin now lives. Without that grant the
  browser's `PUT` is blocked and the upload stops after signing its first part,
  with nothing in the Django log but two `200`s.
- **The vote chime** uploads to this origin instead, over TUS, and Django
  forwards the accepted bytes to S3. It is capped at 5 MB and has to reach
  Python anyway for `validate_chime`, so a direct upload would only have
  downloaded the object straight back out of S3 to inspect it. TUS stages
  chunks in `MEDIA_ROOT/file-form-uploads/`, which `config/settings.py` creates
  at import — the TUS view writes its first chunk there and 500s if it is
  missing.

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
