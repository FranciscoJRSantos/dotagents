# Log-check query templates

Used by `@assess` Step 7, unsandboxed only. **Totals only**: every query ends in
`stats count(*)` and returns counts by route, caller family and status. Never put a
raw log line, request or response body, client address, user or record identifier
into any artifact. Queries may `parse @message` to extract a field, but never display
`@message`, and every extracted field is built so an ID cannot be captured: route
segments match only `v<digits>` or letters, so `/v1/patients/123/notes` becomes
`/v1/patients`; the caller is the first User-Agent token (a library or service name),
never an IP. Letters-only segments can still be names (`/patients/jane-doe`), so routes
are matched, not trusted: after the query, collapse every route that is not listed under
Exposes in the surveys (compared with `{}` for parameters) into one `<unlisted>` row and
never write its text.

Window: the last 14 days. Pass `--region <region>` on every call, one region per call; a
region the system map names but you did not query is a coverage gap. Replace `<log-group>` with the group the system map names
for the repo; `<start>` and `<end>` are epoch seconds.

```bash
START=$(date -u -d '14 days ago' +%s); END=$(date -u +%s)
QID=$(aws logs start-query --region <region> --log-group-name '<log-group>' --start-time "$START" --end-time "$END" \
  --query-string "$(cat <query file>)" --query queryId --output text)
for i in $(seq 1 30); do
  STATUS=$(aws logs get-query-results --region <region> --query-id "$QID" --query status --output text)
  [ "$STATUS" = Complete ] && break
  sleep 5
done
# one tab-separated line per result row: every grouped field, then the count
[ "$STATUS" = Complete ] && aws logs get-query-results --region <region> --query-id "$QID" \
  --query 'results[].map(&value, @)' --output text
```

## 1. ALB access logs: calls by route, caller and status

```insights
parse @message /"(?<verb>GET|POST|PUT|PATCH|DELETE) https?:\/\/[^\/]+(?<route>(\/(v\d+|[A-Za-z_-]+)){1,3})[^ ]* HTTP\/[0-9.]+" "(?<caller>[A-Za-z][A-Za-z0-9._-]*)/
| parse @message /(?<status>[1-5][0-9][0-9]) [0-9-]+ [0-9]+ [0-9]+ "/
| filter ispresent(route)
| stats count(*) as calls by verb, route, caller, status
| sort calls desc
| limit 200
```

## 2. ALB access logs: routes with no traffic

Run query 1, then compare its `route` values with the routes the surveys list under Exposes. A query whose status is not `Complete` after the wait is a coverage gap ("query did not finish; totals may be partial"), never an empty result. A route that never appears in 14 days is a candidate "unused route" finding, never a fact: say "no traffic in the window" and add the coverage caveats from Step 7.

## 2b. ALB access logs: server errors by route and day

```insights
parse @message /"(?<verb>GET|POST|PUT|PATCH|DELETE) https?:\/\/[^\/]+(?<route>(\/(v\d+|[A-Za-z_-]+)){1,3})[^ ]* HTTP\/[0-9.]+"/
| parse @message /(?<status>5[0-9][0-9]) [0-9-]+ [0-9]+ [0-9]+ "/
| filter ispresent(route) and ispresent(status)
| stats count(*) as errors by verb, route, bin(1d)
| sort errors desc
| limit 200
```

The status fields rely on the ALB access-log field order (`elb_status target_status received_bytes sent_bytes "request"`); if a query returns no rows for a busy service, check the format before reading silence as health.

## 3. ECS application logs: events by level (one log group per service)

```insights
parse @message /(?<level>ERROR|WARN|CRITICAL|FATAL)/
| filter ispresent(level)
| stats count(*) as events by level, bin(1d)
| sort events desc
| limit 100
```

## 4. SQS metrics: volume and backlog

Metric totals, no message content. One call per queue the interface sheets name:

```bash
for METRIC in NumberOfMessagesSent NumberOfMessagesReceived; do
  aws cloudwatch get-metric-statistics --region <region> --namespace AWS/SQS --metric-name "$METRIC" \
    --dimensions Name=QueueName,Value=<queue-name> \
    --start-time "$(date -u -d '14 days ago' +%FT%TZ)" --end-time "$(date -u +%FT%TZ)" \
    --period 86400 --statistics Sum --query 'Datapoints[].[Timestamp,Sum]' --output text
done
# ApproximateAgeOfOldestMessage is a gauge: Maximum only, never Sum
aws cloudwatch get-metric-statistics --region <region> --namespace AWS/SQS --metric-name ApproximateAgeOfOldestMessage \
  --dimensions Name=QueueName,Value=<queue-name> \
  --start-time "$(date -u -d '14 days ago' +%FT%TZ)" --end-time "$(date -u +%FT%TZ)" \
  --period 86400 --statistics Maximum --query 'Datapoints[].[Timestamp,Maximum]' --output text
```

A dead-letter queue with `NumberOfMessagesSent` above zero, or a source queue whose oldest message age keeps growing, is a reliability signal worth a finding.

## 5. Grafana: aggregated panels only

Read only already-aggregated panels (rates, counts, percentiles) that the team's dashboards expose. Ask the user for the dashboard URL before any call and read the token from the `GRAFANA_TOKEN` environment variable (never ask for it in chat, so it stays out of session transcripts); never export raw rows or an explore query that returns log lines. Record the panel title and the number you read, nothing else.

## Coverage gaps

Record each of these in `log-check.org` under `* Coverage gaps` instead of reading silence as safety:
- a batch or scheduled job that runs less often than every 14 days (its window may hold no run)
- a service with no ALB access logs or no application log group
- a log group with retention shorter than 14 days
- any query that returned an error or timed out
