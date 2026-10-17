# Optional: GCP credentials in compose (project-specific)

Default `catalog.full.json` in scaffold **does not** mount `google-credentials.json`.

If your **java-boot** API needs GCP:

1. Add to `ops/compose/catalog.json` templates `api_dev` / `api_prod`:

   ```yaml
   volumes:
     - {secrets_backend}/google-credentials.json:/app/google-credentials.json:ro
   environment:
     GOOGLE_APPLICATION_CREDENTIALS: /app/google-credentials.json
   ```

2. Place real JSON at `<secrets root>/<module's secrets folder>/google-credentials.json` (gitignored).

3. Set vars in that folder's `.env.*` (e.g. `GCP_PROJECT_ID`).

4. `.\tools\stack-kit.ps1 compose-gen`

Do not put project brand names in the kit scaffold — only your manifest's `project` values.
