/**
 * Zilo Browser Operator - Content Script
 * Executes DOM-level actions (click, type, extract, scroll) with visual highlights.
 */

// Momentarily highlight target element in yellow for visual AI feedback
function highlightElement(el) {
  if (!el) return;
  const originalOutline = el.style.outline;
  const originalBg = el.style.backgroundColor;

  el.style.outline = "3px solid #facc15"; // Tailwind yellow-400
  el.style.backgroundColor = "rgba(250, 204, 21, 0.2)";

  setTimeout(() => {
    el.style.outline = originalOutline;
    el.style.backgroundColor = originalBg;
  }, 1000);
}

// Find element using CSS or XPath selectors
function findElement(selector) {
  if (!selector) return null;

  // XPath matching
  if (selector.startsWith("/") || selector.startsWith("//") || selector.startsWith("xpath=")) {
    const cleanXPath = selector.replace(/^xpath=/, "");
    const result = document.evaluate(
      cleanXPath,
      document,
      null,
      XPathResult.FIRST_ORDERED_NODE_TYPE,
      null
    );
    return result.singleNodeValue;
  }

  // Text matching fallback syntax: "text=Click Me"
  if (selector.startsWith("text=")) {
    const targetText = selector.replace(/^text=/, "").toLowerCase().trim();
    const elements = document.querySelectorAll("a, button, input[type='button'], input[type='submit'], label, span");
    for (const el of elements) {
      if (el.textContent.toLowerCase().trim() === targetText) {
        return el;
      }
    }
  }

  // Standard CSS selector
  try {
    return document.querySelector(selector);
  } catch (err) {
    console.error(`[Zilo Content] Invalid CSS selector: ${selector}`, err);
    return null;
  }
}

// Emulate natural text entry (fires input/change events for modern reactive webapps)
function enterText(el, text) {
  el.focus();
  el.value = text;
  
  // Dispatch mock typing events so React, Vue, Angular update state
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
  el.blur();
}

// Message Router
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const { action, selector, text, data_type } = message;
  console.log(`[Zilo Content] Received message: ${action}`, message);

  const el = findElement(selector);
  
  if (action !== "navigate" && !el) {
    sendResponse({ error: `Element not found for selector: "${selector}"` });
    return true;
  }

  highlightElement(el);

  switch (action) {
    case "click":
      try {
        el.click();
        sendResponse({ success: true, status: "clicked", selector });
      } catch (err) {
        sendResponse({ error: `Click failed: ${err.message}` });
      }
      break;

    case "type":
      try {
        enterText(el, text);
        sendResponse({ success: true, status: "typed", selector, text_length: text.length });
      } catch (err) {
        sendResponse({ error: `Typing failed: ${err.message}` });
      }
      break;

    case "scroll":
      try {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        sendResponse({ success: true, status: "scrolled", selector });
      } catch (err) {
        sendResponse({ error: `Scroll failed: ${err.message}` });
      }
      break;

    case "extract":
      try {
        let extractedVal = "";
        if (data_type === "html") {
          extractedVal = el.outerHTML;
        } else if (data_type === "value") {
          extractedVal = el.value;
        } else if (data_type === "attribute" && text) {
          extractedVal = el.getAttribute(text);
        } else {
          extractedVal = el.textContent ? el.textContent.trim() : "";
        }
        sendResponse({ success: true, status: "extracted", selector, data: extractedVal });
      } catch (err) {
        sendResponse({ error: `Extraction failed: ${err.message}` });
      }
      break;

    default:
      sendResponse({ error: `Unknown content action: ${action}` });
  }

  return true; // Keep message channel open for async response
});
