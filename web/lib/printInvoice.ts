/**
 * Print any DOM node by cloning it into a fresh window. Avoids the usual
 * `@media print` + `visibility: hidden` tricks, which fail when the source
 * node lives inside a `position: fixed` modal or has `overflow: hidden`
 * ancestors (everything in our invoice modal).
 *
 * The cloned window only contains the node's HTML plus a tiny print
 * stylesheet, so nothing external can hide or clip the output.
 */
export function printNode(node: HTMLElement | null, title = "Invoice") {
  if (!node) return;
  const html = node.outerHTML;
  const win = window.open("", "_blank", "width=900,height=1200");
  if (!win) {
    alert("Please allow pop-ups to print this invoice.");
    return;
  }
  win.document.write(`<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>${title.replace(/</g, "&lt;")}</title>
  <style>
    @page { size: auto; margin: 12mm; }
    html, body { margin: 0; padding: 0; background: white; }
    body { font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
    /* Drop the on-screen card shadow + rounded border when printing */
    @media print {
      .invoice-preview-root { box-shadow: none !important; border: none !important; border-radius: 0 !important; }
    }
  </style>
</head>
<body>${html}</body>
</html>`);
  win.document.close();
  // Wait for images (logo) to load before firing print dialog.
  const trigger = () => {
    try { win.focus(); win.print(); } catch { /* noop */ }
    // Leave the window open so the user can re-print or save; they'll close it.
  };
  const imgs = Array.from(win.document.images);
  if (imgs.length === 0) {
    setTimeout(trigger, 100);
    return;
  }
  let remaining = imgs.length;
  const done = () => { remaining -= 1; if (remaining <= 0) setTimeout(trigger, 50); };
  imgs.forEach(img => {
    if (img.complete) done();
    else { img.addEventListener("load", done); img.addEventListener("error", done); }
  });
  // Safety net in case something never fires.
  setTimeout(trigger, 2500);
}
