# Qiniu Object Storage Setup

Parrot uses the official Qiniu Python and JavaScript SDKs. The backend creates a short-lived,
exact-key Qiniu upload token; the browser uses that token to upload directly to Kodo.

## Upload Flow

1. An authorized resource endpoint issues a 15-minute, single-object Qiniu upload token.
2. The browser keeps that token only in memory to upload the staged object.
3. The resource completion endpoint reads and validates that object, writes a canonical
   private object, then deletes the staging object.

The bucket is never public and applications must not save returned upload tokens.

## Credential Boundaries

The account AK/SK is read from the selected complete deployment TOML and is used only by the backend
SDK to sign upload tokens and authorized reads. During the current MVP it must be a disposable test
account; before real production use it must be rotated and moved to an external secret source. A
browser receives only an upload token scoped to one object key, its declared MIME type, and its
declared maximum size. Do not expose AK/SK, private download tokens, or management credentials to
the browser.

## Bucket Controls

- Keep the bucket private.
- Configure CORS with only the deployed frontend origins and the methods/headers required by the
  Qiniu JavaScript SDK. Do not use `*` as an allowed origin.
- Add a lifecycle rule that expires `parrot/staging/` objects within 24 hours.
- Encrypt the bucket and enable audit logging according to the deployment's data policy.

## Configuration

Set all current MVP values in the selected TOML file's `[object_storage]` section. `access_key` and
`secret_key` follow the disposable-test-account boundary above. The download domain must use HTTPS
in production. The bucket must exist before enabling the frontend upload flow.

Use the Qiniu bucket name and its configured CDN or download domain. The SDK resolves the upload
region itself; do not substitute a CDN delivery domain for an upload endpoint.

```toml
[object_storage]
provider = "qiniu"
bucket = "<qiniu-bucket-name>"
key_prefix = "parrot"
download_domain = "https://<qiniu-cdn-domain>"
upload_token_seconds = 900
access_key = "<disposable-test-access-key>"
secret_key = "<disposable-test-secret-key>"
```

The browser uploads through the Qiniu SDK, not the delivery CDN. Tenant-private objects continue
to be read through Parrot's authorized routes; do not turn them public merely to use CDN delivery.
