import { build, preview } from "vite";

const watcher = await build({ build: { watch: {} } });
let server;
let exiting = false;

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, async () => {
    if (exiting) return;
    exiting = true;
    setTimeout(() => process.exit(1), 5000).unref();

    try {
      await watcher.close();
      if (server) {
        await new Promise((resolve) => server.httpServer.close(resolve));
      }
    } catch (error) {
      console.error(error);
      process.exit(1);
    }
  });
}

let starting = false;
// Wait for the first successful watch build before starting the preview server.
// If preview startup fails (e.g. port in use), reject to crash the dev runner.
await new Promise((resolve, reject) => {
  watcher.on("event", async (event) => {
    if (event.code === "END" && !starting) {
      starting = true;
      try {
        server = await preview();
        resolve();
      } catch (error) {
        try {
          await watcher.close();
        } catch (cleanupError) {
          console.error("Watcher cleanup failed:", cleanupError);
        }
        reject(error);
      }
    }
  });
});
