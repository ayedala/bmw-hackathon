// electron-builder afterPack hook: places the Next.js standalone server
// (including its .next folder and node_modules, which the file globs skip)
// into the app's Resources/app-server folder.
const fs = require("node:fs");
const path = require("node:path");

exports.default = async function afterPack(context) {
  const source = path.resolve(__dirname, "..", ".next", "standalone");
  if (!fs.existsSync(path.join(source, "server.js"))) {
    throw new Error("Standalone server missing — run `npm run app:prepare` first.");
  }
  const resources =
    context.electronPlatformName === "darwin"
      ? path.join(context.appOutDir, `${context.packager.appInfo.productFilename}.app`, "Contents", "Resources")
      : path.join(context.appOutDir, "resources");
  const target = path.join(resources, "app-server");
  fs.rmSync(target, { recursive: true, force: true });
  // sharp (image optimisation) is traced by Next but unused here, and its native
  // binaries are platform-specific; leave it out of the desktop bundle.
  fs.cpSync(source, target, {
    recursive: true,
    dereference: true,
    filter: (src) => !/[\\/]node_modules[\\/](@img|sharp)([\\/]|$)/.test(src),
  });
  console.log(`  • copied server bundle to ${target}`);
};
