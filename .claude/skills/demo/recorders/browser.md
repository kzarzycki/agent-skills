# Web page: Playwright video

Playwright records every page of a browser context to WebM when the context is created
with a video directory. The file is complete only after the context closes.

```ts
const context = await browser.newContext({
  viewport: { width: 1280, height: 720 },
  recordVideo: { dir: tmp, size: { width: 1280, height: 720 } },
  storageState: "auth.json", // logged in before recording, so the video skips the login
});
const page = await context.newPage();
// ... the scenario ...
await context.close();
const webm = await page.video()!.path();
```

Python's equivalent is `browser.new_context(record_video_dir=tmp, record_video_size=...)`.
In Playwright Test, `use: { video: "on" }` records each test.

- Do setup (login, seed data) in a context without `recordVideo`, and save its
  `storageState` for the recorded one.
- Launch with `slowMo` (around 300 ms) so a viewer can follow clicks and typing.
- Pass the `.webm` to `scripts/demo.sh`, which converts it to H.264 MP4.
