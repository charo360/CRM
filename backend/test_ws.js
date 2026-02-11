// Test WebSocket connectivity to WhatsApp from inside Docker
var WebSocket = require("ws");
var ws = new WebSocket("wss://web.whatsapp.com/ws/chat", {
  headers: { "Origin": "https://web.whatsapp.com" }
});
ws.on("open", function() { console.log("WS_OPEN"); ws.close(); process.exit(0); });
ws.on("error", function(e) { console.log("WS_ERROR:" + e.message); process.exit(1); });
setTimeout(function() { console.log("WS_TIMEOUT"); process.exit(1); }, 10000);
