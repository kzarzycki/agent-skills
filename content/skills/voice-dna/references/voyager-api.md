# LinkedIn Voyager API — Technical Reference

## 1. Voyager API Method (PREFERRED)

Use this over DOM scraping. External profiles aggressively virtualize the DOM (~5 posts rendered), making scraping unreliable. The Voyager GraphQL API returns full post text, metadata, and engagement in structured JSON with proper pagination.

### Step-by-step Chrome MCP workflow

1. **Navigate** to `https://www.linkedin.com/in/{handle}/recent-activity/all/` (must be authenticated)
2. **Trigger an API call** — click "Show More" at page bottom
3. **Capture the endpoint** with `read_network_requests` filtered to `voyager/api`:
   ```
   https://www.linkedin.com/voyager/api/graphql?variables=(count:40,start:0,profileUrn:{urn},paginationToken:{token})&queryId=voyagerFeedDashProfileUpdates.{hash}
   ```
4. **Extract** `profileUrn` and `queryId` from the captured URL
5. **Get CSRF token:**
   ```js
   const csrf = document.cookie.match(/JSESSIONID="([^"]+)"/)?.[1];
   ```
6. **Fetch a page:**
   ```js
   const res = await fetch(
     `https://www.linkedin.com/voyager/api/graphql?variables=(count:40,start:0,profileUrn:${profileUrn},paginationToken:${encodeURIComponent(paginationToken)})&queryId=${queryId}`,
     {
       headers: {
         'csrf-token': csrf,
         'accept': 'application/json',
       },
     }
   );
   const data = await res.json();
   ```
7. **Paginate** — extract next token and repeat until null:
   ```js
   const nextToken = data.data.feedDashProfileUpdatesByMemberShareFeed.metadata.paginationToken;
   ```

### Response parsing

Filter `data.included[]` by `$type`:

```js
const updates = data.included.filter(
  e => e['$type'] === 'com.linkedin.voyager.dash.feed.Update'
);
const counts = data.included.filter(
  e => e['$type'] === 'com.linkedin.voyager.dash.feed.SocialActivityCounts'
);
```

Per update entity:
- **Post text:** `update.commentary.text.text`
- **Activity URN:** `update.metadata.backendUrn` (e.g. `urn:li:activity:7654321`)
- **Repost detection:** `update.resharedUpdate` — present if the post is a reshare

Cross-reference engagement by matching `activityUrn` in the counts' `entityUrn`:

```js
const activityId = update.metadata.backendUrn.split(':').pop();
const engagement = counts.find(c => c.entityUrn?.includes(activityId));
// engagement.numLikes, engagement.numComments, engagement.numShares
```

### Timestamp from snowflake

LinkedIn activity IDs are snowflake IDs using **Unix epoch** (NOT Twitter epoch):

```js
const timestamp = new Date(Number(BigInt(activityId) >> 22n)).toISOString();
```

Do NOT add `1288834974657`. That is the Twitter epoch offset and produces dates ~40 years in the future.

### Pagination loop (complete)

```js
let paginationToken = '';
let allPosts = [];
const PAGE_DELAY = 800;

while (true) {
  const vars = `(count:40,start:0,profileUrn:${profileUrn}${
    paginationToken ? `,paginationToken:${encodeURIComponent(paginationToken)}` : ''
  })`;
  const res = await fetch(
    `https://www.linkedin.com/voyager/api/graphql?variables=${vars}&queryId=${queryId}`,
    { headers: { 'csrf-token': csrf, 'accept': 'application/json' } }
  );
  const data = await res.json();
  const updates = data.included.filter(
    e => e['$type'] === 'com.linkedin.voyager.dash.feed.Update'
  );
  if (!updates.length) break;
  allPosts.push(...updates);
  const next = data.data.feedDashProfileUpdatesByMemberShareFeed.metadata.paginationToken;
  if (!next) break;
  paginationToken = next;
  await new Promise(r => setTimeout(r, PAGE_DELAY));
}
```

## 2. Content Output Strategy

- **Primary channel:** `console.log()` + `read_console_messages`. The JS tool return value gets blocked by LinkedIn's content security filter when returning combined social media text with URLs.
- **Compact JSON batches:** Strip URLs from output or return structured data without raw links.
- **Large corpora (>1MB):** Output chunks to `console.log`, read all at once with high limit, then use `scripts/parse-voyager-corpus.py` to parse into a clean corpus file.
- **Rate limiting:** ~800ms delay between pages. LinkedIn returns 40-50 posts per page. Tested at 2800+ posts over ~10 years.

## 3. Gotchas

- **`start` parameter alone does not paginate** — returns the same page. MUST use `paginationToken` from each response.
- **Snowflake = Unix epoch** — off by ~40 years if you add Twitter epoch offset.
- **Deduplicate by `activityUrn`** after full extraction — page boundaries can overlap.
- **DOM scraping on external profiles fails** — virtualization renders only ~5 posts with placeholder `<li>` elements for the rest. This is why the API method is preferred.
- **`read_console_messages` with `clear: true`** clears ALL messages including unread. Read ALL first (high limit), THEN clear.

## 4. Fallback: DOM Scraping + Fetch Expansion

When the API endpoint cannot be captured (e.g. network tab not available), fall back to DOM scraping on the user's **own** profile (works better than external):

1. **Slow scroll** to load posts — 400px steps, 500ms delay:
   ```js
   window.scrollBy(0, 400);
   ```
2. **Capture visible posts** into a `window.*` variable (survives extension disconnects).
3. **Expand truncated posts** — activity feed shows "...more" snippets. Fetch individual post URLs for full text:
   ```js
   const res = await fetch(`https://www.linkedin.com/feed/update/urn:li:activity:${id}/`);
   const html = await res.text();
   ```
4. **Parse `<code>` blocks** in the HTML for HTML-encoded JSON — decode entities, find the longest `"text":"..."` match (>100 chars) for the post body.

Limitations: slow (~500ms per post for expansion), truncation requires per-post fetch, reposts need separate handling (longest text may be reshared content, not user's commentary).
