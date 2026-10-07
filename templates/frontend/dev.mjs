import { build, preview } from "vite";

// Complete the first build before serving it. A busy preview port fails here,
// before the long-running watcher starts, so npm reports the startup failure.
await build();
const server = await preview();
const watcher = await build({ build: { watch: {} } }).catch((error) => {
  server.httpServer.close();
  throw error;
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.once(signal, async () => {
    await watcher.close();
    server.httpServer.close();
    process.exit(0);
  });
}
