/**
 * Zilo Browser Operator - Content Script (Enterprise Hardened)
 * Executes DOM-level actions with Shadow DOM & Iframe traversal, human click emulation,
 * React/Vue state override bypasses, and fuzzy text/attribute matching.
 */

// Momentarily highlight target element for visual AI feedback
function highlightElement(el) {
  if (!el) return;
  const originalOutline = el.style.outline;
  const originalBg = el.style.backgroundColor;

  el.style.outline = "3px solid #10b981"; // Enterprise emerald-500
  el.style.backgroundColor = "rgba(16, 185, 129, 0.25)";
  el.style.transition = "outline 0.2s, background-color 0.2s";

  setTimeout(() => {
    el.style.outline = originalOutline;
    el.style.backgroundColor = originalBg;
  }, 1200);
}

// Traverse Shadow DOM and visible Iframes recursively to locate element
function querySelectorAllDeep(selector, root = document) {
  let results = Array.from(root.querySelectorAll(selector));

  // 1. Recursive check inside open Shadow DOM roots
  const elements = root.querySelectorAll("*");
  for (const el of elements) {
    if (el.shadowRoot) {
      results = results.concat(querySelectorAllDeep(selector, el.shadowRoot));
    }
  }

  // 2. Recursive check inside accessible Iframes
  const iframes = root.querySelectorAll("iframe");
  for (const iframe of iframes) {
    try {
      if (iframe.contentDocument) {
        results = results.concat(querySelectorAllDeep(selector, iframe.contentDocument));
      }
    } catch (e) {
      // Cross-origin iframe (suppress security error, skip cross-domain frames)
    }
  }

  return results;
}

// Find element using CSS, XPath, ARIA, Placeholder, or fuzzy Text Match
function findElement(selector) {
  if (!selector) return null;

  // 1. XPath / Multi-syntax selector
  if (selector.startsWith("/") || selector.startsWith("//") || selector.startsWith("xpath=")) {
    const cleanXPath = selector.replace(/^xpath=/, "");
    try {
      const result = document.evaluate(
        cleanXPath,
        document,
        null,
        XPathResult.FIRST_ORDERED_NODE_TYPE,
        null
      );
      if (result.singleNodeValue) return result.singleNodeValue;
    } catch (e) {
      console.warn("[Zilo Content] XPath evaluate failed, falling back", e);
    }
  }

  // 2. Text matching fallback syntax: "text=Click Me"
  if (selector.startsWith("text=")) {
    const targetText = selector.replace(/^text=/, "").toLowerCase().trim();
    // Query all clickable and interactive elements deep
    const candidateSelectors = "a, button, input[type='button'], input[type='submit'], label, [role='button'], span, p";
    const candidates = querySelectorAllDeep(candidateSelectors);
    for (const el of candidates) {
      const text = el.textContent || "";
      if (text.toLowerCase().trim() === targetText || text.toLowerCase().includes(targetText)) {
        return el;
      }
    }
  }

  // 3. Clean CSS selector deep query (Shadow DOM & Iframe friendly)
  try {
    const deepMatches = querySelectorAllDeep(selector);
    if (deepMatches.length > 0) return deepMatches[0];
  } catch (err) {
    console.warn(`[Zilo Content] Standard querySelector failed for: ${selector}`, err);
  }

  // 4. Fuzzy fallback (Aria-label, placeholder, title search)
  try {
    const cleanSelector = selector.replace(/['"]/g, "");
    const fuzzySelector = `[aria-label*="${cleanSelector}"], [placeholder*="${cleanSelector}"], [title*="${cleanSelector}"], [id*="${cleanSelector}"]`;
    const fuzzyMatches = querySelectorAllDeep(fuzzySelector);
    if (fuzzyMatches.length > 0) return fuzzyMatches[0];
  } catch (e) {
    // Ignore invalid fuzzy selector queries
  }

  return null;
}

// Emulate full pointer sequence for indistinguishable human click mechanics
function clickElementHumanLike(el) {
  const events = ["mouseenter", "mouseover", "mousedown", "pointerdown", "mouseup", "pointerup", "click"];
  events.forEach(evName => {
    try {
      const ev = new MouseEvent(evName, {
        bubbles: true,
        cancelable: true,
        view: window,
        buttons: 1
      });
      el.dispatchEvent(ev);
    } catch (err) {
      console.error(`[Zilo Content] Event dispatch ${evName} failed:`, err);
    }
  });
}

// Emulate state-bypassing value setter for React, Vue, Angular components
function enterTextBypass(el, text) {
  el.focus();

  // Try bypassing React's internal value interceptor tracker override
  let valSetterMatched = false;
  try {
    const prototype = Object.getPrototypeOf(el);
    const valueDescriptor = Object.getOwnPropertyDescriptor(prototype, "value");
    if (valueDescriptor && valueDescriptor.set) {
      valueDescriptor.set.call(el, text);
      valSetterMatched = true;
    }
  } catch (e) {
    // Fail-open to standard native assignment
  }

  if (!valSetterMatched) {
    el.value = text;
  }

  // Dispatch fully bubbled reactivity updates
  const changeEvent = new Event("change", { bubbles: true });
  const inputEvent = new Event("input", { bubbles: true });
  el.dispatchEvent(inputEvent);
  el.dispatchEvent(changeEvent);

  // Dispatch keyup to trigger dynamic validations
  try {
    el.dispatchEvent(new KeyboardEvent("keyup", { bubbles: true, key: "Enter" }));
  } catch (err) {
    // Ignore keyup failures
  }

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
        clickElementHumanLike(el);
        sendResponse({ success: true, status: "clicked", selector });
      } catch (err) {
        sendResponse({ error: `Click failed: ${err.message}` });
      }
      break;

    case "type":
      try {
        enterTextBypass(el, text);
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
          extractedVal = el.value || "";
        } else if (data_type === "attribute" && text) {
          extractedVal = el.getAttribute(text) || "";
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
