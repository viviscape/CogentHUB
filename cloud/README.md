# Cloud side — telemetry ingestion

The CogentHUB add-on POSTs telemetry to the **Cogent.API.Open** project in the
**Cogent Enterprise Advanced** solution (published at `https://api.cogentlog.io`).

## Endpoint

```
POST /api/v1/hub/telemetry
Header: APIKey: <account api key>
Body:   HubTelemetryBatch (snake_case JSON)
```

Auth is handled globally by `ApiKeyHandler` (validates the `APIKey` header against
`SEC_AccountAPIKeys` and injects the `pid` / platform account id). The controller reads
the account via `GetPlatformAccountID()`.

## Files added (in `Cogent Enterprise Advanced/`)

| File | Purpose |
|---|---|
| `Cogent.DAL/sql/012-add-hub-telemetry.sql` | DDL for `HUB_Hubs` + `HUB_TelemetryEvents`. **Run once per environment.** |
| `Cogent.BL/Models/HubTelemetry.cs` | `HubTelemetryBatch`, `HubTelemetryEvent`, `HubTelemetryResult` DTOs. |
| `Cogent.BL/HubService.cs` | Upserts the hub, bulk-inserts events via raw parameterized SQL. |
| `Cogent.API.Open/Controllers/HubController.cs` | `POST /api/v1/hub/telemetry`. |

Each file was also registered in the respective classic `.csproj` (`<Compile Include=...>`).

## Design notes

- The `HUB_*` tables are **not** mapped in the `CogentDB` EDMX, so no model regeneration
  is needed. `HubService` uses `context.Database.ExecuteSqlCommand` / `SqlQuery` on the
  existing `CogentDBEntities` connection — matching the codebase's raw-SQL idiom.
- JSON is bound by Web API's Newtonsoft formatter; DTO properties are snake_case to match
  the wire format the add-on sends.

## Deploy

1. Run `Cogent.DAL/sql/012-add-hub-telemetry.sql` against the target database.
2. Build/publish `Cogent.API.Open` (MSBuild; see that project's `CLAUDE.md`).

## Not done (intentional / follow-ups)

- **MCP server (`CogentCloudMCP`) not updated.** That project exposes *AI-callable* tools;
  machine telemetry ingestion isn't one. The natural MCP addition is **Phase 2** (cloud →
  device control), where `hub.call_service` / trigger tools would let an agent actuate hub
  devices. Add those when Phase 2 lands.
- **Pre-existing build blocker:** `Cogent.BL/OrderService.cs` references `LegTrack.dispatch_status`,
  a property missing from `Cogent.BL/Models/LegTrack.cs` (3 errors). Unrelated to this work
  and appears to be an in-progress edit. The full solution won't build until that's resolved
  (one-line property add, owner's call). The hub files themselves compile clean.
